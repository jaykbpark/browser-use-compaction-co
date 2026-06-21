# AGENTS.md

## Project Goal

BrowserDelta is a semantic compaction layer for browser agents. It should reduce
the browser context sent to an LLM by replacing repeated full screenshots with
compact observations about what changed after each browser action.

## Current MVP

Build three pieces that meet at a file contract:

1. Browserbase recorder
   - Opens a Browserbase or local Playwright browser.
   - Executes actions.
   - Captures before/after screenshots and page state.
   - Writes raw run files under `runs/<run_id>/`.

2. Compaction codec
   - Reads raw run files.
   - Diffs screenshot and page state.
   - Writes `compact_observations.jsonl`.

3. Replay evaluator
   - Reads `steps.jsonl` and `compact_observations.jsonl`.
   - Predicts the next browser action from compact context only.
   - Writes `eval_report.json` with next-action parity and token savings.
   - Can compare compact context against a full captured-state baseline or a
     vision full-state baseline that attaches the after screenshot to the LLM,
     writing `eval_full_state_report.json`,
     `eval_vision_full_state_report.json`, `eval_comparison.json`, and
     `eval_summary.md`.

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
- `backend/browserdelta/compaction/router.py`
- `backend/browserdelta/compaction/renderer.py`
- `backend/browserdelta/compaction/metrics.py`
- `scripts/compact_run.py`
- `tests/test_codec.py`
- `tests/test_image_diff.py`
- `tests/test_metrics.py`
- `tests/test_router.py`
- `tests/test_structural_diff.py`

Shared files:

- `backend/browserdelta/schemas.py`
- `backend/browserdelta/storage.py`
- `backend/browserdelta/eval/**`
- `docs/schemas.md`
- `examples/runs/**`
- `scripts/eval_run.py`
- `tests/test_eval_runner.py`
- `tests/test_example_fixture.py`
- `tests/test_run_contract.py`

Coordinate before changing shared schemas.

Parallel work rule: Browserbase can change recorder/session/action/state code
while compaction changes codec/diff/rendering code, as long as both sides keep
the run folder contract valid. Do not have two teams develop against the same
mutable `runs/<run_id>` folder; copy a fixture or use separate run IDs.

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
  "visual_regions": [],
  "fallback": "none",
  "crop_paths": []
}
```

All `StatePointer` paths and `CompactObservation.crop_paths` are relative to the
run folder. Resolve them as `runs/<run_id>/<path>` when reading files.

## Golden Fixtures

- Use `examples/runs/login_error` as the first smoke test for recorder/codec
  compatibility. It is a checked-in raw run fixture with one click action that
  produces an `Email is required` validation error.
- Use `examples/runs/modal_checkout` to verify semantic DOM/accessibility
  changes route to `text_only` when a checkout modal and form fields appear.
- Use `examples/runs/visual_only_change` to verify pixel-only changes route to
  `crop_with_context` when the DOM/accessibility state does not explain a
  canvas-like chart update.
- Use `tasks/local_checkout.json` plus `demo_pages/local_checkout.html` as the
  live local browser proof. It records validation, input value, visual-only crop
  fallback, and modal-open transitions without external credentials.
- Use `tasks/search_filter.json` plus `demo_pages/search_filter.html` as a
  deterministic table/filter benchmark. It records search filtering, a changed
  result table, an add-to-cart state update, reset, and a second filter.
- Use `tasks/visual_canvas_chart.json`, `tasks/visual_progress_toast.json`, and
  `tasks/visual_swatch_picker.json` as visual benchmark tasks for canvas redraws,
  progress/toast changes, and style/state changes.
- Run it with `python scripts/compact_run.py examples/runs/login_error`.
- Run the live proof with
  `python scripts/record_demo.py --task tasks/local_checkout.json --run-id local_checkout --headless --compact --runtime local`.
- Run the Browserbase-backed proof with
  `python scripts/record_demo.py --task tasks/local_checkout.json --run-id browserbase_checkout --headless --compact --runtime browserbase`.
- Score a compacted proof run with
  `python scripts/eval_run.py runs/local_checkout`.
- Score a compacted proof run with a real OpenAI model using
  `python scripts/eval_run.py runs/local_checkout --predictor llm`.
- Compare compact replay against the vision full-state baseline with
  `python scripts/eval_run.py runs/local_checkout --predictor llm --compare`.
- Compare against the cheaper text-only full-state baseline with
  `python scripts/eval_run.py runs/local_checkout --predictor llm --compare --baseline-context full_state`.
- Batch that comparison over the local, Browserbase, and visual benchmark runs
  with `python scripts/eval_suite.py --predictor llm --compare runs/local_checkout runs/browserbase_checkout runs/visual_canvas_chart runs/visual_progress_toast runs/visual_swatch_picker`.
- BrowserGym/MiniWoB support is an optional adapter, not a core dependency.
  Current BrowserGym packages pin an older Playwright, so use an isolated
  BrowserGym environment for `scripts/record_browsergym.py`. Do not add
  BrowserGym to the default project dependencies unless the Playwright conflict
  is resolved.
- The login and modal fixtures should produce `route=text_only`,
  `fallback=none`, and a positive `reduction_pct`.
- The visual-only fixture should produce `route=crop_with_context`,
  `fallback=crop`, and at least one generated crop path.
- Visual benchmark tasks should continue to record and compact locally through
  `tests/test_visual_benchmark_tasks.py`; do not require OpenAI calls there.
- External benchmark tests should mock BrowserGym and must not require a live
  MiniWoB server in normal CI.
- Keep fixture raw inputs stable unless the shared schema changes. If the schema
  changes, update the fixture, `docs/schemas.md`, and tests in the same change.
- Do not commit generated `compact_observations.jsonl` from local smoke runs
  unless it is intentionally being added as an expected-output artifact.
- Run `pytest tests/test_run_contract.py` after changing recorder output,
  shared schemas, or compaction path handling.

## Development Rules

- Use Python for backend and runner code.
- Use Playwright Python for browser control.
- Keep Browserbase credentials in `.env`; never commit secrets.
- Keep OpenAI credentials in `.env`; never commit secrets.
- Prefer `BROWSERBASE_API_KEY` for Browserbase sessions. `BROWSERBASE_PROJECT_ID`
  is optional; use `BROWSERBASE_CONNECT_URL` only when a raw CDP URL is provided.
- Use `OPENAI_API_KEY` and optional `OPENAI_MODEL` for model-backed replay eval.
  Keep `heuristic` eval as the default free smoke test.
- Keep generated runs under `runs/`; do not commit run artifacts except small
  hand-written examples under `examples/`.
- Prefer deterministic DOM/accessibility diffs first, image diffs second, OCR or
  vision fallback only when needed.
- For visual compaction changes, preserve the hybrid CV contract: noise-filtered
  pixel diff, connected regions, DOM-box alignment, SSIM/pHash metrics, optional
  OCR, and a router decision that chooses text, crop, or full screenshot.
- Keep modules small and hackathon-readable.
- If you change the run schema, update `docs/schemas.md` in the same change.

## Useful Commands

```bash
pip install -e ".[dev]"
python -m playwright install chromium
uvicorn browserdelta.main:app --reload --app-dir backend
python scripts/record_demo.py --url https://example.com --run-id smoke
python scripts/record_demo.py --task tasks/local_checkout.json --run-id local_checkout --headless --compact --runtime local
python scripts/eval_run.py runs/local_checkout
python scripts/eval_run.py runs/local_checkout --predictor llm
python scripts/eval_run.py runs/local_checkout --predictor llm --compare
python scripts/eval_run.py runs/local_checkout --predictor llm --context-mode vision_full_state
python scripts/eval_suite.py --predictor llm --compare runs/local_checkout runs/browserbase_checkout runs/visual_canvas_chart runs/visual_progress_toast runs/visual_swatch_picker
python scripts/compact_run.py runs/smoke
python scripts/compact_run.py examples/runs/login_error
python scripts/compact_run.py examples/runs/modal_checkout
python scripts/compact_run.py examples/runs/visual_only_change
pytest
```
