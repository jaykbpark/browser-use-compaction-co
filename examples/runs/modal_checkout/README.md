# Modal Checkout Fixture

This fixture tests a semantic UI change that the DOM/accessibility state can
explain without image fallback.

Scenario:

1. The user clicks `Checkout` on a cart page.
2. A checkout dialog opens.
3. New form fields appear for email and shipping address.

Expected compact result:

- `route`: `text_only`
- `fallback`: `none`
- `summary`: mentions the dialog/modal or checkout form
- `changed`: includes `modal_opened` and `form_fields_appeared`
