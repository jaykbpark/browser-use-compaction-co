from __future__ import annotations

from browserdelta.schemas import RouteDecision, StructuralChange, VisualDiff


SEMANTIC_CHANGE_TYPES = {
    "validation_error",
    "form_error",
    "success_message",
    "modal_opened",
    "modal_closed",
    "navigation",
    "url_changed",
    "title_changed",
    "focus_changed",
    "cart_updated",
    "form_fields_appeared",
    "element_value_changed",
    "element_disabled_changed",
    "element_checked_changed",
    "element_selected_changed",
    "element_expanded_changed",
    "console_error",
    "network_error",
}

STRONG_SEMANTIC_CHANGE_TYPES = {
    "validation_error",
    "form_error",
    "success_message",
    "modal_opened",
    "modal_closed",
    "navigation",
    "form_fields_appeared",
    "cart_updated",
}


def route_observation(
    changes: list[StructuralChange],
    visual: VisualDiff,
    action_ok: bool,
) -> RouteDecision:
    """Choose the cheapest observation that should still preserve enough context."""

    if not action_ok:
        return RouteDecision(
            route="text_only",
            fallback="none",
            confidence=0.95,
            reason="Browser action failed; the action error is enough context.",
        )

    semantic_count = sum(1 for change in changes if change.type in SEMANTIC_CHANGE_TYPES)
    semantic_types = {change.type for change in changes}
    has_semantic_signal = semantic_count > 0
    has_strong_semantic_signal = bool(semantic_types & STRONG_SEMANTIC_CHANGE_TYPES)
    has_crops = bool(visual.regions)
    has_aligned_visual = any(region.element_name or region.element_ref for region in visual.regions)
    has_visual_text = any(region.ocr_text for region in visual.regions)
    ssim = visual.ssim_score if visual.ssim_score is not None else 1.0
    phash_distance = visual.perceptual_hash_distance or 0

    if has_strong_semantic_signal:
        confidence = 0.9 + min(semantic_count, 3) * 0.025
        if visual.changed_pct > 50:
            confidence -= 0.06
        return RouteDecision(
            route="text_only",
            fallback="none",
            confidence=_clamp(confidence),
            reason="Strong DOM/accessibility signal explains the visual change.",
        )

    if visual.raw_changed_pct > 0 and visual.changed_pct == 0:
        return RouteDecision(
            route="text_only",
            fallback="none",
            confidence=0.82,
            reason="Only tiny/noisy visual changes were filtered out.",
        )

    if visual.changed_pct >= 35 or (visual.changed_pct >= 20 and ssim < 0.78):
        return RouteDecision(
            route="full_screenshot",
            fallback="full_screenshot",
            confidence=0.55 if has_semantic_signal else 0.35,
            reason="Large visual change; compact text may miss layout or rendered content.",
        )

    if (
        has_crops
        and has_aligned_visual
        and visual.changed_pct > 1
        and semantic_types <= {"focus_changed", "element_added", "element_removed"}
    ):
        return RouteDecision(
            route="crop_with_context",
            fallback="crop",
            confidence=0.74,
            reason="Only weak DOM changes were detected; aligned visual region needs crop context.",
        )

    if has_semantic_signal and visual.changed_pct <= 15:
        confidence = 0.86 + min(semantic_count, 4) * 0.03
        if visual.changed_pct > 8:
            confidence -= (visual.changed_pct - 8) * 0.015
        return RouteDecision(
            route="text_only",
            fallback="none",
            confidence=_clamp(confidence),
            reason="DOM/accessibility changes explain the step.",
        )

    if has_semantic_signal and has_crops:
        confidence = (
            0.72 + (0.05 if has_aligned_visual else 0.0) + (0.04 if has_visual_text else 0.0)
        )
        return RouteDecision(
            route="crop_with_context",
            fallback="crop",
            confidence=_clamp(confidence),
            reason="DOM signal exists, but moderate visual change needs crop context.",
        )

    if not changes and visual.changed_pct <= 1:
        return RouteDecision(
            route="text_only",
            fallback="none",
            confidence=0.82,
            reason="No meaningful DOM or pixel change detected.",
        )

    if has_crops and visual.changed_pct > 1:
        confidence = 0.58
        if has_aligned_visual:
            confidence += 0.12
        if has_visual_text:
            confidence += 0.08
        if phash_distance >= 6:
            confidence += 0.04
        return RouteDecision(
            route="crop_with_context",
            fallback="crop",
            confidence=_clamp(confidence),
            reason=_visual_crop_reason(has_aligned_visual, has_visual_text),
        )

    return RouteDecision(
        route="text_only",
        fallback="none",
        confidence=0.55,
        reason="Only weak state changes were detected.",
    )


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def _visual_crop_reason(has_aligned_visual: bool, has_visual_text: bool) -> str:
    if has_aligned_visual and has_visual_text:
        return "Visual change aligns to a page element and OCR extracted rendered text."
    if has_aligned_visual:
        return "Visual change aligns to a page element, but DOM text did not explain it."
    if has_visual_text:
        return "Visual change includes OCR text without a strong DOM explanation."
    return "Visual change was detected without a strong DOM explanation."
