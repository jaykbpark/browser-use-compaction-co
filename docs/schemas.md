# Schemas

This is the contract between the Browserbase team and the compaction team.

All file pointers in this contract are relative to the run folder. For example,
`steps/step_001_after.png` resolves to
`runs/<run_id>/steps/step_001_after.png`.

## Run Manifest

`runs/<run_id>/run.json`

```json
{
  "run_id": "smoke",
  "start_url": "https://example.com",
  "mode": "local",
  "steps_path": "steps.jsonl",
  "metadata": {}
}
```

## Step Record

`runs/<run_id>/steps.jsonl`

The filename comes from `run.json.steps_path`; `steps.jsonl` is the default.

```json
{
  "step": 1,
  "action": {
    "type": "click",
    "target": "Search textbox",
    "text": null,
    "key": null,
    "amount": null,
    "url": null,
    "metadata": {}
  },
  "result": {
    "ok": true,
    "message": "click executed",
    "error": null
  },
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

## Page State

`runs/<run_id>/steps/step_001_before.json`

```json
{
  "url": "https://example.com",
  "title": "Example Domain",
  "text": ["Example Domain", "This domain is for use in illustrative examples."],
  "interactive": [
    {
      "ref": "e1",
      "role": "link",
      "name": "More information...",
      "value": null,
      "disabled": false,
      "checked": null,
      "selected": null,
      "expanded": null,
      "bbox": {"x": 1, "y": 2, "width": 3, "height": 4},
      "attributes": {
        "id": null,
        "name": null,
        "aria-label": null,
        "data-testid": null,
        "data-test": null,
        "type": null,
        "href": "https://iana.org/domains/example"
      }
    }
  ],
  "focused_ref": null,
  "console_errors": [],
  "network_errors": [],
  "screenshot": "steps/step_001_before.png",
  "metadata": {"capture_version": 1}
}
```

## Compact Observation

`runs/<run_id>/compact_observations.jsonl`

```json
{
  "step": 1,
  "action_result": "success",
  "summary": "Focus changed to Search textbox",
  "changed": [
    {
      "type": "focus_changed",
      "detail": "Focus changed to Search textbox",
      "before": null,
      "after": "Search textbox"
    }
  ],
  "interactive": [],
  "visual_changed_pct": 0.4,
  "visual_raw_changed_pct": 0.4,
  "visual_ssim_score": 0.9912,
  "visual_phash_distance": 3,
  "fallback": "none",
  "route": "text_only",
  "route_reason": "DOM/accessibility changes explain the step.",
  "confidence": 0.89,
  "llm_observation": "Focus changed to Search textbox",
  "crop_paths": [],
  "full_screenshot_path": null,
  "visual_regions": [
    {
      "bbox": {"x": 120, "y": 180, "width": 260, "height": 140},
      "kind": "canvas_changed",
      "crop_path": "crops/step_001/crop_01.png",
      "area_pct": 2.7,
      "element_ref": "e4",
      "element_role": "canvas",
      "element_name": "Revenue chart",
      "overlap_pct": 97.2,
      "ocr_text": null
    }
  ],
  "tokens_estimate": 8,
  "baseline_tokens_estimate": 520,
  "reduction_pct": 98.46
}
```

### Route fields

- `fallback`: backwards-compatible attachment hint for the agent runner:
  `none`, `crop`, or `full_screenshot`.
- `route`: higher-level compaction decision:
  `text_only`, `crop_with_context`, or `full_screenshot`.
- `route_reason`: short explanation for why the route was chosen.
- `confidence`: `0.0` to `1.0` estimate that the compact observation contains
  enough context for the next agent step.
- `crop_paths`: run-relative crop paths written only when `fallback` is `crop`.
- `full_screenshot_path`: run-relative screenshot path written only when
  `fallback` is `full_screenshot`.
- `visual_regions`: CV-derived changed regions. Regions may include DOM element
  alignment (`element_*`, `overlap_pct`) and optional OCR text when local OCR is
  available.

### Metric fields

- `visual_changed_pct`: filtered meaningful visual change after removing tiny
  noise components.
- `visual_raw_changed_pct`: raw thresholded pixel change before noise filtering.
- `visual_ssim_score`: approximate screenshot structural similarity, where
  `1.0` means identical.
- `visual_phash_distance`: perceptual hash distance between before/after
  screenshots.
- `tokens_estimate`: estimated cost of the compact observation, including any
  attached crop or full screenshot fallback.
- `baseline_tokens_estimate`: estimated cost of the uncompressed baseline,
  modeled as raw `PageState` JSON plus the after-action screenshot.
- `reduction_pct`: estimated percentage saved versus that baseline.

## Eval Report

`runs/<run_id>/eval_report.json`

Compact-context replay writes `eval_report.json`. Full captured-state baseline
replay writes `eval_full_state_report.json` with the same shape and
`context_mode: "full_state"`. Vision full-state replay writes
`eval_vision_full_state_report.json` with `context_mode: "vision_full_state"`.

```json
{
  "run_id": "local_checkout",
  "predictor": "heuristic",
  "context_mode": "compact",
  "evaluated_steps": 3,
  "passed_steps": 3,
  "next_action_accuracy": 1.0,
  "compact_tokens": 1200,
  "baseline_tokens": 4500,
  "avg_reduction_pct": 73.33,
  "steps": [
    {
      "step": 1,
      "context_mode": "compact",
      "observation_summary": "New text appeared: Email is required",
      "expected_next_action": {"type": "type", "target": "Email", "text": "jay@example.com"},
      "predicted_next_action": {"type": "type", "target": "Email", "text": "jay@example.com"},
      "passed": true,
      "match_reason": "type action target and text matched",
      "rationale": "Validation text appeared, so fill the first available textbox.",
      "confidence": 0.82,
      "route": "text_only",
      "fallback": "none",
      "tokens_estimate": 66,
      "baseline_tokens_estimate": 1487,
      "reduction_pct": 95.56
    }
  ]
}
```

The eval report scores transitions. Step `N` is judged by whether the compact
observation after step `N` predicts the recorded action at step `N + 1`.

`predictor` is either `heuristic` for deterministic smoke checks or `llm:<model>`
for model-backed replay eval.

`context_mode` is:

- `compact`: the replay agent receives the compact observation from
  `compact_observations.jsonl`.
- `full_state`: the replay agent receives a rendered full after-action page
  state and a full screenshot pointer. Token estimates include the raw page
  state plus screenshot evidence.
- `vision_full_state`: the replay agent receives the rendered full after-action
  page state and the after-action screenshot as an actual model `input_image`.
  This is the honest vision baseline for compact-versus-screenshot comparisons.

## Eval Comparison

`runs/<run_id>/eval_comparison.json`

```json
{
  "run_id": "local_checkout",
  "predictor": "llm:gpt-4.1-mini",
  "compact": {"context_mode": "compact"},
  "baseline": {"context_mode": "vision_full_state"},
  "summary": {
    "run_id": "local_checkout",
    "predictor": "llm:gpt-4.1-mini",
    "baseline_context_mode": "vision_full_state",
    "evaluated_steps": 3,
    "compact_passed_steps": 3,
    "baseline_passed_steps": 3,
    "compact_accuracy": 1.0,
    "baseline_accuracy": 1.0,
    "accuracy_delta": 0.0,
    "compact_tokens": 1200,
    "baseline_tokens": 4500,
    "token_savings": 3300,
    "token_reduction_pct": 73.33
  },
  "verdict": "compact_matches_or_beats_baseline",
  "explanation": [
    "Compact context got 3/3 next actions correct.",
    "Vision full state baseline got 3/3 next actions correct.",
    "Compact context used 1200 estimated tokens versus 4500 for vision full state, saving 73.33%."
  ]
}
```

`eval_summary.md` is the human-readable companion to `eval_comparison.json`. It
contains the verdict, plain-English explanation, and a step-by-step compact
versus baseline prediction table.
