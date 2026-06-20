from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from browserdelta.schemas import BoundingBox, VisualDiff, VisualRegion


def diff_images(before_path: Path, after_path: Path, threshold: int = 32) -> VisualDiff:
    if not before_path.exists() or not after_path.exists():
        return VisualDiff(changed_pct=0.0, regions=[])

    before = Image.open(before_path).convert("RGB")
    after = Image.open(after_path).convert("RGB")
    if before.size != after.size:
        after = after.resize(before.size)

    before_arr = np.asarray(before, dtype=np.int16)
    after_arr = np.asarray(after, dtype=np.int16)
    diff = np.abs(after_arr - before_arr).mean(axis=2)
    mask = diff > threshold

    changed_pixels = int(mask.sum())
    total_pixels = int(mask.size)
    changed_pct = round((changed_pixels / max(total_pixels, 1)) * 100, 3)

    if changed_pixels == 0:
        return VisualDiff(changed_pct=0.0, regions=[])

    regions = _regions_from_mask(mask)
    return VisualDiff(changed_pct=changed_pct, regions=regions)


def write_crops(after_path: Path, regions: list[VisualRegion], output_dir: Path) -> list[VisualRegion]:
    if not after_path.exists() or not regions:
        return regions

    output_dir.mkdir(parents=True, exist_ok=True)
    image = Image.open(after_path).convert("RGB")
    updated: list[VisualRegion] = []

    for index, region in enumerate(regions, start=1):
        box = region.bbox
        left = max(int(box.x), 0)
        top = max(int(box.y), 0)
        right = min(int(box.x + box.width), image.width)
        bottom = min(int(box.y + box.height), image.height)
        crop_path = output_dir / f"crop_{index:02d}.png"
        image.crop((left, top, right, bottom)).save(crop_path)
        updated.append(
            VisualRegion(
                bbox=region.bbox,
                kind=region.kind,
                crop_path=str(crop_path),
            )
        )

    return updated


def _regions_from_mask(mask: np.ndarray) -> list[VisualRegion]:
    try:
        import cv2  # type: ignore

        num_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(
            mask.astype("uint8"), connectivity=8
        )
        regions: list[VisualRegion] = []
        for label in range(1, num_labels):
            x, y, width, height, area = stats[label]
            if area < 25:
                continue
            regions.append(
                VisualRegion(
                    bbox=BoundingBox(x=float(x), y=float(y), width=float(width), height=float(height))
                )
            )
        return regions[:8]
    except Exception:  # noqa: BLE001 - OpenCV fallback should not block compaction
        ys, xs = np.where(mask)
        x0, x1 = xs.min(), xs.max()
        y0, y1 = ys.min(), ys.max()
        return [
            VisualRegion(
                bbox=BoundingBox(
                    x=float(x0),
                    y=float(y0),
                    width=float(x1 - x0 + 1),
                    height=float(y1 - y0 + 1),
                )
            )
        ]
