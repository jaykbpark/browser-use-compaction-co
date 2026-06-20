from pathlib import Path

from PIL import Image

from browserdelta.compaction.image_diff import diff_images


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

    assert visual.changed_pct > 0
    assert visual.regions
