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
```

## What We Are Building

The MVP has two independent workstreams:

1. Browserbase recorder: runs browser actions and saves raw step evidence.
2. Compaction codec: converts raw step evidence into compact LLM observations.

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
can work from those files without needing Browserbase credentials.

## Tech Stack

- Backend: Python, FastAPI
- Browser runtime: Browserbase, with local Playwright fallback
- Browser control: Playwright Python
- Screenshot diff: Pillow, NumPy, optional OpenCV
- Data format: JSON / JSONL run logs
- Viewer: Vite, React, TypeScript

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
cp .env.example .env
```

Run the API:

```bash
uvicorn browserdelta.main:app --reload --app-dir backend
```

Record a local demo run:

```bash
python scripts/record_demo.py --url https://example.com --run-id smoke
```

Compact a run:

```bash
python scripts/compact_run.py runs/smoke
```

Run tests:

```bash
pytest
```

## A/B Eval

Compare the naive baseline observation (full page state + a screenshot every
step) against BrowserDelta compact observations and write `eval_report.json`:

```bash
# Evaluate runs already recorded under runs/
python scripts/eval_ab.py --tasks tasks/docs_search.json tasks/shopping.json

# Or record the runs live first (needs Playwright + network)
python scripts/eval_ab.py --tasks tasks/docs_search.json tasks/shopping.json --record
```

For each step the report records: baseline vs compact **token estimate**, the
**route used** (`structural` / `image_crop` / `vision_full` vs the baseline
`full_state+screenshot`), whether the **predicted next action matches** the
expected scripted action (element-grounding accuracy), and whether a **fallback
was needed**. Per-task and overall summaries roll these up. The methodology
(modeled on WebArena / Mind2Web style step accuracy + cost) is documented inline
in the report.

## Browserbase Setup

For local development, BrowserDelta falls back to a local Playwright Chromium
browser when no Browserbase connection URL is configured.

To use Browserbase, set:

```bash
BROWSERBASE_CONNECT_URL="wss://..."
```

The Browserbase team can replace `backend/browserdelta/browserbase/session.py`
with first-class session creation once the event credentials are available.

## Project Shape

```text
backend/browserdelta/
  api/              FastAPI routes
  browserbase/      browser connection, action execution, state capture
  compaction/       screenshot + structural diffs and compact observations
  schemas.py        shared Pydantic models
  storage.py        run folder IO

scripts/
  record_demo.py    record a raw browser run
  compact_run.py    compact a saved raw run

viewer/
  Vite/React shell for viewing runs

docs/
  architecture.md
  team-todos.md
  schemas.md
```

## Core Claim

BrowserDelta is not just screenshot compression. It compresses browser state
transitions: the action, visual diff, DOM/accessibility changes, errors, and
fallback evidence needed for the next agent step.
