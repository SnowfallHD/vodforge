"""A transition oracle must reject delayed partial paint, not just final state."""

from PIL import Image, ImageDraw
from quality_harness.resize_pixels import assess_static_resize_frames


def _sequence(tmp_path, *, delayed: bool):
    frames = []
    for index in range(9):
        image = Image.new("RGB", (200, 140), "#302c38")
        draw = ImageDraw.Draw(image)
        draw.rectangle((35, 72, 175, 105), fill="#aa88dd")
        if delayed and index < 7:
            draw.rectangle((80, 72, 175, 105), fill="#302c38")
        name = f"frame-{index}.png"
        image.save(tmp_path / name)
        frames.append(
            {
                "bounds": [0, 0, 200, 140],
                "begin": index * 0.05,
                "file": name,
            }
        )
    return frames


def test_static_resize_pixels_accept_complete_frames(tmp_path):
    assert assess_static_resize_frames(_sequence(tmp_path, delayed=False), tmp_path)[
        "passed"
    ]


def test_static_resize_pixels_reject_delayed_partial_control(tmp_path):
    result = assess_static_resize_frames(_sequence(tmp_path, delayed=True), tmp_path)
    assert not result["passed"]
    assert result["epochs"][0]["lagging"]


def test_static_resize_pixels_requires_transition_samples(tmp_path):
    assert not assess_static_resize_frames([], tmp_path)["passed"]
