# BrowserDelta

BrowserDelta is a semantic compaction layer for Browserbase-style browser agents.
Instead of sending an LLM a full screenshot after every browser action, it records
the browser state before and after each step, diffs the states, and emits a small
observation that says only what changed.

```text
Browserbase session
  -> browser action
  -> raw before/after state
  -> BrowserDelta codec
  -> compact observation for the LLM
  -> replay eval for next-action parity
```

## What We Are Building

The MVP has three independent workstreams:

1. Browserbase recorder: runs browser actions and saves raw step evidence.
2. Compaction codec: converts raw step evidence into compact LLM observations.
3. Replay evaluator: checks whether compact observations preserve the next action.

The contract between the two teams is the run folder:

```text
runs/<run_id>/
  run.json
  steps.jsonl
  steps/
    step_001_before.json
    step_001_after.json
    step_001_before.png
    step_001_after.png
```

Each `steps.jsonl` row points to the raw before/after files. The compaction team
can work from those files without needing Browserbase credentials. Pointer paths
and generated crop paths are run-relative, so a copied run folder should still
compact correctly.

## Tech Stack

- Backend: Python, FastAPI
- Browser runtime: Browserbase, with local Playwright fallback
- Browser control: Playwright Python
- Screenshot diff: Pillow, NumPy, optional OpenCV
- Visual delta: connected components, DOM-box alignment, SSIM, perceptual hash,
  optional OCR
- Data format: JSON / JSONL run logs
- Viewer: Vite, React, TypeScript

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
npm --prefix viewer install
cp .env.example .env
```

Generate screenshot-rich local runs for the dashboard:

```bash
browserdelta demo
```

Start the API:

```bash
browserdelta serve
```

In another terminal, start the viewer:

```bash
npm --prefix viewer run dev -- --host 127.0.0.1 --port 5174
```

Open `http://127.0.0.1:5174/#dashboard`.

The CLI command a browser agent should call is:

```bash
browserdelta observe local_checkout --step 3 --format json
```

It returns the compact observation, token estimates, and any crop screenshot
paths for the selected browser step.

Lower-level scripts are still available for debugging:

```bash
python scripts/record_demo.py --url https://example.com --run-id smoke
```

Run the deterministic local BrowserDelta proof:

```bash
python scripts/record_demo.py --task tasks/local_checkout.json --run-id local_checkout --headless --compact --runtime local
```

This opens `demo_pages/local_checkout.html`, records four real browser actions,
and immediately compacts the run. Expected behavior:

- step 1: validation error -> `text_only`
- step 2: typed field value -> `text_only`
- step 3: canvas-only chart update -> `crop_with_context`
- step 4: checkout modal opens -> `text_only`

Record the deterministic table/filter viewer demo:

```bash
python scripts/record_demo.py --task tasks/search_filter.json --run-id search_filter --headless --compact --runtime local
```

This produces four screenshot-rich steps for the viewer: filter the fruit table,
add Strawberry to the cart, reset the table, and filter for Cherry.

Compact a run:

```bash
python scripts/compact_run.py runs/smoke
```

Evaluate whether compact observations preserve the next action:

```bash
python scripts/eval_run.py runs/local_checkout
```

The replay evaluator writes `eval_report.json` and reports next-action parity
for every transition that has a following recorded action.

Run the same replay eval with a real LLM predictor:

```bash
python scripts/eval_run.py runs/local_checkout --predictor llm
```

This uses `OPENAI_API_KEY` and `OPENAI_MODEL` from `.env`. The default
`heuristic` predictor is still useful for free, deterministic smoke tests; the
`llm` predictor is the demo proof that a model can choose the same next actions
from compact context only.

Compare compact context against a real vision full-state baseline:

```bash
python scripts/eval_run.py runs/local_checkout --predictor llm --compare
```

This writes:

- `eval_report.json`: compact-only replay report.
- `eval_vision_full_state_report.json`: baseline replay report that sends the
  full captured page state plus the after-action screenshot as an `input_image`.
- `eval_comparison.json`: machine-readable compact-vs-baseline comparison.
- `eval_summary.md`: human-readable result for demos.

The comparison answers the core question directly: did compact context preserve
the next browser action, and how many estimated tokens did it save versus sending
the full captured state plus screenshot evidence?

For a cheaper text-only baseline that does not attach screenshot bytes, run:

```bash
python scripts/eval_run.py runs/local_checkout --predictor llm --compare --baseline-context full_state
```

Batch replay eval over multiple runs:

```bash
python scripts/eval_suite.py runs/local_checkout runs/browserbase_checkout
python scripts/eval_suite.py --json tasks/local_checkout.json
python scripts/eval_suite.py --predictor llm --compare runs/local_checkout runs/browserbase_checkout
python scripts/eval_suite.py --predictor llm --compare --baseline-context full_state runs/local_checkout runs/browserbase_checkout
```

Task JSON resolves its `id` to `runs/<id>`; suite JSON can also pass a `runs`
list of run folders.

Prepare the screenshot-heavy local viewer data without external credentials:

```bash
for task in local_checkout search_filter visual_canvas_chart visual_progress_toast visual_swatch_picker; do
  python scripts/record_demo.py --task "tasks/${task}.json" --run-id "$task" --headless --compact --runtime local
done
python scripts/eval_suite.py --predictor heuristic --compare --baseline-context vision_full_state runs/local_checkout runs/search_filter runs/visual_canvas_chart runs/visual_progress_toast runs/visual_swatch_picker
```

The generated `runs/` folders are intentionally ignored by git, but the viewer
will read them through the API and show full screenshots, compact text, and crop
thumbnails for visual-change steps.

### Arize AX Tracing

BrowserDelta can export replay eval traces to Arize AX. Each comparison becomes
one trace with child spans for the compact run, baseline run, and every scored
browser step. Step spans include route, fallback, visual diff metrics,
expected/predicted actions, pass/fail, token estimates, and token savings.

Install optional tracing dependencies:

```bash
pip install -e ".[observability]"
```

Set credentials in `.env`:

```bash
ARIZE_API_KEY="..."
ARIZE_SPACE_ID="..."
ARIZE_PROJECT_NAME="browserdelta-hackathon"
```

Send a single comparison to Arize:

```bash
python scripts/eval_run.py runs/local_checkout --predictor llm --compare --arize
```

Send a suite comparison:

```bash
python scripts/eval_suite.py --predictor llm --compare --arize runs/local_checkout runs/visual_canvas_chart runs/visual_progress_toast runs/visual_swatch_picker
```

If Arize credentials or optional packages are missing, evals still run normally
and print a tracing-disabled warning.

Run the checked-in smoke fixture:

```bash
python scripts/compact_run.py examples/runs/login_error
```

That fixture should produce a text-only compact observation for an `Email is
required` validation error. Use it first when checking whether recorder output
still matches the compaction contract.

The CLI prints demo-facing metrics per step:

```text
step 1: text_only, 91.34% saved, confidence 0.95 - New text appeared: Email is required
total: 1 step(s), 60 compact tokens vs 693 baseline, 91.34% saved
```

Additional fixtures cover the two main router behaviors:

```bash
python scripts/compact_run.py examples/runs/modal_checkout
python scripts/compact_run.py examples/runs/visual_only_change
```

- `modal_checkout`: checkout dialog and form fields appear, expected
  `route=text_only`.
- `visual_only_change`: canvas-like chart changes without useful DOM evidence,
  expected `route=crop_with_context` with crops under `crops/step_001/`.

Visual benchmark tasks stress CV-heavy browser changes:

```bash
python scripts/record_demo.py --task tasks/visual_canvas_chart.json --run-id visual_canvas_chart --headless --compact --runtime local
python scripts/record_demo.py --task tasks/visual_progress_toast.json --run-id visual_progress_toast --headless --compact --runtime local
python scripts/record_demo.py --task tasks/visual_swatch_picker.json --run-id visual_swatch_picker --headless --compact --runtime local
```

- `visual_canvas_chart`: repeated canvas redraws with no useful DOM text delta.
- `visual_progress_toast`: progress bar visual movement plus a completion toast.
- `visual_swatch_picker`: radio state plus selected swatch styling.
- `search_filter`: table filtering and cart state transitions for the demo
  viewer's screenshot-vs-compact-text comparison.

Run tests:

```bash
pytest
```

Run the shared recorder/codec contract test after changing schemas, recorder
output, or compaction path handling:

```bash
pytest tests/test_run_contract.py
```

## Browserbase Setup

For local development, BrowserDelta falls back to a local Playwright Chromium
browser when no Browserbase connection URL is configured.

To use Browserbase with the normal token flow, set:

```bash
BROWSERBASE_API_KEY="..."
```

`BROWSERBASE_PROJECT_ID` is optional; Browserbase can infer the project from the
API key. If the event gives you a raw CDP URL instead, set:

```bash
BROWSERBASE_CONNECT_URL="wss://..."
```

Then run the same proof command:

```bash
python scripts/record_demo.py --task tasks/local_checkout.json --run-id browserbase_checkout --headless --compact --runtime browserbase
```

For model-backed replay eval, set:

```bash
OPENAI_API_KEY="..."
OPENAI_MODEL="gpt-4.1-mini"
```

Then run:

```bash
python scripts/eval_run.py runs/browserbase_checkout --predictor llm
```

## Project Shape

```text
backend/browserdelta/
  api/              FastAPI routes
  browserbase/      browser connection, action execution, state capture
  compaction/       screenshot + structural diffs and compact observations
  eval/             replay evaluation for next-action parity
  schemas.py        shared Pydantic models
  storage.py        run folder IO

scripts/
  record_demo.py    record a raw browser run
  compact_run.py    compact a saved raw run
  eval_run.py       score compact observations against recorded next actions
  eval_suite.py     batch replay eval across run folders or task files

CLI:
  browserdelta demo       generate screenshot-rich local dashboard runs
  browserdelta observe    emit one compact observation for a CLI agent
  browserdelta serve      run the FastAPI service

tasks/
  local_checkout.json deterministic local proof task
  search_filter.json deterministic table/filter viewer demo
  visual_*.json visual benchmark tasks for CV-heavy state changes

demo_pages/
  local_checkout.html deterministic browser page for recorder/codec proof
  search_filter.html deterministic table/filter viewer page
  visual_*.html self-contained visual benchmark pages

viewer/
  Vite/React shell for viewing runs

docs/
  architecture.md
  team-todos.md
  schemas.md

examples/runs/login_error/
  Checked-in raw run fixture for the codec smoke test
examples/runs/modal_checkout/
  Checked-in fixture for modal/form semantic routing
examples/runs/visual_only_change/
  Checked-in fixture for crop fallback routing
```

## Core Claim

BrowserDelta is not just screenshot compression. It compresses browser state
transitions: the action, visual diff, DOM/accessibility changes, errors, and
fallback evidence needed for the next agent step.

The visual layer is intentionally hybrid: deterministic DOM/accessibility diffs
first, then CV-derived visual regions when page state changes through canvas,
images, progress bars, or styling that the DOM alone does not explain.
