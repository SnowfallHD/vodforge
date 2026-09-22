"""Independent ordinary-loop pixels qualify staged review reveal."""

import json
import os
import sys
import time
from itertools import pairwise
from pathlib import Path
from threading import Event, Thread

import pytest
from PIL import Image
from quality_harness.transition_observations import (
    classify_view_regions,
    compare_unchanged_regions,
    content_regions,
)

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump, seed
from tests.test_relink_navigation_native import descendants
from yt_downloader.platforms.macos.windowing import _native_window

application = _application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1" or sys.platform != "darwin",
    reason="Mac native display required",
)


@pytest.mark.parametrize("flow", ["relink", "playback"])
@pytest.mark.parametrize("fault", ["none", "entry", "return"])
def test_review_reveal_has_no_blank_or_mixed_frames(
    application, tmp_path, monkeypatch, fault, flow
):
    import Quartz
    from AppKit import NSApplication

    app = application
    if fault != "none":
        from yt_downloader.ui_transition import WidgetReveal

        original_start = WidgetReveal.start

        def show_too_early(reveal, ready=None):
            if (reveal.finished is not None) != (fault == "return"):
                return original_start(reveal, ready)
            for widget in reveal.outgoing:
                widget.grid_remove()
            reveal.frame.lift()
            reveal.cancel()
            if flow == "playback" and fault == "entry":
                # Missing loading text is a concrete sparse-content defect.
                # Immediate mapping alone can already be complete in one frame.
                for child in reveal.frame.winfo_children():
                    if child.winfo_class() == "TLabel":
                        child.grid_remove()
                        child.after(160, child.grid)

        monkeypatch.setattr(WidgetReveal, "start", show_too_early)
    rows = seed(app, tmp_path, 1)
    app._select_focus_view("library")
    app.geometry("1180x740+60+70")
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    pump(app, 0.5)
    replacement = tmp_path / "replacement.mp4"
    replacement.write_bytes(b"existence only")
    release_resolution = Event()
    if flow == "relink":
        app._archive_worker.close()
    else:
        from yt_downloader import media_player

        original_resolve = media_player.resolve_library_media_path

        def delayed_resolution(info):
            release_resolution.wait(3)
            return original_resolve(info)

        monkeypatch.setattr(
            media_player, "resolve_library_media_path", delayed_resolution
        )
        deadline = time.monotonic() + 2
        while app._archive_worker.busy and time.monotonic() < deadline:
            pump(app, 0.02)
        assert not app._archive_worker.busy
    number = int(_native_window(app).windowNumber())
    out = Path(os.environ["VODFORGE_NATIVE_EVIDENCE_DIR"]) / (flow + "-" + fault)
    out.mkdir()
    frames = []
    target_regions = []
    events = []
    errors = []
    stop = Event()
    origin = time.monotonic()

    def capture():
        try:
            while not stop.is_set():
                begin = time.monotonic() - origin
                raw = Quartz.CGWindowListCreateImage(
                    Quartz.CGRectNull,
                    Quartz.kCGWindowListOptionIncludingWindow,
                    number,
                    Quartz.kCGWindowImageBoundsIgnoreFraming
                    | Quartz.kCGWindowImageNominalResolution,
                )
                if raw is None:
                    raise RuntimeError("Own-window pixels unavailable")
                image = Image.frombytes(
                    "RGB",
                    (Quartz.CGImageGetWidth(raw), Quartz.CGImageGetHeight(raw)),
                    bytes(
                        Quartz.CGDataProviderCopyData(
                            Quartz.CGImageGetDataProvider(raw)
                        )
                    ),
                    "raw",
                    "BGRX",
                    Quartz.CGImageGetBytesPerRow(raw),
                )
                frames.append(
                    {"begin": begin, "end": time.monotonic() - origin, "_image": image}
                )
                if len(frames) >= 140:
                    raise RuntimeError("Bounded observer exceeded 140 frames")
                stop.wait(max(0, 0.020 - (time.monotonic() - origin - begin)))
        except Exception as exc:  # noqa: BLE001 - observer failure invalidates evidence
            errors.append(repr(exc))

    def begin():
        events.append({"event": "open_requested", "t": time.monotonic() - origin})
        if flow == "relink":
            app._archive_begin_relink(None, (0,), exact=str(replacement))
        else:
            app._archive_request_playback(rows[0])
        events.append(
            {
                "event": "open_returned",
                "t": time.monotonic() - origin,
                "flow": flow,
            }
        )

    def back():
        if flow == "playback":
            for n, widget in enumerate(app._archive_overlay.winfo_children()):
                if widget.winfo_class() in {"TLabel", "TButton"}:
                    x = widget.winfo_rootx() - app.winfo_rootx()
                    y = widget.winfo_rooty() - app.winfo_rooty()
                    target_regions.append(
                        {
                            "owner": f"loading-control-{n}",
                            "bbox": [
                                x,
                                y,
                                x + widget.winfo_width(),
                                y + widget.winfo_height(),
                            ],
                        }
                    )
        events.append({"event": "back_requested", "t": time.monotonic() - origin})
        next(
            w
            for w in descendants(app._archive_overlay)
            if w.winfo_class() == "TButton"
            and str(w.cget("text"))
            == ("Back to Library" if flow == "relink" else "Back to browse")
        ).invoke()
        events.append({"event": "back_returned", "t": time.monotonic() - origin})

    recorder = Thread(target=capture, daemon=True)
    recorder.start()
    app.after(250, begin)
    app.after(1250, back)
    app.after(2200, app.quit)
    try:
        app.mainloop()
    finally:
        stop.set()
        recorder.join(2)
        release_resolution.set()
    assert not recorder.is_alive(), "Recorder did not terminate"
    for n, f in enumerate(frames):
        bitmap = f.pop("_image")
        f["size"] = list(bitmap.size)
        f["file"] = f"frame-{n:03d}.png"
        bitmap.save(out / f["file"])
    # Preserve acquisition evidence even when geometry, cadence or action
    # assertions reject the run before presentation can be evaluated.
    (out / "acquisition.json").write_text(
        json.dumps(
            {
                "events": events,
                "frames": frames,
                "errors": errors,
                "expected_viewport": [1180, 740],
                "maximum_sampling_gap_seconds": 0.05,
            },
            indent=2,
        )
    )
    assert not app.__dict__.get("_archive_restore_reveal"), (
        "Return reveal was not retired"
    )
    assert not errors, errors
    assert not recorder.is_alive(), "Recorder did not terminate"
    assert all(f["size"] == [1180, 740] for f in frames), (
        "Viewport changed during observation"
    )
    measured = [f for f in frames if f["end"] >= 0.20]
    assert max(b["begin"] - a["begin"] for a, b in pairwise(measured)) <= 0.05
    assert max(f["end"] - f["begin"] for f in measured) <= 0.05
    assert len(events) == 4
    start = events[0]["t"]
    returned = events[2]["t"]
    before = next(f for f in reversed(frames) if f["end"] < start)
    settled = next(f for f in reversed(frames) if f["end"] < returned - 0.05)
    last = frames[-1]
    region = [{"owner": "review-content", "bbox": [260, 60, 1140, 390]}]
    # Reload after all captures; no encoding, Tk call, or capture-induced display flush during sampling.
    reference = Image.open(out / settled["file"])
    for f in frames:
        f["matches_settled_review"] = compare_unchanged_regions(
            Image.open(out / f["file"]), reference, region, region
        )[0]
    qualified = [f for f in frames if f["end"] >= start and f["begin"] < returned]
    first = next((f for f in qualified if f["matches_settled_review"]["matched"]), None)
    previous = Image.open(out / before["file"])
    boxes = content_regions(reference.size)
    for f in qualified:
        f["whole_content"] = classify_view_regions(
            Image.open(out / f["file"]), previous, reference, boxes
        )
    for f in qualified:
        if target_regions:
            bitmap = Image.open(out / f["file"])
            old_controls = compare_unchanged_regions(
                bitmap, previous, target_regions, target_regions
            )
            new_controls = compare_unchanged_regions(
                bitmap, reference, target_regions, target_regions
            )
            f["loading_controls"] = {"old": old_controls, "new": new_controls}
            f["loading_controls_complete"] = all(
                row["matched"] for row in old_controls
            ) or all(row["matched"] for row in new_controls)
    invalid = [
        f["file"]
        for f in qualified
        if not f.get("loading_controls_complete", True)
        or f["whole_content"]["status"] != "passed"
        or {"old", "new"}.issubset(
            {row["state"] for row in f["whole_content"]["regions"]}
        )
    ]
    restored = Image.open(out / last["file"])
    reverse = []
    for f in frames:
        if f["end"] < returned:
            continue
        check = classify_view_regions(
            Image.open(out / f["file"]), reference, restored, boxes
        )
        reverse.append({"file": f["file"], **check})
    reverse_invalid = [
        f["file"]
        for f in reverse
        if f["status"] != "passed"
        or {"old", "new"}.issubset({row["state"] for row in f["regions"]})
    ]
    result = {
        "reverse_invalid_frames": reverse_invalid,
        "reverse_evaluations": reverse,
        "presentation_acceptance": "failed" if invalid or reverse_invalid else "passed",
        "negative_control": fault != "none",
        "fault": fault,
        "negative_control_kind": (
            "premature_return"
            if fault == "return"
            else "premature_reveal"
            if flow == "relink"
            else "missing_loading_label"
        ),
        "target_regions": target_regions,
        "flow": flow,
        "invalid_frames": invalid,
        "input": "Scheduled direct production action then actual Back button invocation",
        "observation": "Independent Quartz own-window thread; app.mainloop without capture-driven update/update_idletasks",
        "scope": "Relink refusal or deliberately pending playback resolution and return pixels; no actual video, physical-input, Windows or package claim",
        "events": events,
        "frames": frames,
        "first_reference_match_upper_bound_ms": None
        if first is None
        else (first["end"] - start) * 1000,
        "reference_frame": settled["file"],
        "before_frame": before["file"],
        "returned_frame": last["file"],
        "errors": errors,
    }
    (out / "ordinary-loop.json").write_text(json.dumps(result, indent=2))
    assert bool(reverse_invalid) is (fault == "return"), reverse_invalid
    assert bool(invalid) is (fault == "entry"), result["invalid_frames"]
    assert first is not None, "No observed review frame before Back"
    assert not before["matches_settled_review"]["matched"], (
        "Reference did not distinguish the old view"
    )
    assert not last["matches_settled_review"]["matched"], (
        "Back did not visibly leave the review"
    )


def test_successor_review_and_tab_change_retire_pending_return(application, tmp_path):
    app = application
    seed(app, tmp_path, 1)
    app._select_focus_view("library")
    pump(app, 0.3)
    app._archive_worker.close()
    replacement = tmp_path / "replacement.mp4"
    replacement.write_bytes(b"existence only")
    app._archive_begin_relink(None, (0,), exact=str(replacement))
    pump(app, 0.3)
    first = app._archive_overlay
    assert not first._archive_reveal.active
    app._archive_cancel_relink()
    returning = app._archive_restore_reveal
    assert returning.active
    app._archive_begin_relink(None, (0,), exact=str(replacement))
    second = app._archive_overlay
    assert second is not first
    assert not first.winfo_exists() and not returning.active
    assert not app.__dict__.get("_archive_restore_reveal")
    pump(app, 0.3)
    assert not second._archive_reveal.active
    app._archive_cancel_relink()
    returning = app._archive_restore_reveal
    app._select_focus_view("watch")
    pump(app, 0.3)
    assert not returning.active and not second.winfo_exists()
    assert not app.__dict__.get("_archive_restore_reveal")
    assert app._focus_selected_view == "watch"
    assert app._archive_overlay is None
