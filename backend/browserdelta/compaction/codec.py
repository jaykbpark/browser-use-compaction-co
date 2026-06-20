from __future__ import annotations

from pathlib import Path

from browserdelta.compaction.image_diff import diff_images, write_crops
from browserdelta.compaction.structural_diff import diff_page_state
from browserdelta.schemas import CompactObservation, PageState, StepRecord
from browserdelta.storage import read_json, read_steps, write_compact_observations


def compact_run(path: Path) -> list[CompactObservation]:
    observations = [compact_step(path, step) for step in read_steps(path)]
    write_compact_observations(path, observations)
    return observations


def compact_step(run_path: Path, step: StepRecord) -> CompactObservation:
    before_state = PageState.model_validate(read_json(run_path / step.before.state))
    after_state = PageState.model_validate(read_json(run_path / step.after.state))
    visual = diff_images(run_path / step.before.screenshot, run_path / step.after.screenshot)

    fallback = "none"
    crop_paths: list[str] = []
    if visual.changed_pct > 35:
        fallback = "full_screenshot"
    elif visual.changed_pct > 2 and visual.regions:
        fallback = "crop"
        crop_dir = run_path / "crops" / f"step_{step.step:03d}"
        visual.regions = write_crops(run_path / step.after.screenshot, visual.regions, crop_dir)
        crop_paths = [region.crop_path for region in visual.regions if region.crop_path]

    structural_changes = diff_page_state(before_state, after_state)
    summary = _summarize(step, structural_changes, visual.changed_pct)
    llm_observation = _render_llm_observation(summary, structural_changes, after_state, step.result.ok)

    return CompactObservation(
        step=step.step,
        action_result="success" if step.result.ok else "failed",
        summary=summary,
        changed=structural_changes[:24],
        interactive=after_state.interactive[:30],
        visual_changed_pct=visual.changed_pct,
        fallback=fallback,  # type: ignore[arg-type]
        llm_observation=llm_observation,
        crop_paths=crop_paths,
        full_screenshot_path=step.after.screenshot if fallback == "full_screenshot" else None,
        tokens_estimate=_estimate_tokens(llm_observation),
    )


def _summarize(step: StepRecord, changes: list, visual_changed_pct: float) -> str:
    if not step.result.ok:
        return f"{step.action.type} failed: {step.result.error or step.result.message}"
    if changes:
        return changes[0].detail
    if visual_changed_pct > 0:
        return f"Visual state changed by {visual_changed_pct}%."
    return f"{step.action.type} completed with no obvious state change."


def _render_llm_observation(summary: str, changes: list, after: PageState, ok: bool) -> str:
    lines = [summary]
    if not ok:
        lines.append("The last browser action failed. Choose a recovery action.")

    important = [change.detail for change in changes[:8]]
    if important:
        lines.append("Changes: " + "; ".join(important))

    interactives = [
        f"{item.role}: {item.name or item.ref}{' disabled' if item.disabled else ''}"
        for item in after.interactive[:12]
    ]
    if interactives:
        lines.append("Current interactive elements: " + "; ".join(interactives))

    if after.console_errors:
        lines.append("Console errors: " + "; ".join(after.console_errors[-3:]))
    if after.network_errors:
        lines.append("Network errors: " + "; ".join(after.network_errors[-3:]))

    return "\n".join(lines)


def _estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))
