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
  -> next LLM planner step
```

For the MVP, the planner can be a hardcoded action script. The important part is
the observation format.

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

### Compaction Codec

The codec reads a saved run and emits `compact_observations.jsonl`.

It computes:

- structural page changes
- interactive element changes
- focus changes
- URL/title changes
- console/network errors
- screenshot changed percent
- crop or full screenshot fallback decision

### API

FastAPI exposes the saved runs and lets a frontend trigger compaction:

```text
GET  /health
GET  /api/runs
GET  /api/runs/{run_id}
POST /api/runs/{run_id}/compact
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
