from __future__ import annotations

from browserdelta.schemas import (
    PageState,
    RouteDecision,
    StepRecord,
    StructuralChange,
    VisualRegion,
)


def summarize_observation(
    step: StepRecord,
    changes: list[StructuralChange],
    visual_changed_pct: float,
    visual_regions: list[VisualRegion] | None = None,
) -> str:
    if not step.result.ok:
        return f"{step.action.type} failed: {step.result.error or step.result.message}"

    preferred = _preferred_summary_change(changes)
    if preferred:
        return preferred.detail
    if changes:
        return changes[0].detail
    region = _preferred_visual_region(visual_regions or [])
    if region:
        target = region.element_name or region.element_ref
        if not target:
            return f"Visual state changed by {visual_changed_pct}%."
        return f"{target} visual region changed by {visual_changed_pct}%."
    if visual_changed_pct > 0:
        return f"Visual state changed by {visual_changed_pct}%."
    return f"{step.action.type} completed with no obvious state change."


def render_llm_observation(
    summary: str,
    changes: list[StructuralChange],
    after: PageState,
    ok: bool,
    decision: RouteDecision,
    crop_paths: list[str],
    visual_regions: list[VisualRegion] | None = None,
) -> str:
    lines = [summary]
    if not ok:
        lines.append("The last browser action failed. Choose a recovery action.")

    important = [change.detail for change in changes[:8]]
    if important:
        lines.append("Changes: " + "; ".join(important))

    interactives = [_render_interactive_for_llm(item) for item in after.interactive[:12]]
    if interactives:
        lines.append("Current interactive elements: " + "; ".join(interactives))

    if decision.fallback == "crop" and crop_paths:
        lines.append(f"Visual fallback: {len(crop_paths)} crop(s) attached for changed regions.")
    elif decision.fallback == "full_screenshot":
        lines.append("Visual fallback: full screenshot attached because the page changed heavily.")

    region_lines = [_render_visual_region(region) for region in (visual_regions or [])[:6]]
    if region_lines:
        lines.append("Visual regions: " + "; ".join(region_lines))

    if after.console_errors:
        lines.append("Console errors: " + "; ".join(after.console_errors[-3:]))
    if after.network_errors:
        lines.append("Network errors: " + "; ".join(after.network_errors[-3:]))

    return "\n".join(lines)


def _preferred_summary_change(changes: list[StructuralChange]) -> StructuralChange | None:
    preferred_types = (
        "validation_error",
        "success_message",
        "modal_opened",
        "modal_closed",
        "cart_updated",
        "navigation",
        "focus_changed",
        "form_fields_appeared",
    )
    for change_type in preferred_types:
        for change in changes:
            if change.type == change_type:
                return change
    return None


def _preferred_visual_region(regions: list[VisualRegion]) -> VisualRegion | None:
    if not regions:
        return None
    return sorted(regions, key=lambda region: (-region.overlap_pct, -region.area_pct))[0]


def _render_interactive_for_llm(item) -> str:
    label = item.name or item.value or item.ref
    state_bits = []
    if item.disabled:
        state_bits.append("disabled")
    if item.checked:
        state_bits.append("checked")
    if item.selected:
        state_bits.append("selected")
    suffix = f" ({', '.join(state_bits)})" if state_bits else ""
    return f"{item.ref} {item.role}: {label}{suffix}"


def _render_visual_region(region: VisualRegion) -> str:
    target = region.element_name or region.element_ref or "unmatched page area"
    role = f" {region.element_role}" if region.element_role else ""
    overlap = f", {region.overlap_pct:.0f}% overlap" if region.overlap_pct else ""
    area = f"{region.area_pct:.2f}% area" if region.area_pct else "unknown area"
    ocr = f", OCR: {region.ocr_text}" if region.ocr_text else ""
    return f"{region.kind}{role} near {target} ({area}{overlap}{ocr})"
