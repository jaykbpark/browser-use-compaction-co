# Schemas

This is the contract between the Browserbase team and the compaction team.

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
      "attributes": {"id": null, "type": null, "href": "https://iana.org/domains/example"}
    }
  ],
  "focused_ref": null,
  "console_errors": [],
  "network_errors": [],
  "screenshot": "runs/smoke/steps/step_001_before.png",
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
  "fallback": "none",
  "llm_observation": "Focus changed to Search textbox",
  "crop_paths": [],
  "full_screenshot_path": null,
  "tokens_estimate": 8
}
```
