# Architecture

BrowserDelta has one narrow job: turn raw browser state transitions into compact
observations for an LLM-driven browser agent.

```text
User task
  -> LLM planner
  -> browser action
  -> Browserbase or local Playwright browser
  -> raw before/after state
  -> BrowserDelta codec
  -> compact observation
  -> replay evaluator
  -> next LLM planner step
```

For the MVP, the planner can be a hardcoded action script. The important part is
the observation format.

The deterministic local proof is:

```bash
python scripts/record_demo.py --task tasks/local_checkout.json --run-id local_checkout --headless --compact --runtime local
```

It uses local Playwright against `demo_pages/local_checkout.html`, then writes and
compacts the same run-folder shape that Browserbase will produce.

## Components

### Browserbase Recorder

The recorder runs a browser and writes raw step evidence.

It captures:

- screenshot
- URL and title
- visible text lines
- visible interactive elements
- focused element
- console errors
- network errors

It writes data under:

```text
runs/<run_id>/
  run.json
  steps.jsonl
  steps/
```

This run folder is the boundary between teams: recorder writes it, compaction
reads it, and `tests/test_run_contract.py` verifies that the boundary still
holds.

### Compaction Codec

The codec reads a saved run and emits `compact_observations.jsonl`.

It computes:

- structural page changes
- interactive element changes
- focus changes
- URL/title changes
- console/network errors
- screenshot changed percent after noise filtering
- SSIM and perceptual hash distance for screenshot-level change detection
- connected visual changed regions and crop boxes
- DOM/visual alignment between changed regions and captured element boxes
- optional OCR text on changed crops when local OCR is available
- crop, text-only, or full screenshot fallback decision

### Replay Evaluator

The evaluator reads `steps.jsonl` and `compact_observations.jsonl`, then asks a
replay agent what the next browser action should be from the compact
observation. It compares that prediction to the next recorded action and writes
`eval_report.json`.

It can also run the same replay against two baselines:

- `full_state`: rendered after-action page state plus the full screenshot
  pointer.
- `vision_full_state`: rendered after-action page state plus the full screenshot
  attached to the Responses API call as an `input_image`.

Token estimates include the raw page state plus screenshot evidence. The default
comparison command uses `vision_full_state` and writes:

- `eval_report.json` for compact context.
- `eval_vision_full_state_report.json` for the vision full-state baseline.
- `eval_comparison.json` for machine-readable compact-vs-baseline metrics.
- `eval_summary.md` for the demo-friendly explanation and step table.

There are two predictor modes:

- `heuristic`: deterministic, free, and useful for smoke tests.
- `llm`: calls the OpenAI Responses API using `OPENAI_API_KEY`, returning a
  strict JSON browser action prediction from compact context, full state, or
  full state plus screenshot image depending on `context_mode`.

### API

FastAPI exposes the saved runs and lets a frontend trigger compaction:

```text
GET  /health
GET  /api/runs
GET  /api/runs/{run_id}
POST /api/runs/{run_id}/compact
POST /api/runs/{run_id}/eval
POST /api/runs/{run_id}/eval?predictor=llm
POST /api/runs/{run_id}/eval?context_mode=full_state
POST /api/runs/{run_id}/eval?context_mode=vision_full_state
POST /api/runs/{run_id}/eval/compare?predictor=llm
POST /api/runs/{run_id}/eval/compare?predictor=llm&baseline_context_mode=full_state
```

## Browserbase Fit

Browserbase is the browser runtime, not the inference layer.

BrowserDelta sits above it:

```text
Browserbase session
  -> Playwright action
  -> BrowserDelta state capture
  -> BrowserDelta compact observation
```

If Browserbase credentials are not available, the same recorder runs locally
with Playwright Chromium.
