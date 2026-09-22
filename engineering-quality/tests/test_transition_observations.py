from PIL import Image
from quality_harness.transition_observations import classify_view_regions


def test_mixed_generation_detection_has_valid_and_unknown_controls():
    old = Image.new("RGB", (100, 100), "#902030")
    new = Image.new("RGB", (100, 100), "#2060c0")
    boxes = [(0, 0, 50, 50), (50, 0, 100, 50), (0, 50, 50, 100), (50, 50, 100, 100)]
    for valid in (old, new):
        assert classify_view_regions(valid, old, new, boxes)["status"] == "passed"
    mixed = old.copy()
    mixed.paste(new.crop((0, 0, 100, 50)), (0, 0))
    result = classify_view_regions(mixed, old, new, boxes)
    assert result["status"] == "failed" and result["mixed_generations"]
    unknown = Image.new("RGB", old.size, "#20d030")
    assert classify_view_regions(unknown, old, new, boxes)["status"] == "unproven"
    assert classify_view_regions(old, old, new, [])["status"] == "unproven"

    assert classify_view_regions(old, old, old, boxes)["status"] == "unproven"


def test_content_regions_preserve_compact_grid_and_sparse_large_view_sensitivity():
    from PIL import Image, ImageDraw
    from quality_harness.transition_observations import (
        classify_view_regions,
        content_regions,
    )

    assert content_regions((980, 600)) == [
        (x, y, x + 230, y + 130)
        for y in (60, 190, 320, 450)
        for x in (20, 250, 480, 710)
    ]
    size = (1280, 760)
    boxes = content_regions(size)
    assert max(b[2] for b in boxes) == 1240
    assert max(b[3] for b in boxes) == 740
    assert all(0 < x2 - x1 <= 230 and 0 < y2 - y1 <= 130 for x1, y1, x2, y2 in boxes)
    old = Image.new("RGB", size, "black")
    new = old.copy()
    draw = ImageDraw.Draw(new)
    for x, y, _, _ in boxes[:4]:
        draw.rectangle((x + 10, y + 10, x + 64, y + 44), fill="white")
    assert classify_view_regions(old, old, new, boxes)["status"] == "passed"
    assert classify_view_regions(new, old, new, boxes)["status"] == "passed"
    mixed = old.copy()
    for box in boxes[:2]:
        mixed.paste(new.crop(box), box[:2])
    assert classify_view_regions(mixed, old, new, boxes)["mixed_generations"]


def test_unchanged_control_can_move_without_losing_its_border():
    from PIL import Image, ImageDraw
    from quality_harness.transition_observations import compare_unchanged_regions

    control = Image.new("RGB", (200, 40), "#091018")
    ImageDraw.Draw(control).rounded_rectangle(
        (0, 0, 199, 39), radius=9, fill="#18202b", outline="#526477", width=2
    )
    before = Image.new("RGB", (400, 100))
    before.paste(control, (10, 20))
    after = Image.new("RGB", (500, 100))
    after.paste(control, (230, 20))
    expected = [{"owner": "search", "bbox": (10, 20, 210, 60)}]
    moved = [{"owner": "search", "bbox": (230, 20, 430, 60)}]
    assert compare_unchanged_regions(after, before, moved, expected)[0]["matched"]
    # Real missing-chrome pixels, not a changed oracle flag.
    ImageDraw.Draw(after).rectangle((230, 20, 429, 59), fill="#18202b")
    result = compare_unchanged_regions(after, before, moved, expected)[0]
    assert result["status"] == "failed" and result["changed_pixels"] > 40


def test_unchanged_control_rejects_wrong_reference_size_and_clipped_pixels():
    import pytest
    from PIL import Image
    from quality_harness.transition_observations import compare_unchanged_regions

    image = Image.new("RGB", (200, 100), "white")
    refs = [{"owner": "button", "bbox": (0, 0, 100, 40)}]
    different = [{"owner": "button", "bbox": (0, 0, 120, 40)}]
    assert (
        compare_unchanged_regions(image, image, different, refs)[0]["status"]
        == "unproven"
    )
    with pytest.raises(ValueError, match="outside"):
        compare_unchanged_regions(
            image, image, [{"owner": "button", "bbox": (-1, 0, 99, 40)}], refs
        )
    with pytest.raises(ValueError, match="missing|no reference"):
        compare_unchanged_regions(
            image, image, [{"owner": "other", "bbox": (0, 0, 100, 40)}], refs
        )


def test_unchanged_controls_cannot_pass_when_one_required_control_disappears():
    import pytest
    from quality_harness.transition_observations import compare_unchanged_regions

    image = Image.new("RGB", (200, 100), "white")
    controls = [
        {"owner": "search", "bbox": (0, 0, 100, 40)},
        {"owner": "filter", "bbox": (100, 0, 200, 40)},
    ]
    assert all(
        row["matched"]
        for row in compare_unchanged_regions(image, image, controls, controls)
    )
    with pytest.raises(ValueError, match="missing"):
        compare_unchanged_regions(image, image, controls[:1], controls)
