# Team Todos

## Browserbase Team

Goal: produce clean raw browser step data.

### P0: Browser Session

- [ ] Confirm `.env` setup.
- [x] Run local smoke test with Playwright fallback.
- [ ] Add Browserbase session creation if a direct connect URL is not enough.
- [ ] Confirm `BROWSERBASE_CONNECT_URL` path works.

### P1: Action Executor

- [ ] Improve target resolution in `actions.py`.
- [ ] Support stable refs from `data-browserdelta-ref`.
- [ ] Add action types if needed: select, hover, upload.
- [ ] Keep action result errors explicit.

### P2: State Capture

- [x] Expand `state.py` with stable HTML attrs needed by the compaction matcher.
- [ ] Add true accessibility snapshot if time permits.
- [ ] Capture network failures from Playwright event hooks.
- [ ] Capture console errors from Playwright event hooks.

### P3: Runs

- [x] Record one complete flow from `tasks/` locally.
- [x] Save `steps.jsonl` and all before/after states.
- [x] Hand the run folder to the compaction team through the shared run contract.

## Compaction Team

Goal: turn raw step data into compact observations.

### P0: Structural Diff

- [x] Improve element identity matching.
- [x] Detect modal opened/closed.
- [x] Detect form validation errors.
- [x] Detect button enabled/disabled.

### P1: Visual Diff

- [x] Tune image threshold.
- [x] Split changed regions into useful crops.
- [ ] Ignore tiny cursor/caret/animation noise.
- [ ] Add OCR only if crops are unreadable from DOM.

### P2: Observation Rendering

- [x] Make `llm_observation` terse and action-useful.
- [x] Include current interactive refs.
- [x] Include fallback hint when crop/full screenshot is needed.
- [x] Estimate baseline vs compact token count.

## Shared

- [ ] Do not change schema without updating `docs/schemas.md`.
- [ ] Keep all generated run artifacts under `runs/`.
- [ ] Prefer command-line proof before frontend polish.
- [x] Add `tests/test_run_contract.py` as the shared recorder/codec contract
  check.
- [x] Keep `examples/runs/login_error` as the golden recorder/codec smoke fixture.
- [x] Add `examples/runs/modal_checkout` and `examples/runs/visual_only_change`
  to cover text-only and crop fallback routing.
- [x] Add `tasks/local_checkout.json` as a live local browser proof that records
  validation, input, visual-only, and modal transitions.
- [x] Browserbase team should produce one Browserbase-backed run that matches
  the local proof shape once credentials are available.
- [x] Add replay eval that writes `eval_report.json` and scores next-action
  parity from compact observations.
- [x] Add model-backed replay eval with `--predictor llm` so the demo can show a
  real model choosing next actions from compact context.

## Parallel Work Rule

Browserbase and compaction teams can work in parallel if they do not edit the
same mutable run folder. Browserbase owns recording raw files into
`runs/<run_id>/`; compaction owns reading those files and writing
`compact_observations.jsonl`. Run `pytest tests/test_run_contract.py` after any
change to recorder output, shared schemas, pointer paths, or compact observation
path handling.
