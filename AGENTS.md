# AGENTS.md

## Project Goal

BrowserDelta is a semantic compaction layer for browser agents. It should reduce
the browser context sent to an LLM by replacing repeated full screenshots with
compact observations about what changed after each browser action.

## Current MVP

Build two pieces that meet at a file contract:

1. Browserbase recorder
   - Opens a Browserbase or local Playwright browser.
   - Executes actions.
   - Captures before/after screenshots and page state.
   - Writes raw run files under `runs/<run_id>/`.

2. Compaction codec
   - Reads raw run files.
   - Diffs screenshot and page state.
   - Writes `compact_observations.jsonl`.

Do not make the project depend on a polished demo viewer before the recorder and
codec work from the command line.

## Team Split

Browserbase team owns:

- `backend/browserdelta/browserbase/session.py`
- `backend/browserdelta/browserbase/actions.py`
- `backend/browserdelta/browserbase/state.py`
- `backend/browserdelta/browserbase/recorder.py`
- `scripts/record_demo.py`

Compaction team owns:

- `backend/browserdelta/compaction/image_diff.py`
- `backend/browserdelta/compaction/structural_diff.py`
- `backend/browserdelta/compaction/codec.py`
- `scripts/compact_run.py`

Shared files:

- `backend/browserdelta/schemas.py`
- `backend/browserdelta/storage.py`
- `docs/schemas.md`

Coordinate before changing shared schemas.

## File Contract

Every recorded step must provide:

```json
{
  "step": 1,
  "action": {"type": "click", "target": "Search textbox"},
  "result": {"ok": true},
  "before": {
    "screenshot": "steps/step_001_before.png",
    "state": "steps/step_001_before.json"
  },
  "after": {
    "screenshot": "steps/step_001_after.png",
    "state": "steps/step_001_after.json"
  }
}
```

The compaction output must be JSONL, one row per step:

```json
{
  "step": 1,
  "summary": "Search textbox is now focused.",
  "llm_observation": "Search textbox is focused. Type the query next.",
  "visual_changed_pct": 0.4,
  "fallback": "none"
}
```

## Development Rules

- Use Python for backend and runner code.
- Use Playwright Python for browser control.
- Keep Browserbase credentials in `.env`; never commit secrets.
- Keep generated runs under `runs/`; do not commit run artifacts except small
  hand-written examples under `examples/`.
- Prefer deterministic DOM/accessibility diffs first, image diffs second, OCR or
  vision fallback only when needed.
- Keep modules small and hackathon-readable.
- If you change the run schema, update `docs/schemas.md` in the same change.

## Useful Commands

```bash
pip install -e ".[dev]"
python -m playwright install chromium
uvicorn browserdelta.main:app --reload --app-dir backend
python scripts/record_demo.py --url https://example.com --run-id smoke
python scripts/compact_run.py runs/smoke
pytest
```
