from browserdelta.compaction.structural_diff import diff_page_state, element_key, normalize_text
from browserdelta.schemas import InteractiveElement, PageState


def test_normalizes_text_and_stable_element_key_ignores_ref():
    first = InteractiveElement(ref="e1", role="button", name="  Add   to cart  ")
    second = InteractiveElement(ref="e9", role="button", name="add to cart")

    assert normalize_text("  Add   to cart  ") == "add to cart"
    assert element_key(first) == element_key(second)


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


def test_does_not_report_remove_add_when_ref_changes_only():
    before = PageState(
        url="https://example.com",
        title="Example",
        interactive=[InteractiveElement(ref="e1", role="button", name="Continue", disabled=True)],
        focused_ref="e1",
    )
    after = PageState(
        url="https://example.com",
        title="Example",
        interactive=[InteractiveElement(ref="e99", role="button", name="Continue", disabled=False)],
        focused_ref="e99",
    )

    changes = diff_page_state(before, after)
    types = {change.type for change in changes}

    assert "element_added" not in types
    assert "element_removed" not in types
    assert "element_disabled_changed" in types


def test_classifies_modal_and_form_fields_opened():
    before = PageState(url="https://shop.test/cart", title="Cart")
    after = PageState(
        url="https://shop.test/cart",
        title="Cart",
        interactive=[
            InteractiveElement(ref="e1", role="dialog", name="Checkout"),
            InteractiveElement(ref="e2", role="textbox", name="Email"),
            InteractiveElement(ref="e3", role="textbox", name="Shipping address"),
            InteractiveElement(ref="e4", role="button", name="Continue", disabled=True),
        ],
    )

    changes = diff_page_state(before, after)
    types = {change.type for change in changes}

    assert "modal_opened" in types
    assert "form_fields_appeared" in types


def test_detects_validation_error_from_new_text():
    before = PageState(url="https://app.test/login", title="Login", text=["Login"])
    after = PageState(
        url="https://app.test/login",
        title="Login",
        text=["Login", "Email is required"],
        interactive=[InteractiveElement(ref="e1", role="textbox", name="Email")],
    )

    changes = diff_page_state(before, after)
    types = {change.type for change in changes}

    assert "validation_error" in types
    assert "form_error" in types
    assert any("Email is required" in change.detail for change in changes)


def test_classifies_cart_update():
    before = PageState(
        url="https://shop.test/products",
        title="Products",
        interactive=[InteractiveElement(ref="e1", role="button", name="Add to cart")],
        text=["Products", "Cart"],
    )
    after = PageState(
        url="https://shop.test/products",
        title="Products",
        interactive=[
            InteractiveElement(ref="e1", role="button", name="Remove"),
            InteractiveElement(ref="e2", role="link", name="Checkout"),
        ],
        text=["Products", "Cart", "1"],
    )

    changes = diff_page_state(before, after)

    assert any(change.type == "cart_updated" for change in changes)
