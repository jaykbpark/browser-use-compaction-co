# Arize Evaluator Setup

BrowserDelta uses Arize AX for three judged surfaces:

1. Trace emission from replay evals and live BrowserGym/MiniWoB evals.
2. An Arize evaluator named `browserdelta_action_preservation`.
3. A continuous task over the `browserdelta-hackathon` project that scores step-level
   evaluator spans.

Created Arize resources:

- AI integration: `browserdelta-openai`
  (`TGxtSW50ZWdyYXRpb246NDAwMjpNMTYv`)
- Evaluator: `browserdelta_action_preservation`
  (`RXZhbHVhdG9yOjk0MTQ6Zm1ZOQ==`)
- Continuous task: `browserdelta_action_preservation_continuous`
  (`T25saW5lVGFzazoyNzU5NjoyZW1T`)
- On-demand backfill task: `browserdelta_action_preservation_backfill`
  (`T25saW5lVGFzazoyNzYwMDppNi9l`)

Verified setup:

- The backfill task completed a run over `2026-06-21T18:00:00Z` to
  `2026-06-21T18:25:00Z` with `30` successes, `0` errors, and `0` skipped.
- Exported spans include Arize evaluations named
  `browserdelta_action_preservation` with labels such as
  `preserved_high_compression`, `preserved_low_compression`, and
  `preserved_no_compression`.

## What the evaluator scores

The evaluator runs on spans with `openinference.span.kind = EVALUATOR`.

The preferred deterministic code evaluator reads these BrowserDelta span attributes:

- `browserdelta.passed`
- `browserdelta.compact_tokens`
- `browserdelta.baseline_tokens`
- `browserdelta.reduction_pct`
- `browserdelta.route`
- `browserdelta.fallback`
- `browserdelta.match_reason`

If custom code evaluators are unavailable on the Arize account, use the
LLM-as-judge fallback in `integrations/arize/action_preservation_template.txt`.
That template reads:

- `input` mapped to `attributes.input.value`
- `output` mapped to `attributes.output.value`

Labels:

- `preserved_high_compression`: next action preserved and token reduction is at least 70%.
- `preserved_low_compression`: next action preserved, but token savings are below 70%.
- `preserved_no_compression`: next action preserved, but no token reduction.
- `regressed_next_action`: compact observation changed the expected next action.
- `missing_eval_data`: required span fields were missing.

## CLI setup

```bash
pip install -e ".[observability]" arize-ax-cli
cp /Users/jaypark/Documents/GitHub/browser-use-compaction-co/.env .env
```

Try to create the deterministic code evaluator in the Arize space from the
project `.env`:

```bash
set -a; source .env; set +a

ax evaluators create-code-evaluator \
  --space "$ARIZE_SPACE_ID" \
  --name browserdelta_action_preservation \
  --description "Scores whether BrowserDelta preserved the next browser action while saving tokens." \
  --commit-message "Initial BrowserDelta action-preservation evaluator" \
  --code-type custom \
  --code-name browserdelta_action_preservation \
  --variables @integrations/arize/action_preservation_variables.json \
  --code @integrations/arize/browserdelta_action_preservation_evaluator.py \
  --data-granularity span \
  --query-filter "attributes.openinference.span.kind = 'EVALUATOR'" \
  --output json
```

If Arize returns `Custom code evals are not available for your account`, create
the LLM-as-judge evaluator instead:

The checked-in template uses `{input}` and `{output}` placeholders because that
is the form accepted by the live Arize evaluator API for this account.

```bash
set -a; source .env; set +a

ax ai-integrations create \
  --name browserdelta-openai \
  --provider openAI \
  --api-key "$OPENAI_API_KEY" \
  --model-name gpt-4.1-mini \
  --model-name gpt-4o-mini \
  --function-calling-enabled \
  --output json

ax evaluators create-template-evaluator \
  --space "$ARIZE_SPACE_ID" \
  --name browserdelta_action_preservation \
  --description "Scores whether BrowserDelta preserved the next browser action while saving tokens." \
  --commit-message "Initial BrowserDelta action-preservation evaluator" \
  --template-name browserdelta_action_preservation \
  --template "$(cat integrations/arize/action_preservation_template.txt)" \
  --ai-integration-id "<browserdelta-openai integration id>" \
  --model-name gpt-4.1-mini \
  --include-explanations \
  --use-function-calling \
  --classification-choices '{"preserved_high_compression":1,"preserved_low_compression":0.5,"preserved_no_compression":0.25,"regressed_next_action":0,"missing_eval_data":0}' \
  --direction maximize \
  --data-granularity span \
  --output json
```

Then create the continuous task against the `browserdelta-hackathon` project,
replacing the evaluator ID in `integrations/arize/action_preservation_task_evaluators.json`:

```bash
ax tasks create-evaluation \
  --space "$ARIZE_SPACE_ID" \
  --project browserdelta-hackathon \
  --name browserdelta_action_preservation_continuous \
  --task-type code_evaluation \
  --evaluators @integrations/arize/action_preservation_task_evaluators.json \
  --sampling-rate 1 \
  --is-continuous \
  --query-filter "attributes.openinference.span.kind = 'EVALUATOR'" \
  --output json
```

The live setup currently uses the LLM-as-judge fallback, so the live continuous
task uses `--task-type template_evaluation` and
`integrations/arize/action_preservation_template_task_evaluators.json`.

It is also useful to keep a non-continuous backfill task with the same evaluator
mapping. That gives us a manual proof path for demos and judge review:

```bash
ax tasks create-evaluation \
  --space "$ARIZE_SPACE_ID" \
  --project browserdelta-hackathon \
  --name browserdelta_action_preservation_backfill \
  --task-type template_evaluation \
  --evaluators @integrations/arize/action_preservation_template_task_evaluators.json \
  --sampling-rate 1 \
  --no-continuous \
  --query-filter "attributes.openinference.span.kind = 'EVALUATOR'" \
  --output json
```

Send demo traces:

```bash
python scripts/eval_run.py runs/local_checkout --predictor llm --compare --arize
```

Trigger a backfill task run:

```bash
export ARIZE_BACKFILL_TASK_ID="T25saW5lVGFzazoyNzYwMDppNi9l"

curl -sS -X POST "https://api.arize.com/v2/tasks/$ARIZE_BACKFILL_TASK_ID/trigger" \
  -H "Authorization: Bearer ${ARIZE_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{
    "data_start_time": "2026-06-21T18:00:00Z",
    "data_end_time": "2026-06-21T18:25:00Z",
    "max_spans": 200,
    "override_evaluations": true
  }'
```

The `ax tasks trigger-run` CLI path worked for creating runs but rejected or
mis-serialized timestamp windows in this environment, so the direct REST trigger
is the reliable path for now.
