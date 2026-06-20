from __future__ import annotations

from browserdelta.schemas import InteractiveElement, PageState, StructuralChange


def diff_page_state(before: PageState, after: PageState) -> list[StructuralChange]:
    changes: list[StructuralChange] = []

    if before.url != after.url:
        changes.append(
            StructuralChange(type="url_changed", detail=f"URL changed to {after.url}", before=before.url, after=after.url)
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

    if before.focused_ref != after.focused_ref:
        before_focus = _element_name(before.interactive, before.focused_ref)
        after_focus = _element_name(after.interactive, after.focused_ref)
        changes.append(
            StructuralChange(
                type="focus_changed",
                detail=f"Focus changed to {after_focus or after.focused_ref}",
                before=before_focus,
                after=after_focus,
            )
        )

    before_elements = {_element_key(element): element for element in before.interactive}
    after_elements = {_element_key(element): element for element in after.interactive}

    for key, element in after_elements.items():
        if key not in before_elements:
            changes.append(
                StructuralChange(
                    type="element_added",
                    detail=f"{element.role} appeared: {element.name or element.ref}",
                    after=element.model_dump(mode="json"),
                )
            )

    for key, element in before_elements.items():
        if key not in after_elements:
            changes.append(
                StructuralChange(
                    type="element_removed",
                    detail=f"{element.role} disappeared: {element.name or element.ref}",
                    before=element.model_dump(mode="json"),
                )
            )

    for key in before_elements.keys() & after_elements.keys():
        before_element = before_elements[key]
        after_element = after_elements[key]
        for field in ("value", "disabled", "checked", "selected", "expanded"):
            before_value = getattr(before_element, field)
            after_value = getattr(after_element, field)
            if before_value != after_value:
                changes.append(
                    StructuralChange(
                        type=f"element_{field}_changed",
                        detail=(
                            f"{after_element.role} {after_element.name or after_element.ref} "
                            f"{field} changed to {after_value}"
                        ),
                        before=before_value,
                        after=after_value,
                    )
                )

    for error in after.console_errors:
        if error not in before.console_errors:
            changes.append(StructuralChange(type="console_error", detail=error, after=error))

    for error in after.network_errors:
        if error not in before.network_errors:
            changes.append(StructuralChange(type="network_error", detail=error, after=error))

    return changes


def _element_key(element: InteractiveElement) -> str:
    return f"{element.role}:{element.name}:{element.attributes.get('id') or ''}"


def _element_name(elements: list[InteractiveElement], ref: str | None) -> str | None:
    if ref is None:
        return None
    for element in elements:
        if element.ref == ref:
            return element.name or element.ref
    return ref
