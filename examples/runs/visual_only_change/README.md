# Visual Only Change Fixture

This fixture tests an escalation path where the screenshot changes but the
captured DOM/accessibility state does not explain the change.

Scenario:

1. The user clicks `Refresh chart`.
2. A canvas-like chart area updates visually.
3. The page state remains effectively the same.

Expected compact result:

- `route`: `crop_with_context`
- `fallback`: `crop`
- `crop_paths`: at least one crop for the changed visual region
- `route_reason`: says visual change was detected without strong DOM evidence
