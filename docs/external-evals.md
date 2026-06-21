# External evals (open-source browser-agent benchmarks)

BrowserDelta's internal suite (`scripts/eval_ab.py` → `eval_report.json`) records
real public sites and a local `demo_pages/` task. This doc adds an **external**
path so we can demo BrowserDelta on credible, citable browser-agent benchmarks.

## Why BrowserGym / MiniWoB++ first

- **Light & deterministic.** MiniWoB++ is dozens of tiny, self-contained DOM
  tasks. It runs locally from static HTML — no live websites, no auth, no flake.
- **Rich observations.** BrowserGym exposes exactly what BrowserDelta needs to
  compact: a CDP **accessibility tree** (with element `bid`s), a DOM snapshot, a
  screenshot, the goal, the last action, and reward/success — so the adapter can
  build a faithful BrowserDelta run record.
- **Credibility.** "We ran on BrowserGym/MiniWoB++" is a recognized benchmark
  story, far cheaper to stand up than WebArena.

Heavier options to add next, in rough order of effort:

1. **Browser Use benchmark** — agent-task suite aligned with this project's domain.
2. **WebArena / VisualWebArena** — realistic self-hosted sites; needs Docker and
   significant setup, but is the strongest credibility signal.
3. **WebLINX / Mind2Web trace replay** — no live browser; replay recorded human
   traces. Great for offline, reproducible grounding eval.

## Install

BrowserGym is an **optional** dependency (it is not needed for core recording,
compaction, or the internal eval):

```bash
pip install -e ".[external-evals]"
python -m playwright install chromium
```

MiniWoB++ serves static HTML. Clone it and point `MINIWOB_URL` at the html dir:

```bash
git clone https://github.com/Farama-Foundation/miniwob-plusplus.git
export MINIWOB_URL="file://$(pwd)/miniwob-plusplus/miniwob/html/miniwob/"
```

If BrowserGym is missing, the scripts fail with this exact install hint instead
of a traceback.

## Commands

Record one episode into BrowserDelta's run format and compact it:

```bash
python scripts/record_browsergym.py \
    --env browsergym/miniwob.click-button \
    --run-id bg_click_button --headless --compact
```

Run the small default suite and compare observation modes:

```bash
python scripts/eval_external_suite.py \
    --suite browsergym-miniwob --predictor llm --compare
```

Reports are written under `reports/external/` (gitignored).

## What the adapter does

`backend/browserdelta/external/browsergym_adapter.py` converts each BrowserGym
observation into the existing run schema (`docs/schemas.md`) — no schema change:

| BrowserGym obs field            | BrowserDelta                                  |
| ------------------------------- | --------------------------------------------- |
| `url`, `open_pages_titles`      | `PageState.url`, `PageState.title`            |
| `axtree_object` (named nodes)   | `PageState.text`                              |
| `axtree_object` (nodes w/ bid)  | `PageState.interactive` (ref/role/name/state) |
| `extra_element_properties.bbox` | `InteractiveElement.bbox`                     |
| `screenshot` (np array)         | `steps/step_*.png`                           |
| `focused_element_bid`           | `PageState.focused_ref`                       |
| `goal` / `goal_object`          | `RunManifest.metadata.goal`                  |
| BrowserGym action string        | `BrowserAction` (`click(bid)` → click, ...)   |
| `reward` / `info.success`       | `RunManifest.metadata.{reward,success}`      |

Runs are tagged `metadata.source = "browsergym"` and keep `mode = "local"`.

### Limitation

MiniWoB tasks are not *solved* by default — the recorder ships a no-op policy and
records observation **transitions** (which is what compaction is measured on).
Pass scripted `--action` strings, or wire an agent policy, to drive task success.
The `--predictor llm` flag only affects next-action *grounding* scoring, not the
recording.

## Metrics we show in the demo

`scripts/eval_external_suite.py` aggregates across episodes and reports, per the
three observation modes (`vision_full_state` = full state + screenshot,
`full_state` = text only, `compact` = BrowserDelta):

- **token totals** per mode and **savings %** (compact vs each baseline)
- **next-action accuracy** (can the predictor recover the next action from each
  mode's observation), heuristic or `llm`
- **episode success rate** and **mean latency**
- **per-task failures** (missing dep, env error, or unsolved episode)
