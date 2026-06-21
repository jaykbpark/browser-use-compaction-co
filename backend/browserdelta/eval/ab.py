"""A/B evaluation: baseline (full state + screenshot) vs BrowserDelta compact.

The eval is modeled on how real browser-agent benchmarks (WebArena, Mind2Web,
WebVoyager) score an agent: a task suite, per-step *action grounding* accuracy,
and a cost measure. Here the "cost" is the token budget the observation spends,
and the quality measure is whether the element needed for the next scripted
action survives into the observation we actually send to the LLM.

For every recorded step we compare two observation strategies:

* baseline -- the naive payload an agent sends with no compaction: the full
  after-state (url, title, every visible text line, every interactive element)
  plus a screenshot.
* compact -- BrowserDelta's ``llm_observation`` (a diff summary plus the top
  interactive refs), with a screenshot only when the codec falls back.

We report, per step and in aggregate:

* token estimate (baseline vs compact, and the savings)
* route used (baseline is always full-state+screenshot; compact is one of
  ``structural`` / ``image_crop`` / ``vision_full``)
* whether the predicted next action matches the expected next action
* whether a fallback was needed
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from browserdelta.compaction.codec import compact_run
from browserdelta.schemas import (
    BrowserAction,
    CompactObservation,
    InteractiveElement,
    PageState,
    StepRecord,
)
from browserdelta.storage import read_json, read_steps

# Targets in task files may carry a Playwright-style locator prefix.
_TARGET_PREFIXES = ("css=", "text=", "placeholder=", "label=")

# Maps the codec's fallback decision to a human eval "route".
_ROUTE_BY_FALLBACK = {
    "none": "structural",
    "crop": "image_crop",
    "full_screenshot": "vision_full",
}

BASELINE_ROUTE = "full_state+screenshot"


@dataclass
class EvalConfig:
    """Knobs and documented assumptions for the eval."""

    chars_per_token: int = 4
    # OpenAI high-detail image tiling constants.
    image_base_tokens: int = 85
    image_tile_tokens: int = 170
    image_tile_px: int = 512
    image_max_long_px: int = 2048
    image_min_short_px: int = 768
    # The compact llm_observation text lists this many interactive elements
    # (see compaction.codec._render_llm_observation). Grounding for the compact
    # strategy is judged against exactly the elements the LLM can read.
    compact_text_interactive_limit: int = 12


def estimate_text_tokens(text: str, config: EvalConfig | None = None) -> int:
    """Estimate text tokens with the same heuristic the codec uses (chars / 4)."""

    cfg = config or EvalConfig()
    if not text:
        return 0
    return max(1, round(len(text) / cfg.chars_per_token))


def estimate_image_tokens(width: int, height: int, config: EvalConfig | None = None) -> int:
    """Estimate vision tokens for one screenshot using OpenAI high-detail tiling.

    The image is scaled to fit ``image_max_long_px`` on the long side and
    ``image_min_short_px`` on the short side, then split into 512px tiles. Cost
    is ``base + tile * n_tiles``. This is a documented, deterministic stand-in
    for real provider pricing.
    """

    cfg = config or EvalConfig()
    if width <= 0 or height <= 0:
        return 0

    long_side, short_side = max(width, height), min(width, height)
    if long_side > cfg.image_max_long_px:
        scale = cfg.image_max_long_px / long_side
        long_side, short_side = long_side * scale, short_side * scale
    if short_side > cfg.image_min_short_px:
        scale = cfg.image_min_short_px / short_side
        long_side, short_side = long_side * scale, short_side * scale

    tiles = math.ceil(long_side / cfg.image_tile_px) * math.ceil(short_side / cfg.image_tile_px)
    return cfg.image_base_tokens + cfg.image_tile_tokens * tiles


def _resolve_artifact(run_path: Path, stored: str) -> Path:
    """Resolve a screenshot/crop path that the codec may store relative to CWD.

    Crop paths are written as ``runs/<id>/crops/...`` (relative to the working
    directory), while screenshot pointers are relative to the run folder. Try the
    likely bases and fall back to matching the ``crops/...`` suffix so the eval
    works regardless of where the run folder lives.
    """

    candidates = [Path(stored), run_path / stored]
    marker = "crops/"
    if marker in stored:
        candidates.append(run_path / stored[stored.index(marker) :])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _image_size(path: Path) -> tuple[int, int]:
    if not path.exists():
        return (0, 0)
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def _baseline_payload(state: PageState) -> dict[str, Any]:
    """The full observation a naive agent would send (text portion)."""

    return {
        "url": state.url,
        "title": state.title,
        "text": state.text,
        "interactive": [element.model_dump(mode="json") for element in state.interactive],
        "focused_ref": state.focused_ref,
        "console_errors": state.console_errors,
        "network_errors": state.network_errors,
    }


def _normalize(value: str) -> str:
    return " ".join(value.split()).strip().lower()


def _strip_target_prefix(target: str) -> str:
    for prefix in _TARGET_PREFIXES:
        if target.startswith(prefix):
            return target[len(prefix) :]
    return target


def _is_selector_target(target: str | None) -> bool:
    """True when the target is an explicit locator (css=/text=/...).

    Selector targets hand the agent an exact element, so they do not test
    whether the element survived into the observation -- they are not grounding
    samples.
    """

    return bool(target) and target.startswith(_TARGET_PREFIXES)


def _needs_grounding(action: BrowserAction) -> bool:
    return action.target is not None and not _is_selector_target(action.target)


def _resolve_target(target: str, elements: list[InteractiveElement]) -> InteractiveElement | None:
    """Find the interactive element a target string refers to, if present."""

    needle = _normalize(_strip_target_prefix(target))
    if not needle:
        return None
    for element in elements:
        name = _normalize(element.name or "")
        if not name:
            continue
        if needle == name or needle in name or name in needle:
            return element
    for element in elements:
        if _normalize(element.ref) == needle:
            return element
    return None


@dataclass
class TokenBreakdown:
    text: int
    image: int
    total: int


@dataclass
class NextActionPrediction:
    predicted: dict[str, Any]
    match: bool
    grounded: bool


@dataclass
class NextActionEval:
    expected_action: dict[str, Any]
    needs_grounding: bool
    baseline: NextActionPrediction
    compact: NextActionPrediction


def _predict_next_action(
    expected: BrowserAction,
    available: list[InteractiveElement],
) -> NextActionPrediction:
    """A deterministic planner: can the next scripted action be grounded?

    Actions without a DOM target (press / scroll / wait / goto) are directly
    executable, so they always "match". Target-bearing actions match only when
    the referenced element is present in the observation the planner can see;
    otherwise the planner is forced into an exploratory fallback and mismatches.
    """

    if not _needs_grounding(expected):
        return NextActionPrediction(
            predicted=expected.model_dump(mode="json", exclude_none=True),
            match=True,
            grounded=True,
        )

    element = _resolve_target(expected.target, available)
    if element is None:
        return NextActionPrediction(
            predicted={"type": "request_full_screenshot", "reason": "target_not_grounded"},
            match=False,
            grounded=False,
        )

    predicted = expected.model_dump(mode="json", exclude_none=True)
    predicted["resolved_ref"] = element.ref
    return NextActionPrediction(predicted=predicted, match=True, grounded=True)


@dataclass
class StepEval:
    step: int
    action: dict[str, Any]
    action_ok: bool
    route_baseline: str
    route_compact: str
    fallback_needed: bool
    visual_changed_pct: float
    tokens_baseline: TokenBreakdown
    tokens_compact: TokenBreakdown
    token_savings_pct: float
    next_action_eval: NextActionEval | None


def _compact_image_tokens(
    run_path: Path,
    observation: CompactObservation,
    after_screenshot: Path,
    config: EvalConfig,
) -> int:
    if observation.fallback == "full_screenshot":
        width, height = _image_size(after_screenshot)
        return estimate_image_tokens(width, height, config)
    if observation.fallback == "crop":
        total = 0
        for crop in observation.crop_paths:
            width, height = _image_size(_resolve_artifact(run_path, crop))
            total += estimate_image_tokens(width, height, config)
        return total
    return 0


def _savings_pct(baseline: int, compact: int) -> float:
    if baseline <= 0:
        return 0.0
    return round((1 - compact / baseline) * 100, 2)


def _evaluate_step(
    run_path: Path,
    step: StepRecord,
    observation: CompactObservation,
    expected_next: BrowserAction | None,
    config: EvalConfig,
) -> StepEval:
    after_state = PageState.model_validate(read_json(run_path / step.after.state))
    after_screenshot = run_path / step.after.screenshot

    baseline_text = estimate_text_tokens(json.dumps(_baseline_payload(after_state)), config)
    width, height = _image_size(after_screenshot)
    baseline_image = estimate_image_tokens(width, height, config)
    baseline_tokens = TokenBreakdown(baseline_text, baseline_image, baseline_text + baseline_image)

    compact_text = estimate_text_tokens(observation.llm_observation, config)
    compact_image = _compact_image_tokens(run_path, observation, after_screenshot, config)
    compact_tokens = TokenBreakdown(compact_text, compact_image, compact_text + compact_image)

    next_action_eval: NextActionEval | None = None
    if expected_next is not None:
        baseline_available = after_state.interactive
        compact_available = observation.interactive[: config.compact_text_interactive_limit]
        next_action_eval = NextActionEval(
            expected_action=expected_next.model_dump(mode="json", exclude_none=True),
            needs_grounding=_needs_grounding(expected_next),
            baseline=_predict_next_action(expected_next, baseline_available),
            compact=_predict_next_action(expected_next, compact_available),
        )

    return StepEval(
        step=step.step,
        action=step.action.model_dump(mode="json", exclude_none=True),
        action_ok=step.result.ok,
        route_baseline=BASELINE_ROUTE,
        route_compact=_ROUTE_BY_FALLBACK.get(observation.fallback, observation.fallback),
        fallback_needed=observation.fallback != "none",
        visual_changed_pct=observation.visual_changed_pct,
        tokens_baseline=baseline_tokens,
        tokens_compact=compact_tokens,
        token_savings_pct=_savings_pct(baseline_tokens.total, compact_tokens.total),
        next_action_eval=next_action_eval,
    )


def _summarize_steps(steps: list[StepEval]) -> dict[str, Any]:
    baseline_total = sum(step.tokens_baseline.total for step in steps)
    compact_total = sum(step.tokens_compact.total for step in steps)

    route_hist: dict[str, int] = {}
    for step in steps:
        route_hist[step.route_compact] = route_hist.get(step.route_compact, 0) + 1

    fallback_steps = sum(1 for step in steps if step.fallback_needed)

    samples = [step.next_action_eval for step in steps if step.next_action_eval is not None]
    grounding_samples = [s for s in samples if s.needs_grounding]
    n_ground = len(grounding_samples)
    baseline_correct = sum(1 for s in grounding_samples if s.baseline.match)
    compact_correct = sum(1 for s in grounding_samples if s.compact.match)
    agreement = sum(1 for s in grounding_samples if s.baseline.match == s.compact.match)

    return {
        "n_steps": len(steps),
        "tokens": {
            "baseline_total": baseline_total,
            "compact_total": compact_total,
            "savings_pct": _savings_pct(baseline_total, compact_total),
            "compression_ratio": round(baseline_total / compact_total, 2)
            if compact_total
            else None,
        },
        "routes_compact": route_hist,
        "fallback": {
            "steps_with_fallback": fallback_steps,
            "fallback_rate": round(fallback_steps / len(steps), 3) if steps else 0.0,
        },
        "next_action": {
            "n_samples": len(samples),
            "n_grounding_samples": n_ground,
            "baseline_accuracy": round(baseline_correct / n_ground, 3) if n_ground else None,
            "compact_accuracy": round(compact_correct / n_ground, 3) if n_ground else None,
            "agreement_rate": round(agreement / n_ground, 3) if n_ground else None,
        },
    }


#: Predictors the next-action grounding step supports. The eval ships with a
#: deterministic heuristic planner only; this list is the extension point for an
#: optional LLM planner without changing the call sites.
SUPPORTED_PREDICTORS = ("heuristic",)


def evaluate_run(
    run_path: Path,
    task: dict[str, Any] | None = None,
    config: EvalConfig | None = None,
    compact_if_missing: bool = True,
    predictor: str = "heuristic",
) -> dict[str, Any]:
    """Evaluate a single recorded run; returns a JSON-serializable report section."""

    if predictor not in SUPPORTED_PREDICTORS:
        raise ValueError(f"unsupported predictor {predictor!r}; choose from {SUPPORTED_PREDICTORS}")

    cfg = config or EvalConfig()
    run_path = Path(run_path)
    steps = read_steps(run_path)
    if not steps:
        raise ValueError(f"no steps found in {run_path}")

    observations_path = run_path / "compact_observations.jsonl"
    if observations_path.exists():
        observations = [
            CompactObservation.model_validate(row)
            for row in (
                json.loads(line)
                for line in observations_path.read_text().splitlines()
                if line.strip()
            )
        ]
    elif compact_if_missing:
        observations = compact_run(run_path)
    else:
        raise ValueError(f"no compact_observations.jsonl in {run_path}")

    obs_by_step = {obs.step: obs for obs in observations}

    expected_actions: list[BrowserAction] = []
    if task and task.get("actions"):
        expected_actions = [BrowserAction.model_validate(action) for action in task["actions"]]

    step_evals: list[StepEval] = []
    for index, step in enumerate(steps):
        observation = obs_by_step.get(step.step)
        if observation is None:
            continue
        # The agent picks action[index] (0-based) *after* seeing this step's
        # result; step index `index` recorded executing action[index].
        expected_next = expected_actions[index + 1] if index + 1 < len(expected_actions) else None
        step_evals.append(_evaluate_step(run_path, step, observation, expected_next, cfg))

    return {
        "task_id": task.get("id") if task else run_path.name,
        "goal": task.get("goal") if task else None,
        "run_path": str(run_path),
        "steps": [_step_to_dict(step) for step in step_evals],
        "summary": _summarize_steps(step_evals),
    }


def _step_to_dict(step: StepEval) -> dict[str, Any]:
    data = asdict(step)
    if step.next_action_eval is None:
        data["next_action_eval"] = None
    return data


def _methodology(config: EvalConfig) -> dict[str, Any]:
    return {
        "baseline": (
            "Full after-state (url, title, all text lines, all interactive "
            "elements) serialized as JSON, plus one screenshot per step."
        ),
        "compact": (
            "BrowserDelta llm_observation text; a screenshot (crop or full) only "
            "when the codec routes to a vision fallback."
        ),
        "text_tokens": f"chars / {config.chars_per_token} (matches codec heuristic)",
        "image_tokens": (
            "OpenAI high-detail tiling: "
            f"{config.image_base_tokens} base + {config.image_tile_tokens} per "
            f"{config.image_tile_px}px tile after scaling to <= {config.image_max_long_px}px "
            f"long / <= {config.image_min_short_px}px short side."
        ),
        "routes": {
            "baseline": BASELINE_ROUTE,
            "compact": _ROUTE_BY_FALLBACK,
        },
        "next_action_match": (
            "A deterministic planner grounds the next scripted action against the "
            "elements visible in each observation. Target-bearing actions match "
            "only if the element survives into the observation; the compact "
            f"strategy sees the first {config.compact_text_interactive_limit} "
            "interactive elements (the ones rendered into llm_observation). "
            "Actions without a DOM target are always executable."
        ),
    }


def run_ab_eval(
    tasks: list[dict[str, Any]],
    runs_root: Path,
    config: EvalConfig | None = None,
) -> dict[str, Any]:
    """Evaluate several tasks and produce the full A/B report."""

    cfg = config or EvalConfig()
    runs_root = Path(runs_root)

    task_reports: list[dict[str, Any]] = []
    for task in tasks:
        run_path = runs_root / task["id"]
        task_reports.append(evaluate_run(run_path, task=task, config=cfg))

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": _methodology(cfg),
        "config": asdict(cfg),
        "tasks": task_reports,
        "overall_summary": _overall_summary(task_reports),
    }


def _overall_summary(task_reports: list[dict[str, Any]]) -> dict[str, Any]:
    baseline_total = sum(report["summary"]["tokens"]["baseline_total"] for report in task_reports)
    compact_total = sum(report["summary"]["tokens"]["compact_total"] for report in task_reports)

    route_hist: dict[str, int] = {}
    fallback_steps = 0
    n_steps = 0
    n_ground = 0
    baseline_correct = 0
    compact_correct = 0
    for report in task_reports:
        n_steps += report["summary"]["n_steps"]
        fallback_steps += report["summary"]["fallback"]["steps_with_fallback"]
        for route, count in report["summary"]["routes_compact"].items():
            route_hist[route] = route_hist.get(route, 0) + count
        for step in report["steps"]:
            sample = step.get("next_action_eval")
            if sample and sample["needs_grounding"]:
                n_ground += 1
                baseline_correct += 1 if sample["baseline"]["match"] else 0
                compact_correct += 1 if sample["compact"]["match"] else 0

    return {
        "n_tasks": len(task_reports),
        "n_steps": n_steps,
        "tokens": {
            "baseline_total": baseline_total,
            "compact_total": compact_total,
            "savings_pct": _savings_pct(baseline_total, compact_total),
            "compression_ratio": round(baseline_total / compact_total, 2)
            if compact_total
            else None,
        },
        "routes_compact": route_hist,
        "fallback": {
            "steps_with_fallback": fallback_steps,
            "fallback_rate": round(fallback_steps / n_steps, 3) if n_steps else 0.0,
        },
        "next_action": {
            "n_grounding_samples": n_ground,
            "baseline_accuracy": round(baseline_correct / n_ground, 3) if n_ground else None,
            "compact_accuracy": round(compact_correct / n_ground, 3) if n_ground else None,
        },
    }


__all__ = [
    "EvalConfig",
    "estimate_image_tokens",
    "estimate_text_tokens",
    "evaluate_run",
    "run_ab_eval",
]
