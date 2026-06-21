# BrowserDelta Remotion Demo

This folder contains the voiceover-synced pitch video source for BrowserDelta.
The current composition is a 3:28 demo built around Jay's recorded narration,
real BrowserDelta viewer captures, and the 5-seed MiniWoB benchmark summary.

## What It Shows

- The core problem: browser agents keep resending full screenshots and full page state even when only a small part of the page changed.
- The BrowserDelta layer: watch each before/after browser transaction and emit a compact LLM observation.
- The codec pipeline: DOM/accessibility diff first, visual changed-region detection next, OCR/SSIM/hash when useful, then route to `text_only`, `crop_with_context`, or `full_screenshot`.
- Real viewer captures showing a compact observation beside the screenshot/crop evidence.
- The 5-seed MiniWoB benchmark: `40.96% ± 1.55%` compact success vs `43.52% ± 1.93%` full-state success, with `469.88 ± 28.3` vs `2978.32 ± 212.0` average decision tokens.
- The headline tradeoff: `84.17% ± 1.16%` fewer decision tokens while keeping about `94%` of full-state success.

The benchmark numbers come from:

```text
reports/demo/miniwob-5seed-summary/summary.json
```

The app capture assets are committed under:

```text
video/public/assets/app/
```

Jay's raw narration and intro clip are intentionally local-only and ignored by
Git. To render this exact version, place these private files here:

```text
video/public/private/jay-voiceover.wav
video/public/private/jay-intro.mp4
```

Intermediate transcription/capture artifacts live under `video/work/`, and final
renders live under `video/out/`. Both directories are ignored by Git.

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
