import pytest
from PIL import Image, ImageDraw
from quality_harness.artwork_observations import (
    inspect_artwork_centers,
    inspect_artwork_shapes,
)


def test_distinct_identity_detects_reused_pixels_with_unchanged_geometry():
    image = Image.new("RGB", (160, 80), (220, 40, 40))
    ImageDraw.Draw(image).rectangle((80, 0, 159, 79), fill=(40, 220, 40))
    regions = [
        {"owner": "one", "bbox": (0, 0, 80, 80)},
        {"owner": "two", "bbox": (80, 0, 160, 80)},
    ]
    palette = {"one": (220, 40, 40), "two": (40, 220, 40)}
    assert all(
        row["matched"] for row in inspect_artwork_centers(image, regions, palette)
    )
    image.paste(image.crop((0, 0, 80, 80)), (80, 0))
    results = inspect_artwork_centers(image, regions, palette)
    assert results[0]["matched"] and not results[1]["matched"]


@pytest.mark.parametrize(
    "region",
    [
        {"owner": "missing", "bbox": (0, 0, 80, 80)},
        {"owner": "one", "bbox": (-1, 0, 80, 80)},
    ],
)
def test_missing_identity_or_capture_cannot_pass(region):
    with pytest.raises(ValueError):
        inspect_artwork_centers(
            Image.new("RGB", (80, 80)), [region], {"one": (0, 0, 0)}
        )


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "horizontal_stretch",
        "vertical_stretch",
        "offset",
        "clipped",
        "filled",
        "duplicated",
        "missing",
    ],
)
def test_shape_oracle_detects_wrong_composition_despite_correct_center(fault):
    # Draw the expected geometry directly; never call the production fit routine.
    image = Image.new("RGB", (96, 96), (220, 40, 40))
    draw = ImageDraw.Draw(image)
    box = {
        "horizontal_stretch": (30, 12, 66, 84),
        "vertical_stretch": (12, 30, 84, 66),
        "offset": (18, 12, 90, 84),
    }.get(fault, (12, 12, 84, 84))
    if fault != "missing":
        draw.ellipse(
            box, outline="white", width=3, fill="white" if fault == "filled" else None
        )
    if fault == "clipped":
        draw.rectangle((48, 0, 95, 47), fill=(220, 40, 40))
    if fault == "duplicated":
        draw.ellipse((25, 25, 71, 71), outline="white", width=3)
    regions = [{"owner": "one", "bbox": (0, 0, 96, 96)}]
    if fault != "filled":
        assert inspect_artwork_centers(image, regions, {"one": (220, 40, 40)})[0][
            "matched"
        ]
    result = inspect_artwork_shapes(image, regions)[0]
    assert result["matched"] is (fault == "none"), result


@pytest.mark.parametrize("size", [32, 48, 80, 128])
def test_shape_oracle_preserves_correct_ring_across_avatar_sizes(size):
    image = Image.new("RGB", (size, size), (40, 80, 220))
    margin = size / 8
    ImageDraw.Draw(image).ellipse(
        (margin, margin, size - margin, size - margin),
        outline="white",
        width=max(1, round(size / 32)),
    )
    result = inspect_artwork_shapes(
        image, [{"owner": "one", "bbox": (0, 0, size, size)}]
    )[0]
    assert result["matched"], result


def test_identity_patch_can_avoid_known_foreground_content_without_ignoring_wrong_owner():
    image = Image.new("RGB", (200, 100), (220, 40, 40))
    ImageDraw.Draw(image).rectangle((0, 0, 135, 99), fill="black")
    regions = [
        {"owner": "one", "bbox": (0, 0, 200, 100), "identity_point": (0.88, 0.2)}
    ]
    palette = {"one": (220, 40, 40)}
    assert inspect_artwork_centers(image, regions, palette)[0]["matched"]
    image.paste((40, 220, 40), (140, 0, 200, 100))
    assert not inspect_artwork_centers(image, regions, palette)[0]["matched"]


def test_identity_patch_cannot_be_moved_outside_artwork():
    with pytest.raises(ValueError):
        inspect_artwork_centers(
            Image.new("RGB", (100, 100)),
            [{"owner": "one", "bbox": (0, 0, 100, 100), "identity_point": (1.5, 0.5)}],
            {"one": (0, 0, 0)},
        )
