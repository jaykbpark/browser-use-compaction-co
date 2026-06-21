from __future__ import annotations

import re
from collections import Counter, defaultdict

from browserdelta.schemas import InteractiveElement, PageState, StructuralChange


ERROR_WORDS = (
    "error",
    "required",
    "invalid",
    "failed",
    "wrong",
    "missing",
    "try again",
    "cannot",
    "couldn't",
)
SUCCESS_WORDS = (
    "success",
    "submitted",
    "confirmed",
    "complete",
    "added",
    "saved",
    "done",
)
MODAL_ROLES = {"dialog", "alertdialog"}
INPUT_ROLES = {"textbox", "combobox", "checkbox", "radio", "searchbox", "spinbutton", "slider"}


def diff_page_state(before: PageState, after: PageState) -> list[StructuralChange]:
    """Return deterministic, model-free changes between two browser state captures."""

    changes: list[StructuralChange] = []
    changes.extend(_diff_page_metadata(before, after))

    before_index = _ElementIndex(before.interactive)
    after_index = _ElementIndex(after.interactive)
    changes.extend(_diff_focus(before, after, before_index, after_index))
    changes.extend(_diff_interactive_elements(before_index, after_index))
    changes.extend(_diff_visible_text(before.text, after.text))
    changes.extend(_diff_errors(before, after))

    changes.extend(_classify_events(changes, before_index, after_index))
    return _dedupe_changes(changes)


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip().lower()


def element_key(element: InteractiveElement) -> str:
    """Build a mostly-stable identity key for an interactive element.

    Browser refs like e1/e2 can shift between captures, so they are intentionally
    not the primary key. Prefer HTML identity and user-visible role/name.
    """

    attrs = element.attributes or {}
    stable_attr = (
        attrs.get("id")
        or attrs.get("data-testid")
        or attrs.get("data-test")
        or attrs.get("name")
        or attrs.get("href")
        or attrs.get("type")
        or ""
    )
    label = normalize_text(element.name)
    role = normalize_text(element.role)

    # BBox helps separate repeated unlabeled controls without making text/value
    # changes look like remove+add events.
    bbox_bucket = ""
    if element.bbox and not label and not stable_attr:
        bbox_bucket = f":{round(element.bbox.x / 25)}:{round(element.bbox.y / 25)}"

    return f"{role}:{label}:{normalize_text(str(stable_attr))}{bbox_bucket}"


def render_element(element: InteractiveElement) -> str:
    label = element.name or element.value or element.ref
    if element.disabled:
        return f"{element.role} {label} disabled"
    return f"{element.role} {label}"


class _ElementIndex:
    def __init__(self, elements: list[InteractiveElement]) -> None:
        self.elements = elements
        self.by_ref = {element.ref: element for element in elements}
        self.by_key: dict[str, InteractiveElement] = {}
        self.duplicates: dict[str, list[InteractiveElement]] = defaultdict(list)

        counts = Counter(element_key(element) for element in elements)
        for element in elements:
            key = element_key(element)
            if counts[key] == 1:
                self.by_key[key] = element
            else:
                self.duplicates[key].append(element)

    def key_for_ref(self, ref: str | None) -> str | None:
        if ref is None:
            return None
        element = self.by_ref.get(ref)
        if element is None:
            return ref
        return element_key(element)

    def element_for_key(self, key: str | None) -> InteractiveElement | None:
        if key is None:
            return None
        return self.by_key.get(key)


def _diff_page_metadata(before: PageState, after: PageState) -> list[StructuralChange]:
    changes: list[StructuralChange] = []
    if before.url != after.url:
        changes.append(
            StructuralChange(
                type="url_changed",
                detail=f"URL changed to {after.url}",
                before=before.url,
                after=after.url,
            )
        )
    if before.title != after.title:
        changes.append(
            StructuralChange(
                type="title_changed",
                detail=f"Page title changed to {after.title}",
                before=before.title,
                after=after.title,
            )
        )
    return changes


def _diff_focus(
    before: PageState,
    after: PageState,
    before_index: _ElementIndex,
    after_index: _ElementIndex,
) -> list[StructuralChange]:
    before_focus_key = before_index.key_for_ref(before.focused_ref)
    after_focus_key = after_index.key_for_ref(after.focused_ref)
    if before_focus_key == after_focus_key:
        return []

    before_focus = before_index.element_for_key(before_focus_key)
    after_focus = after_index.element_for_key(after_focus_key)
    after_label = render_element(after_focus) if after_focus else after.focused_ref
    return [
        StructuralChange(
            type="focus_changed",
            detail=f"Focus changed to {after_label}",
            before=render_element(before_focus) if before_focus else before.focused_ref,
            after=after_label,
        )
    ]


def _diff_interactive_elements(
    before_index: _ElementIndex, after_index: _ElementIndex
) -> list[StructuralChange]:
    changes: list[StructuralChange] = []
    before_keys = set(before_index.by_key)
    after_keys = set(after_index.by_key)

    for key in sorted(after_keys - before_keys):
        element = after_index.by_key[key]
        changes.append(
            StructuralChange(
                type="element_added",
                detail=f"{render_element(element)} appeared",
                after=element.model_dump(mode="json"),
            )
        )

    for key in sorted(before_keys - after_keys):
        element = before_index.by_key[key]
        changes.append(
            StructuralChange(
                type="element_removed",
                detail=f"{render_element(element)} disappeared",
                before=element.model_dump(mode="json"),
            )
        )

    for key in sorted(before_keys & after_keys):
        before = before_index.by_key[key]
        after = after_index.by_key[key]
        changes.extend(_diff_element_fields(before, after))

    return changes


def _diff_element_fields(
    before: InteractiveElement, after: InteractiveElement
) -> list[StructuralChange]:
    changes: list[StructuralChange] = []
    for field in ("value", "disabled", "checked", "selected", "expanded"):
        before_value = getattr(before, field)
        after_value = getattr(after, field)
        if before_value == after_value:
            continue
        label = after.name or before.name or after.ref
        changes.append(
            StructuralChange(
                type=f"element_{field}_changed",
                detail=f"{after.role} {label} {field} changed to {after_value}",
                before=before_value,
                after=after_value,
            )
        )
    return changes


def _diff_visible_text(before_text: list[str], after_text: list[str]) -> list[StructuralChange]:
    before_counter = Counter(normalize_text(line) for line in before_text if normalize_text(line))
    changes: list[StructuralChange] = []

    for line in after_text:
        normalized = normalize_text(line)
        if not normalized:
            continue
        if before_counter[normalized] > 0:
            before_counter[normalized] -= 1
            continue

        change_type = "text_added"
        if any(word in normalized for word in ERROR_WORDS):
            change_type = "validation_error"
        elif any(word in normalized for word in SUCCESS_WORDS):
            change_type = "success_message"

        changes.append(
            StructuralChange(
                type=change_type,
                detail=f"New text appeared: {line}",
                after=line,
            )
        )

    return changes[:24]


def _diff_errors(before: PageState, after: PageState) -> list[StructuralChange]:
    changes: list[StructuralChange] = []
    for error in after.console_errors:
        if error not in before.console_errors:
            changes.append(StructuralChange(type="console_error", detail=error, after=error))
    for error in after.network_errors:
        if error not in before.network_errors:
            changes.append(StructuralChange(type="network_error", detail=error, after=error))
    return changes


def _classify_events(
    changes: list[StructuralChange],
    before_index: _ElementIndex,
    after_index: _ElementIndex,
) -> list[StructuralChange]:
    events: list[StructuralChange] = []
    added = [change for change in changes if change.type == "element_added"]
    removed = [change for change in changes if change.type == "element_removed"]
    changed = {change.type for change in changes}

    added_elements = [_element_from_change(change, "after") for change in added]
    removed_elements = [_element_from_change(change, "before") for change in removed]
    added_elements = [element for element in added_elements if element is not None]
    removed_elements = [element for element in removed_elements if element is not None]

    if any(normalize_text(element.role) in MODAL_ROLES for element in added_elements):
        events.append(
            StructuralChange(
                type="modal_opened",
                detail="A modal or dialog opened",
                after=[element.model_dump(mode="json") for element in added_elements],
            )
        )

    if any(normalize_text(element.role) in MODAL_ROLES for element in removed_elements):
        events.append(
            StructuralChange(
                type="modal_closed",
                detail="A modal or dialog closed",
                before=[element.model_dump(mode="json") for element in removed_elements],
            )
        )

    added_inputs = [
        element for element in added_elements if normalize_text(element.role) in INPUT_ROLES
    ]
    if len(added_inputs) >= 2:
        names = ", ".join(element.name or element.role for element in added_inputs[:4])
        events.append(
            StructuralChange(
                type="form_fields_appeared",
                detail=f"New form fields appeared: {names}",
                after=[element.model_dump(mode="json") for element in added_inputs],
            )
        )

    if any(change.type == "validation_error" for change in changes):
        events.append(
            StructuralChange(type="form_error", detail="A form or validation error appeared")
        )

    if "url_changed" in changed:
        events.append(StructuralChange(type="navigation", detail="The page navigated"))

    cart_event = _classify_cart_update(changes, added_elements, removed_elements, after_index)
    if cart_event:
        events.append(cart_event)

    return events


def _classify_cart_update(
    changes: list[StructuralChange],
    added_elements: list[InteractiveElement],
    removed_elements: list[InteractiveElement],
    after_index: _ElementIndex,
) -> StructuralChange | None:
    after_text = " ".join(normalize_text(line) for line in _all_after_text(changes))
    added_labels = " ".join(normalize_text(element.name) for element in added_elements)
    removed_labels = " ".join(normalize_text(element.name) for element in removed_elements)
    after_interactive = " ".join(normalize_text(element.name) for element in after_index.elements)

    if (
        ("add to cart" in removed_labels and "remove" in added_labels)
        or "cart count" in after_text
        or re.search(r"\bcart\b", after_text)
        or ("checkout" in after_interactive and "remove" in added_labels)
    ):
        return StructuralChange(type="cart_updated", detail="Cart state changed")
    return None


def _all_after_text(changes: list[StructuralChange]) -> list[str]:
    values: list[str] = []
    for change in changes:
        if isinstance(change.after, str):
            values.append(change.after)
    return values


def _element_from_change(change: StructuralChange, side: str) -> InteractiveElement | None:
    payload = getattr(change, side)
    if not isinstance(payload, dict):
        return None
    try:
        return InteractiveElement.model_validate(payload)
    except Exception:  # noqa: BLE001 - malformed evidence should not block diffing
        return None


def _dedupe_changes(changes: list[StructuralChange]) -> list[StructuralChange]:
    seen: set[tuple[str, str]] = set()
    output: list[StructuralChange] = []
    for change in changes:
        key = (change.type, change.detail)
        if key in seen:
            continue
        seen.add(key)
        output.append(change)
    return sorted(output, key=_change_priority)


def _change_priority(change: StructuralChange) -> tuple[int, str]:
    order = {
        "form_error": 0,
        "validation_error": 1,
        "console_error": 2,
        "network_error": 2,
        "modal_opened": 3,
        "modal_closed": 3,
        "navigation": 4,
        "url_changed": 5,
        "focus_changed": 6,
        "cart_updated": 7,
        "form_fields_appeared": 8,
        "success_message": 9,
        "element_disabled_changed": 10,
        "element_value_changed": 11,
        "element_added": 12,
        "element_removed": 13,
        "text_added": 14,
    }
    return (order.get(change.type, 99), change.detail)
