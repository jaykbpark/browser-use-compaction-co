# Team Todos

## Browserbase Team

Goal: produce clean raw browser step data.

### P0: Browser Session

- [ ] Confirm `.env` setup.
- [ ] Run local smoke test with Playwright fallback.
- [ ] Add Browserbase session creation if a direct connect URL is not enough.
- [ ] Confirm `BROWSERBASE_CONNECT_URL` path works.

### P1: Action Executor

- [ ] Improve target resolution in `actions.py`.
- [ ] Support stable refs from `data-browserdelta-ref`.
- [ ] Add action types if needed: select, hover, upload.
- [ ] Keep action result errors explicit.

### P2: State Capture

- [ ] Expand `state.py` only if the compaction team needs more fields.
- [ ] Add true accessibility snapshot if time permits.
- [ ] Capture network failures from Playwright event hooks.
- [ ] Capture console errors from Playwright event hooks.

### P3: Runs

- [ ] Record one complete flow from `tasks/`.
- [ ] Save `steps.jsonl` and all before/after states.
- [ ] Hand the run folder to the compaction team.

## Compaction Team

Goal: turn raw step data into compact observations.

### P0: Structural Diff

- [ ] Improve element identity matching.
- [ ] Detect modal opened/closed.
- [ ] Detect form validation errors.
- [ ] Detect button enabled/disabled.

### P1: Visual Diff

- [ ] Tune image threshold.
- [ ] Split changed regions into useful crops.
- [ ] Ignore tiny cursor/caret/animation noise.
- [ ] Add OCR only if crops are unreadable from DOM.

### P2: Observation Rendering

- [ ] Make `llm_observation` terse and action-useful.
- [ ] Include current interactive refs.
- [ ] Include fallback hint when crop/full screenshot is needed.
- [ ] Estimate baseline vs compact token count.

## Shared

- [ ] Do not change schema without updating `docs/schemas.md`.
- [ ] Keep all generated run artifacts under `runs/`.
- [ ] Prefer command-line proof before frontend polish.
