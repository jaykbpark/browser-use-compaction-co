from pathlib import Path
import sys
from types import SimpleNamespace

from PIL import Image

from browserdelta.compaction.codec import compact_step
from browserdelta.compaction.image_diff import (
    align_regions_to_elements,
    annotate_regions_with_ocr,
    diff_images,
)
from browserdelta.schemas import ActionResult, BrowserAction, PageState, StatePointer, StepRecord
from browserdelta.schemas import BoundingBox, InteractiveElement, VisualRegion
from browserdelta.storage import write_json


def test_image_diff_finds_changed_region(tmp_path: Path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"

    Image.new("RGB", (100, 100), "white").save(before)
    image = Image.new("RGB", (100, 100), "white")
    for x in range(10, 30):
        for y in range(10, 30):
            image.putpixel((x, y), (0, 0, 0))
    image.save(after)

    visual = diff_images(before, after)

    assert visual.changed_pct == 4.0
    assert visual.raw_changed_pct == 4.0
    assert visual.ssim_score is not None
    assert visual.perceptual_hash_distance is not None
    assert visual.regions


def test_image_diff_groups_nearby_pixels_into_one_region(tmp_path: Path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"

    Image.new("RGB", (100, 100), "white").save(before)
    image = Image.new("RGB", (100, 100), "white")
    for x in range(10, 20):
        for y in range(10, 20):
            image.putpixel((x, y), (0, 0, 0))
    for x in range(30, 40):
        for y in range(10, 20):
            image.putpixel((x, y), (0, 0, 0))
    image.save(after)

    visual = diff_images(before, after)

    assert visual.changed_pct == 2.0
    assert len(visual.regions) == 1
    box = visual.regions[0].bbox
    assert box.x <= 10
    assert box.y <= 10
    assert box.x + box.width >= 40
    assert box.y + box.height >= 20


def test_image_diff_filters_tiny_noise_without_regions(tmp_path: Path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"

    Image.new("RGB", (100, 100), "white").save(before)
    image = Image.new("RGB", (100, 100), "white")
    image.putpixel((10, 10), (0, 0, 0))
    image.putpixel((80, 80), (0, 0, 0))
    image.save(after)

    visual = diff_images(before, after)

    assert visual.raw_changed_pct > 0
    assert visual.changed_pct == 0.0
    assert visual.regions == []


def test_visual_regions_align_to_dom_element():
    visual = align_regions_to_elements(
        visual=diff_with_region(BoundingBox(x=20, y=20, width=80, height=60)),
        elements=[
            InteractiveElement(
                ref="e7",
                role="canvas",
                name="Revenue chart",
                bbox=BoundingBox(x=10, y=10, width=160, height=100),
            )
        ],
    )

    region = visual.regions[0]
    assert region.element_ref == "e7"
    assert region.element_role == "canvas"
    assert region.element_name == "Revenue chart"
    assert region.kind == "canvas_changed"
    assert region.overlap_pct == 100.0


def test_optional_ocr_annotation_reads_crop_text(tmp_path: Path, monkeypatch):
    crop = tmp_path / "crop.png"
    Image.new("RGB", (40, 20), "white").save(crop)
    fake_tesseract = SimpleNamespace(image_to_string=lambda image, config: " Saved successfully\n")
    monkeypatch.setitem(sys.modules, "pytesseract", fake_tesseract)

    regions = annotate_regions_with_ocr(
        [VisualRegion(bbox=BoundingBox(x=0, y=0, width=40, height=20), crop_path=str(crop))]
    )

    assert regions[0].ocr_text == "Saved successfully"


def test_compact_step_writes_crop_fallback_under_step_directory(tmp_path: Path):
    step = _write_visual_run(
        tmp_path,
        changed_rect=(10, 10, 30, 30),
        after_state=PageState(
            url="https://app.test/canvas",
            title="Canvas",
            text=["Canvas"],
            interactive=[
                InteractiveElement(
                    ref="e1",
                    role="canvas",
                    name="Revenue chart",
                    bbox=BoundingBox(x=0, y=0, width=60, height=60),
                )
            ],
        ),
    )
    crop_dir = tmp_path / "crops" / "step_001"
    crop_dir.mkdir(parents=True)
    (crop_dir / "crop_99.png").write_bytes(b"stale")

    observation = compact_step(tmp_path, step)

    assert observation.route == "crop_with_context"
    assert observation.fallback == "crop"
    assert observation.visual_changed_pct == 4.0
    assert len(observation.crop_paths) == 1
    assert observation.crop_paths[0] == "crops/step_001/crop_01.png"
    crop_path = tmp_path / observation.crop_paths[0]
    assert crop_path.parent == tmp_path / "crops" / "step_001"
    assert crop_path.name == "crop_01.png"
    assert crop_path.exists()
    assert sorted(path.name for path in crop_dir.glob("crop_*.png")) == ["crop_01.png"]
    with Image.open(crop_path) as crop:
        assert crop.size[0] >= 20
        assert crop.size[1] >= 20
    assert observation.full_screenshot_path is None
    assert "Visual fallback: 1 crop(s)" in observation.llm_observation
    assert "Revenue chart" in observation.summary
    assert "Visual regions:" in observation.llm_observation
    assert observation.visual_regions[0].element_name == "Revenue chart"


def test_compact_step_uses_full_screenshot_fallback_for_large_visual_change(tmp_path: Path):
    step = _write_visual_run(tmp_path, changed_rect=(0, 0, 70, 70))
    crop_dir = tmp_path / "crops" / "step_001"
    crop_dir.mkdir(parents=True)
    (crop_dir / "crop_01.png").write_bytes(b"stale")

    observation = compact_step(tmp_path, step)

    assert observation.route == "full_screenshot"
    assert observation.fallback == "full_screenshot"
    assert observation.visual_changed_pct == 49.0
    assert observation.crop_paths == []
    assert observation.full_screenshot_path == "steps/step_001_after.png"
    assert not crop_dir.exists()
    assert "Visual fallback: full screenshot attached" in observation.llm_observation


def _write_visual_run(
    run_path: Path,
    changed_rect: tuple[int, int, int, int],
    after_state: PageState | None = None,
) -> StepRecord:
    steps = run_path / "steps"
    steps.mkdir()
    before_png = steps / "step_001_before.png"
    after_png = steps / "step_001_after.png"

    Image.new("RGB", (100, 100), "white").save(before_png)
    image = Image.new("RGB", (100, 100), "white")
    x0, y0, x1, y1 = changed_rect
    for x in range(x0, x1):
        for y in range(y0, y1):
            image.putpixel((x, y), (0, 0, 0))
    image.save(after_png)

    before_state = PageState(url="https://app.test/canvas", title="Canvas", text=["Canvas"])
    write_json(steps / "step_001_before.json", before_state)
    write_json(steps / "step_001_after.json", after_state or before_state)

    return StepRecord(
        step=1,
        action=BrowserAction(type="click", target="Canvas"),
        result=ActionResult(ok=True),
        before=StatePointer(
            screenshot="steps/step_001_before.png",
            state="steps/step_001_before.json",
        ),
        after=StatePointer(
            screenshot="steps/step_001_after.png",
            state="steps/step_001_after.json",
        ),
    )


def diff_with_region(bbox: BoundingBox):
    from browserdelta.schemas import VisualDiff

    return VisualDiff(changed_pct=5.0, regions=[VisualRegion(bbox=bbox, area_pct=5.0)])
