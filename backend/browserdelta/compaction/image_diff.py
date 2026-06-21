from __future__ import annotations

from pathlib import Path
import re

import numpy as np
from PIL import Image

from browserdelta.schemas import BoundingBox, InteractiveElement, VisualDiff, VisualRegion


MIN_REGION_PIXELS = 25
MERGE_GAP_PX = 18
CROP_PADDING_PX = 8
MAX_REGIONS = 8
PHASH_SIZE = 8
SSIM_RESIZE = (128, 128)


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
    raw_changed_pct = round((changed_pixels / max(total_pixels, 1)) * 100, 3)
    ssim_score = _ssim_score(before, after)
    phash_distance = _phash_distance(before, after)

    if changed_pixels == 0:
        return VisualDiff(
            changed_pct=0.0,
            regions=[],
            raw_changed_pct=0.0,
            ssim_score=ssim_score,
            perceptual_hash_distance=phash_distance,
        )

    regions = _regions_from_mask(mask)
    changed_pct = round(sum(region.area_pct for region in regions), 3)
    return VisualDiff(
        changed_pct=changed_pct,
        regions=regions,
        raw_changed_pct=raw_changed_pct,
        ssim_score=ssim_score,
        perceptual_hash_distance=phash_distance,
    )


def align_regions_to_elements(
    visual: VisualDiff,
    elements: list[InteractiveElement],
) -> VisualDiff:
    """Attach nearest DOM/accessibility element metadata to changed visual regions."""

    if not visual.regions or not elements:
        return visual

    aligned: list[VisualRegion] = []
    for region in visual.regions:
        best = _best_overlap(region.bbox, elements)
        if not best:
            aligned.append(region)
            continue
        element, overlap_pct = best
        element_name = _element_label(element)
        aligned.append(
            region.model_copy(
                update={
                    "kind": _visual_kind_for_element(element, region.kind),
                    "element_ref": element.ref,
                    "element_role": element.role,
                    "element_name": element_name,
                    "overlap_pct": overlap_pct,
                }
            )
        )

    return visual.model_copy(update={"regions": aligned})


def write_crops(
    after_path: Path, regions: list[VisualRegion], output_dir: Path
) -> list[VisualRegion]:
    if not after_path.exists() or not regions:
        return regions

    output_dir.mkdir(parents=True, exist_ok=True)
    for stale_crop in output_dir.glob("crop_*.png"):
        stale_crop.unlink()

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
                area_pct=region.area_pct,
                element_ref=region.element_ref,
                element_role=region.element_role,
                element_name=region.element_name,
                overlap_pct=region.overlap_pct,
                ocr_text=region.ocr_text,
            )
        )

    return updated


def annotate_regions_with_ocr(regions: list[VisualRegion]) -> list[VisualRegion]:
    """Best-effort OCR for changed crops.

    OCR is optional: if pytesseract or the local Tesseract binary is unavailable,
    this function returns the regions unchanged.
    """

    if not regions:
        return regions

    try:
        import pytesseract  # type: ignore
    except Exception:  # noqa: BLE001 - optional dependency
        return regions

    annotated: list[VisualRegion] = []
    for region in regions:
        if not region.crop_path:
            annotated.append(region)
            continue
        try:
            image = Image.open(region.crop_path).convert("RGB")
            text = pytesseract.image_to_string(image, config="--psm 6")
        except Exception:  # noqa: BLE001 - optional OCR should not block compaction
            annotated.append(region)
            continue
        cleaned = _clean_ocr_text(text)
        annotated.append(region.model_copy(update={"ocr_text": cleaned or None}))
    return annotated


def _regions_from_mask(mask: np.ndarray) -> list[VisualRegion]:
    image_height, image_width = mask.shape
    try:
        import cv2  # type: ignore

        num_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
            mask.astype("uint8"), connectivity=8
        )
        boxes: list[tuple[int, int, int, int, int]] = []
        for label in range(1, num_labels):
            x, y, component_width, component_height, area = stats[label]
            if area < MIN_REGION_PIXELS:
                continue
            boxes.append(
                (
                    int(x),
                    int(y),
                    int(x + component_width),
                    int(y + component_height),
                    int(area),
                )
            )
        return _regions_from_boxes(boxes, image_width=image_width, image_height=image_height)
    except Exception:  # noqa: BLE001 - OpenCV fallback should not block compaction
        ys, xs = np.where(mask)
        if len(xs) == 0:
            return []
        if len(xs) < MIN_REGION_PIXELS:
            return []
        boxes = [(int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1), int(len(xs)))]
        return _regions_from_boxes(boxes, image_width=image_width, image_height=image_height)


def _regions_from_boxes(
    boxes: list[tuple[int, int, int, int, int]],
    image_width: int,
    image_height: int,
) -> list[VisualRegion]:
    if not boxes:
        return []

    merged = _merge_nearby_boxes(boxes, gap=MERGE_GAP_PX)
    ranked = sorted(merged, key=lambda box: (-box[4], box[1], box[0]))[:MAX_REGIONS]
    ordered = sorted(ranked, key=lambda box: (box[1], box[0]))

    regions: list[VisualRegion] = []
    total_area = max(image_width * image_height, 1)
    for x0, y0, x1, y1, area in ordered:
        padded = _pad_box(
            (x0, y0, x1, y1),
            padding=CROP_PADDING_PX,
            width=image_width,
            height=image_height,
        )
        px0, py0, px1, py1 = padded
        regions.append(
            VisualRegion(
                bbox=BoundingBox(
                    x=float(px0),
                    y=float(py0),
                    width=float(px1 - px0),
                    height=float(py1 - py0),
                ),
                area_pct=round((area / total_area) * 100, 3),
            )
        )
    return regions


def _merge_nearby_boxes(
    boxes: list[tuple[int, int, int, int, int]],
    gap: int,
) -> list[tuple[int, int, int, int, int]]:
    pending = sorted(boxes, key=lambda box: (box[1], box[0], box[2], box[3]))
    changed = True
    while changed:
        changed = False
        merged: list[tuple[int, int, int, int, int]] = []
        for box in pending:
            for index, existing in enumerate(merged):
                if _boxes_are_near(existing, box, gap):
                    merged[index] = _union_boxes(existing, box)
                    changed = True
                    break
            else:
                merged.append(box)
        pending = merged
    return pending


def _boxes_are_near(
    first: tuple[int, int, int, int, int],
    second: tuple[int, int, int, int, int],
    gap: int,
) -> bool:
    return not (
        first[2] + gap < second[0]
        or second[2] + gap < first[0]
        or first[3] + gap < second[1]
        or second[3] + gap < first[1]
    )


def _union_boxes(
    first: tuple[int, int, int, int, int],
    second: tuple[int, int, int, int, int],
) -> tuple[int, int, int, int, int]:
    return (
        min(first[0], second[0]),
        min(first[1], second[1]),
        max(first[2], second[2]),
        max(first[3], second[3]),
        first[4] + second[4],
    )


def _pad_box(
    box: tuple[int, int, int, int],
    padding: int,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return (
        max(0, x0 - padding),
        max(0, y0 - padding),
        min(width, x1 + padding),
        min(height, y1 + padding),
    )


def _best_overlap(
    region: BoundingBox,
    elements: list[InteractiveElement],
) -> tuple[InteractiveElement, float] | None:
    region_area = max(region.width * region.height, 1.0)
    best: tuple[InteractiveElement, float] | None = None
    for element in elements:
        if not element.bbox:
            continue
        overlap = _intersection_area(region, element.bbox)
        if overlap <= 0:
            continue
        overlap_pct = round((overlap / region_area) * 100, 2)
        if overlap_pct < 12:
            continue
        if best is None or overlap_pct > best[1]:
            best = (element, overlap_pct)
    return best


def _intersection_area(first: BoundingBox, second: BoundingBox) -> float:
    x0 = max(first.x, second.x)
    y0 = max(first.y, second.y)
    x1 = min(first.x + first.width, second.x + second.width)
    y1 = min(first.y + first.height, second.y + second.height)
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _element_label(element: InteractiveElement) -> str:
    attrs = element.attributes or {}
    return (
        element.name
        or str(attrs.get("aria-label") or "")
        or str(attrs.get("data-testid") or "")
        or str(attrs.get("id") or "")
        or element.ref
    )


def _visual_kind_for_element(element: InteractiveElement, fallback: str) -> str:
    role = (element.role or "").lower()
    name = _element_label(element).lower()
    if role in {"canvas", "img", "image", "svg"}:
        return f"{role}_changed"
    if "chart" in name or "graph" in name:
        return "chart_changed"
    if role in {"button", "checkbox", "radio", "switch"}:
        return "control_visual_changed"
    return fallback


def _clean_ocr_text(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned[:240]


def _ssim_score(before: Image.Image, after: Image.Image) -> float:
    before_gray = before.convert("L").resize(SSIM_RESIZE)
    after_gray = after.convert("L").resize(SSIM_RESIZE)
    x = np.asarray(before_gray, dtype=np.float64)
    y = np.asarray(after_gray, dtype=np.float64)

    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    mux = x.mean()
    muy = y.mean()
    varx = ((x - mux) ** 2).mean()
    vary = ((y - muy) ** 2).mean()
    cov = ((x - mux) * (y - muy)).mean()
    score = ((2 * mux * muy + c1) * (2 * cov + c2)) / ((mux**2 + muy**2 + c1) * (varx + vary + c2))
    return round(float(max(0.0, min(1.0, score))), 4)


def _phash_distance(before: Image.Image, after: Image.Image) -> int:
    return int(np.count_nonzero(_phash(before) != _phash(after)))


def _phash(image: Image.Image) -> np.ndarray:
    gray = image.convert("L").resize((PHASH_SIZE + 1, PHASH_SIZE), Image.Resampling.LANCZOS)
    arr = np.asarray(gray, dtype=np.int16)
    diff = arr[:, 1:] > arr[:, :-1]
    return diff.flatten()
