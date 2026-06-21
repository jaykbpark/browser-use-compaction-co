from __future__ import annotations

import shutil
from pathlib import Path

from browserdelta.compaction.image_diff import (
    align_regions_to_elements,
    annotate_regions_with_ocr,
    diff_images,
    write_crops,
)
from browserdelta.compaction.metrics import (
    estimate_image_tokens,
    estimate_raw_baseline_tokens,
    estimate_text_tokens,
    reduction_pct,
)
from browserdelta.compaction.renderer import render_llm_observation, summarize_observation
from browserdelta.compaction.router import route_observation
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
    visual = align_regions_to_elements(visual, after_state.interactive)

    structural_changes = diff_page_state(before_state, after_state)
    decision = route_observation(structural_changes, visual, step.result.ok)

    crop_paths: list[str] = []
    crop_dir = run_path / "crops" / f"step_{step.step:03d}"
    if decision.fallback == "crop":
        visual.regions = write_crops(run_path / step.after.screenshot, visual.regions, crop_dir)
        visual.regions = annotate_regions_with_ocr(visual.regions)
        crop_paths = [
            _run_relative_path(run_path, region.crop_path)
            for region in visual.regions
            if region.crop_path
        ]
    elif crop_dir.exists():
        shutil.rmtree(crop_dir)

    summary = summarize_observation(
        step,
        structural_changes,
        visual.changed_pct,
        visual_regions=visual.regions,
    )
    llm_observation = render_llm_observation(
        summary=summary,
        changes=structural_changes,
        after=after_state,
        ok=step.result.ok,
        decision=decision,
        crop_paths=crop_paths,
        visual_regions=visual.regions,
    )

    compact_tokens = estimate_text_tokens(llm_observation)
    compact_tokens += sum(
        estimate_image_tokens(_resolve_run_path(run_path, path)) for path in crop_paths
    )
    if decision.fallback == "full_screenshot":
        compact_tokens += estimate_image_tokens(run_path / step.after.screenshot)

    baseline_tokens = estimate_raw_baseline_tokens(after_state, run_path / step.after.screenshot)

    return CompactObservation(
        step=step.step,
        action_result="success" if step.result.ok else "failed",
        summary=summary,
        changed=structural_changes[:24],
        interactive=after_state.interactive[:30],
        visual_changed_pct=visual.changed_pct,
        visual_raw_changed_pct=visual.raw_changed_pct,
        visual_ssim_score=visual.ssim_score,
        visual_phash_distance=visual.perceptual_hash_distance,
        fallback=decision.fallback,
        route=decision.route,
        route_reason=decision.reason,
        confidence=decision.confidence,
        llm_observation=llm_observation,
        crop_paths=crop_paths,
        full_screenshot_path=step.after.screenshot
        if decision.fallback == "full_screenshot"
        else None,
        visual_regions=visual.regions[:8],
        tokens_estimate=compact_tokens,
        baseline_tokens_estimate=baseline_tokens,
        reduction_pct=reduction_pct(baseline_tokens, compact_tokens),
    )


def _run_relative_path(run_path: Path, path: str) -> str:
    crop_path = Path(path)
    try:
        return crop_path.relative_to(run_path).as_posix()
    except ValueError:
        pass
    if crop_path.is_absolute():
        return crop_path.as_posix()
    return crop_path.as_posix()


def _resolve_run_path(run_path: Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return run_path / candidate
