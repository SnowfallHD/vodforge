"""A transition oracle must reject delayed partial paint, not just final state."""

from PIL import Image, ImageDraw
from quality_harness.resize_pixels import assess_static_resize_frames


def _sequence(tmp_path, *, delayed: bool):
    frames = []
    for step in range(4):
        width = 200 + step * 20
        for index in range(9):
            image = Image.new("RGB", (width, 140), "#302c38")
            draw = ImageDraw.Draw(image)
            draw.rectangle((35, 72, 175, 105), fill="#aa88dd")
            if delayed and index < 7:
                draw.rectangle((80, 72, 175, 105), fill="#302c38")
            name = f"frame-{step}-{index}.png"
            image.save(tmp_path / name)
            frames.append(
                {
                    "bounds": [0, 0, width, 140],
                    "begin": (step * 9 + index) * 0.05,
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


def test_static_resize_pixels_requires_both_native_drags(tmp_path):
    events = [
        {"event": "drag_start", "rect": [0, 0, 200, 140]},
        {"event": "drag_end", "rect": [0, 0, 300, 140]},
        {"event": "drag_start", "rect": [0, 0, 300, 140]},
        {"event": "drag_end", "rect": [0, 0, 305, 140]},
    ]
    result = assess_static_resize_frames(
        _sequence(tmp_path, delayed=False), tmp_path, drag_events=events
    )
    assert not result["passed"]
    assert result["drag_width_changes"] == [100, 5]
