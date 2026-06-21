# Login Error Fixture

This is the canonical smoke fixture for the Browserbase-to-compaction contract.
It represents one browser action:

1. The user clicks `Sign in` on an empty login form.
2. The page shows `Email is required`.
3. BrowserDelta should compact the step to a text-only observation with high
   confidence because the DOM/accessibility state explains the visual change.

Run it with:

```bash
python scripts/compact_run.py examples/runs/login_error
```

Expected shape:

- `route`: `text_only`
- `fallback`: `none`
- `summary`: includes `Email is required`
- `reduction_pct`: positive
