# External Evals

BrowserDelta's credible external-eval path is:

```text
BrowserGym/MiniWoB episode
  -> BrowserDelta run folder
  -> compact_observations.jsonl
  -> existing replay eval
  -> compact vs vision_full_state comparison
```

## Why BrowserGym First

BrowserGym/MiniWoB++ is the lightest open browser-agent benchmark family for our
current stage. It gives us small browser tasks, screenshots, accessibility-tree
style observations, rewards, and task termination without requiring the full
WebArena deployment stack.

Heavier follow-ons:

- WebArena: credible web-agent benchmark, but heavier services and setup.
- VisualWebArena: better for visual grounding, also heavier.
- WebLINX / Mind2Web: useful for offline trace-style replay instead of live
  browser control.
- Browser Use benchmark / BU Bench: useful public comparison story, but should
  be wired after the local adapter path is stable.

## Dependency Rule

Do not add BrowserGym to BrowserDelta's default dependencies right now. Current
`browsergym-core` releases pin `playwright==1.44`, while BrowserDelta's recorder
uses a newer Playwright. Keep BrowserGym in a separate environment until that
conflict is resolved.

Example isolated setup:

```bash
python -m venv .venv-browsergym
.venv-browsergym/bin/pip install browsergym-miniwob==0.14.3
export MINIWOB_URL="file:///path/to/miniwob-plusplus/miniwob/html/miniwob/"
PYTHONPATH=$PWD/backend .venv-browsergym/bin/python scripts/record_browsergym.py \
  --env browsergym/miniwob.click-button \
  --run-id bg_click_button \
  --action "click('a12')" \
  --headless \
  --compact
```

Then evaluate from the normal BrowserDelta environment:

```bash
python scripts/eval_run.py runs/bg_click_button --compare --baseline-context vision_full_state
```

## No-Op Traces Are Not Success

`record_browsergym.py` requires scripted actions by default. You can pass
`--allow-noop-policy` for an adapter smoke trace, but that should not be used as
task-success evidence. A no-op trace only proves the import path writes a valid
run folder.

For a hackathon demo, use one of these:

- a tiny scripted MiniWoB trace with known element refs
- a BrowserGym policy that actually solves the task
- an offline imported trace with gold actions

The eval story should compare two observation tools while holding the agent and
task fixed:

- `vision_full_state`: full page state plus screenshot image every step
- `compact`: BrowserDelta changed DOM/text plus visual crops when needed

The metrics to show are task success or next-action parity, compact-vs-baseline
accuracy, estimated token savings, and failure examples.

## Live Agent Eval: Three Phases

The live path holds the task and agent fixed, then swaps only the observation
that the agent sees:

- `compact`: BrowserDelta compact observation after each action.
- `full_state`: uncompressed current page state and screenshot pointer.
- `vision_full_state`: uncompressed current page state plus attached screenshot
  image for model-backed policies.

Phase 1 is a small MiniWoB live smoke:

```bash
PYTHONPATH=$PWD/backend .venv-browsergym/bin/python scripts/run_browsergym_live.py \
  --env browsergym/miniwob.click-button \
  --modes compact,full_state \
  --policy llm \
  --headless \
  --max-steps 10
```

Phase 2 is the scaled MiniWoB run. Pass a suite JSON or let the script discover
registered MiniWoB envs and cap with `--limit 50`. The output JSON includes
raw runs, a failure table, and a chart-ready `charts` object:

```bash
PYTHONPATH=$PWD/backend .venv-browsergym/bin/python scripts/run_browsergym_live.py \
  docs/browsergym-live-suite.example.json \
  --modes compact,full_state \
  --policy llm \
  --headless \
  --limit 50 \
  --retries 1
```

Phase 3 is optional WorkArena. Probe first; if WorkArena is not installed, the
script returns a clean availability report instead of breaking normal CI:

```bash
PYTHONPATH=$PWD/backend .venv-browsergym/bin/python scripts/run_browsergym_live.py \
  --probe-workarena
```

## Failure Loop

After a scaled run, turn the report's failure table into a focused rerun suite.
This is the fastest way to show whether a compaction improvement fixed the hard
cases without paying to rerun the whole benchmark.

Default hard-case loop: compact regressions plus tasks where both modes failed.

```bash
python3 scripts/build_failure_suite.py \
  reports/external/browsergym-live-miniwob_llm_combined50_20260621T054656Z.json \
  --out artifacts/failure-loop/combined50-hard-cases.json
```

Then rerun only those cases:

```bash
PYTHONPATH=$PWD/backend .venv-browsergym/bin/python scripts/run_browsergym_live.py \
  artifacts/failure-loop/combined50-hard-cases.json \
  --modes compact,full_state \
  --policy llm \
  --headless \
  --retries 1
```

For a demo-positive loop that also includes cases where compact beat the
baseline, add `--all-non-success` when building the suite.
