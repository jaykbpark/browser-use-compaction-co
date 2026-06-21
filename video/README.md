# BrowserDelta Remotion Demo

This folder contains the rendered pitch video source for BrowserDelta.

## What It Shows

- A split between the `full_state` browser-agent loop and the BrowserDelta compact-observation loop.
- The VisualDelta escalation policy: text diff first, cropped screenshot only when needed, full screenshot as the final fallback.
- A live MiniWoB demo case where compact context finds the target without sending a screenshot.
- The 125-task MiniWoB benchmark: `48/125` compact success vs `50/125` full-state success, with `451.7` vs `2828.4` average decision tokens.

The benchmark numbers come from:

```text
reports/external/browsergym-live-miniwob_llm_20260621T091600Z.json
```

The benchmark chart asset was copied from:

```text
reports/external/browserdelta-miniwob-simple-bars_20260621.png
```

## Commands

Install dependencies:

```bash
npm install
```

Preview in Remotion Studio:

```bash
npm run preview
```

Render the final video:

```bash
npm run render
```

Render the poster frame:

```bash
npm run poster
```

Type-check the composition:

```bash
npm run check
```

Rendered files are written to `video/out/`, which is intentionally ignored by Git.
