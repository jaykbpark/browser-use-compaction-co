from browserdelta.compaction.structural_diff import diff_page_state
from browserdelta.schemas import InteractiveElement, PageState


def test_detects_added_element_and_focus_change():
    before = PageState(
        url="https://example.com",
        title="Example",
        interactive=[],
        focused_ref=None,
    )
    after = PageState(
        url="https://example.com",
        title="Example",
        interactive=[InteractiveElement(ref="e1", role="textbox", name="Search")],
        focused_ref="e1",
    )

    changes = diff_page_state(before, after)
    types = {change.type for change in changes}

    assert "focus_changed" in types
    assert "element_added" in types


def test_detects_disabled_change():
    before = PageState(
        url="https://example.com",
        title="Example",
        interactive=[InteractiveElement(ref="e1", role="button", name="Continue", disabled=True)],
    )
    after = PageState(
        url="https://example.com",
        title="Example",
        interactive=[InteractiveElement(ref="e1", role="button", name="Continue", disabled=False)],
    )

    changes = diff_page_state(before, after)

    assert any(change.type == "element_disabled_changed" for change in changes)
