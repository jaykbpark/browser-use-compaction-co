from __future__ import annotations

from browserdelta.schemas import (
    InteractiveElement,
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

    lines.extend(render_adaptive_state_context(after))

    interactives = render_interactive_context(after.interactive)
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


def render_adaptive_state_context(after: PageState) -> list[str]:
    lines: list[str] = []
    goal = str((after.metadata or {}).get("goal") or "")

    checklist = _render_checklist_context(after.interactive, goal)
    if checklist:
        lines.append(checklist)

    listbox = _render_listbox_context(after.interactive)
    if listbox:
        lines.append(listbox)

    tabs = _render_tab_context(after)
    if tabs:
        lines.append(tabs)

    return lines


def render_interactive_context(
    elements: list[InteractiveElement],
    *,
    limit: int = 20,
) -> list[str]:
    return [_render_interactive_for_llm(item) for item in _rank_interactives(elements)[:limit]]


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


def _render_checklist_context(elements: list[InteractiveElement], goal: str) -> str:
    checkboxes = [item for item in elements if item.role == "checkbox" and item.name]
    if len(checkboxes) < 2:
        return ""

    goal_normalized = _normalize(goal)
    requested_items = [
        item
        for item in checkboxes
        if not goal_normalized or _normalize(item.name) in goal_normalized
    ]
    selected_items = [item for item in requested_items if item.checked]
    selected_names = [item.name for item in selected_items]
    remaining_items = [item for item in requested_items if not item.checked]
    submit = next(
        (
            item
            for item in elements
            if item.role == "button" and _normalize(item.name) in {"submit", "done", "ok"}
        ),
        None,
    )

    parts = [
        "Checklist progress:",
        f"progress={len(selected_items)}/{len(requested_items)}",
        f"requested={_join_labels([item.name for item in requested_items], limit=16) or 'unknown'}",
        f"selected={_join_labels(selected_names, limit=16) or 'none'}",
        f"remaining={_join_labels([item.name for item in remaining_items], limit=16) or 'none'}",
    ]
    if remaining_items:
        parts.append(
            "remaining_refs="
            + _join_labels(
                [f"{item.ref} {item.name}" for item in remaining_items],
                limit=8,
            )
        )
    if submit:
        parts.append(f"submit={submit.ref} button {submit.name}")
        if _is_near_large_checklist_completion(requested_items, selected_items):
            parts.append(f"submit_ready_ref={submit.ref}")
    return " ".join(parts)


def _render_listbox_context(elements: list[InteractiveElement]) -> str:
    options = [item for item in elements if item.role == "option"]
    if not options:
        return ""
    selected = [item for item in options if item.selected]
    visible = [_render_option(item) for item in options[:16]]
    label_state = (
        "option labels unavailable in accessibility tree"
        if any(not (item.name or item.value) for item in options)
        else "option labels available"
    )
    selected_text = ", ".join(_render_option(item) for item in selected) or "none"
    return (
        "Listbox state: "
        f"{label_state}; visible_options={'; '.join(visible)}; selected={selected_text}"
    )


def _render_tab_context(after: PageState) -> str:
    goal = str((after.metadata or {}).get("goal") or "")
    tabs = [item for item in after.interactive if item.role == "tab"]
    if not tabs:
        return ""
    active = next((item for item in tabs if item.selected), None)
    tab_names = {_normalize(item.name) for item in tabs if item.name}
    panel_text = [
        line
        for line in after.text
        if _normalize(line)
        and _normalize(line) not in tab_names
        and not _normalize(line).endswith("task")
    ]
    links = [
        item
        for item in after.interactive
        if item.role in {"link", "generic", "button"} and item.role != "tab"
    ]
    link_text = "; ".join(_render_interactive_for_llm(item) for item in links[:12])
    target_hint = _render_panel_target_hint(goal, panel_text, links)
    target_hint_text = f"target_hint={target_hint}; " if target_hint else ""
    return (
        "Tab state: "
        f"active={_render_interactive_for_llm(active) if active else 'unknown'}; "
        f"{target_hint_text}"
        f"visible_panel_text={'; '.join(panel_text[-12:]) or 'none'}; "
        f"panel_clickables={link_text or 'none'}"
    )


def _rank_interactives(elements: list[InteractiveElement]) -> list[InteractiveElement]:
    return sorted(elements, key=_interactive_rank)


def _interactive_rank(item: InteractiveElement) -> tuple[int, int, str]:
    role = _normalize(item.role)
    has_label = bool(item.name or item.value)
    if role in {"button", "checkbox", "radio", "option", "tab", "link", "textbox", "combobox"}:
        role_rank = 0
    elif role in {"listbox", "tablist"}:
        role_rank = 1
    elif has_label:
        role_rank = 2
    else:
        role_rank = 4
    if item.checked or item.selected:
        role_rank -= 1
    label_rank = 0 if has_label else 1
    return (role_rank, label_rank, item.ref)


def _render_option(item: InteractiveElement) -> str:
    label = item.name or item.value or "(blank)"
    state = " selected" if item.selected else ""
    return f"{item.ref}:{label}{state}"


def _is_near_large_checklist_completion(
    requested_items: list[InteractiveElement],
    selected_items: list[InteractiveElement],
) -> bool:
    requested_count = len(requested_items)
    if requested_count < 6:
        return requested_count > 0 and len(selected_items) == requested_count
    return len(selected_items) >= requested_count - 3


def _render_panel_target_hint(
    goal: str,
    panel_text: list[str],
    links: list[InteractiveElement],
) -> str:
    targets = _quoted_text(goal)
    if not targets:
        return ""

    blank_clickables = sorted(
        [
            item
            for item in links
            if item.role == "generic" and not (item.name or item.value)
        ],
        key=_spatial_rank,
    )
    if not blank_clickables:
        return ""

    short_text = [
        line
        for line in panel_text
        if 0 < len(_normalize(line).split()) <= 3
    ]
    short_normalized = [_normalize(line) for line in short_text]
    panel_blob = _normalize(" ".join(panel_text))
    hints: list[str] = []
    for target in targets[:3]:
        target_normalized = _normalize(target)
        if not target_normalized:
            continue
        if target_normalized in short_normalized:
            index = short_normalized.index(target_normalized)
            match = blank_clickables[min(index, len(blank_clickables) - 1)]
            hints.append(f'"{target}" visible; likely_click_ref={match.ref}')
        elif target_normalized in panel_blob:
            hints.append(f'"{target}" visible; likely_click_ref={blank_clickables[0].ref}')
    return ", ".join(hints)


def _spatial_rank(item: InteractiveElement) -> tuple[float, float, str]:
    if not item.bbox:
        return (float("inf"), float("inf"), item.ref)
    return (item.bbox.y, item.bbox.x, item.ref)


def _quoted_text(value: str) -> list[str]:
    out: list[str] = []
    start: int | None = None
    quote_char = ""
    for index, char in enumerate(value):
        if char in {"'", '"'} and start is None:
            start = index + 1
            quote_char = char
        elif start is not None and char == quote_char:
            out.append(value[start:index])
            start = None
            quote_char = ""
    return out


def _join_labels(labels: list[str], limit: int) -> str:
    if not labels:
        return ""
    visible = labels[:limit]
    suffix = f", +{len(labels) - limit} more" if len(labels) > limit else ""
    return ", ".join(visible) + suffix


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().lower().split())


def _render_visual_region(region: VisualRegion) -> str:
    target = region.element_name or region.element_ref or "unmatched page area"
    role = f" {region.element_role}" if region.element_role else ""
    overlap = f", {region.overlap_pct:.0f}% overlap" if region.overlap_pct else ""
    area = f"{region.area_pct:.2f}% area" if region.area_pct else "unknown area"
    ocr = f", OCR: {region.ocr_text}" if region.ocr_text else ""
    return f"{region.kind}{role} near {target} ({area}{overlap}{ocr})"
