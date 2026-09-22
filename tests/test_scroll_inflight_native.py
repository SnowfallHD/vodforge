"""Paired OS-wheel diagnostic; pixels and callbacks remain separate evidence."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from threading import Event, Thread

import pytest
from PIL import Image

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump, seed
from yt_downloader.library_artwork_source import ArtworkAsset
from yt_downloader.platforms.macos.windowing import _native_window
from yt_downloader.ui_scrolling import ScrollBinding

application = _application
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="Mac native display required",
)


@pytest.mark.parametrize(
    "surface,defer_paint",
    [
        ("library", False),
        ("watch", False),
        ("library-media", False),
        ("watch-home", False),
        ("all-runs", False),
        ("watch-home", True),
    ],
)
@pytest.mark.parametrize("scroll_sequence", ["short", "sustained"])
def test_paired_native_scroll_observations(
    application, tmp_path, monkeypatch, surface, defer_paint, scroll_sequence
):
    import Quartz
    from AppKit import NSApplication
    from quality_harness.source_identity import source_manifest

    source_root = Path(__file__).resolve().parents[1]
    identity = source_manifest(source_root)
    app = application
    sustained = scroll_sequence == "sustained"
    event_count = 240 if sustained else 48
    rows = seed(app, tmp_path, count=180)
    for index, row in enumerate(rows):
        row["channel"] = f"Channel {index:03d}"
        row["title"] = f"Episode {index:03d} - Calibrated scrolling"
        if sustained:
            row["title"] += " through mountains and forests" * 50
    app._reconcile_library_projection()
    artwork = tmp_path / "scroll-artwork.png"
    Image.effect_noise((320, 180), 50).convert("RGB").save(artwork)
    for view in (app.library_scene, app.focus_watch):
        monkeypatch.setattr(
            view,
            "_artwork_source_path",
            lambda *_args: ArtworkAsset(artwork, "thumbnail"),
        )
    app.geometry("980x600+100+80")
    app.deiconify()
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    if surface == "all-runs":
        app._select_focus_view("forge")
        menu = app.focus_run_hover_menu
        monkeypatch.setattr(menu, "records", lambda: rows)
        pump(app, 0.4)
        menu.show()
        canvas = menu.menu
    else:
        tab = surface.split("-")[0]
        app._select_focus_view(tab)
        view = app.library_scene if tab == "library" else app.focus_watch
        route = (
            "home"
            if surface == "watch-home"
            else "videos"
            if surface == "library-media"
            else "channels"
        )
        (view.navigate if tab == "library" else view._navigate)(route)
        canvas = view.canvas
    pump(app, 1.5)
    top = canvas.winfo_toplevel()
    number = int(_native_window(top).windowNumber())
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionIncludingWindow, number
    )
    bounds = next(
        dict(w["kCGWindowBounds"])
        for w in windows
        if int(w["kCGWindowNumber"]) == number
    )
    region = (
        canvas.winfo_rootx() - bounds["X"],
        canvas.winfo_rooty() - bounds["Y"],
        canvas.winfo_width(),
        canvas.winfo_height(),
    )
    x, y = (
        canvas.winfo_rootx() + canvas.winfo_width() // 2,
        canvas.winfo_rooty() + canvas.winfo_height() // 2,
    )
    move = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventMouseMoved, (x, y), Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
    pump(app, 0.2)
    assert canvas.winfo_exists() and canvas.winfo_ismapped()
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path))) / (
        surface
        + ("-deferred-paint" if defer_paint else "")
        + ("-sustained" if sustained else "")
    )
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    events, handled, frames, samples, errors = [], [], [], [], []
    heartbeat, renders, injected_delays = [], [], []
    stop = Event()
    original = ScrollBinding._move

    def observed(binding, axis, pixels):
        if binding.scroller is not canvas:
            return original(binding, axis, pixels)
        begin = time.monotonic() - started
        before = canvas.canvasy(0)
        if defer_paint and not injected_delays:
            # Force one real delayed scroll response, independent of whether
            # this Tk runtime needs the optional presentation helper.
            delay_start = time.monotonic() - started
            time.sleep(0.25)
            injected_delays.append(
                {
                    "begin": delay_start,
                    "end": time.monotonic() - started,
                    "scope": "first target scroll callback before movement",
                }
            )
        original(binding, axis, pixels)
        handled.append(
            {
                "begin": begin,
                "end": time.monotonic() - started,
                "axis": axis,
                "pixels": pixels,
                "before": before,
                "after": canvas.canvasy(0),
            }
        )

    monkeypatch.setattr(ScrollBinding, "_move", observed)

    def capture():
        try:
            while not stop.is_set():
                begin = time.monotonic() - started
                raw = Quartz.CGWindowListCreateImage(
                    Quartz.CGRectNull,
                    Quartz.kCGWindowListOptionIncludingWindow,
                    number,
                    Quartz.kCGWindowImageBoundsIgnoreFraming
                    | Quartz.kCGWindowImageNominalResolution,
                )
                if raw is None:
                    raise RuntimeError("Own-window capture unavailable")
                scale = Quartz.CGImageGetWidth(raw) / bounds["Width"]
                left, upper, width, height = region
                raw = Quartz.CGImageCreateWithImageInRect(
                    raw,
                    ((left * scale, upper * scale), (width * scale, height * scale)),
                )
                data = bytes(
                    Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(raw))
                )
                image = Image.frombytes(
                    "RGB",
                    (Quartz.CGImageGetWidth(raw), Quartz.CGImageGetHeight(raw)),
                    data,
                    "raw",
                    "BGRX",
                    Quartz.CGImageGetBytesPerRow(raw),
                )
                image.thumbnail((360, 240))
                name = f"frame-{len(frames):03d}.png"
                image.save(output / name, compress_level=0)
                frames.append(
                    {
                        "begin": begin,
                        "end": time.monotonic() - started,
                        "sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                        "file": name,
                    }
                )
                stop.wait(max(0, 1 / 60 - (time.monotonic() - started - begin)))
        except Exception as exc:  # noqa: BLE001 - retain observer failure and fail the test
            errors.append({"observer": "own-window-pixels", "error": repr(exc)})

    def driver():
        try:
            time.sleep(0.15)
            schedule_start = time.monotonic()
            for index in range(event_count):
                due = schedule_start + index / 60
                time.sleep(max(0, due - time.monotonic()))
                pixels = 12 if sustained and index >= 160 else -12
                event = Quartz.CGEventCreateScrollWheelEvent(
                    None, Quartz.kCGScrollEventUnitPixel, 1, pixels
                )
                Quartz.CGEventSetLocation(event, (x, y))
                stamp = time.monotonic() - started
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                events.append(
                    {"t": stamp, "index": index, "pixels": pixels, "due": due - started}
                )
            time.sleep(0.3)
        except Exception as exc:  # noqa: BLE001 - retain observer failure and fail the test
            errors.append({"observer": "input-driver", "error": repr(exc)})

    heartbeat_token = None

    def beat():
        nonlocal heartbeat_token
        heartbeat.append({"t": time.monotonic() - started, "offset": canvas.canvasy(0)})
        if not stop.is_set():
            heartbeat_token = app.after(8, beat)

    beat()
    if surface != "all-runs":
        draw = view._render

        def observed_render():
            begin = time.monotonic() - started
            draw()
            renders.append({"begin": begin, "end": time.monotonic() - started})

        monkeypatch.setattr(view, "_render", observed_render)

    recorder = Thread(target=capture, daemon=True)
    worker = Thread(target=driver, daemon=True)
    recorder.start()
    worker.start()
    deadline = time.monotonic() + 10

    def service():
        samples.append({"t": time.monotonic() - started, "offset": canvas.canvasy(0)})
        if worker.is_alive() and time.monotonic() < deadline:
            app.after(2, service)
        else:
            app.quit()

    app.after(0, service)
    app.mainloop()
    worker.join(1)
    stop.set()
    recorder.join(2)
    if heartbeat_token is not None:
        app.after_cancel(heartbeat_token)
    receipt = {
        "surface": surface,
        "mutation": "blocked-scroll-callback" if defer_paint else None,
        "injected_delays": injected_delays,
        "source_manifest_sha256": identity["sha256"],
        "source_manifest": identity,
        "source_manifest_unchanged": source_manifest(source_root)["sha256"]
        == identity["sha256"],
        "input": f"OS-injected pixel wheel, {event_count} x 12 at nominal 60Hz",
        "scroll_sequence": scroll_sequence,
        "events": events,
        "handled": handled,
        "frames": frames,
        "samples": samples,
        "errors": errors,
        "source_file": str(Path(__file__).resolve()),
        "event_loop": "Tk.mainloop",
        "heartbeat": heartbeat,
        "renders": renders,
        "limits": [
            "Diagnostic baseline; no smoothness acceptance from completion.",
            "Window-server snapshots are sampled, not display-refresh timestamps.",
            "Capture/save overhead is retained per frame; same instrumentation for all views.",
        ],
        "completed": not worker.is_alive() and not recorder.is_alive(),
    }
    from quality_harness.scroll_observations import evaluate_scroll_observations

    receipt["evaluation"] = evaluate_scroll_observations(receipt)
    (output / "scroll-observations.json").write_text(json.dumps(receipt, indent=2))
    if surface == "all-runs":
        app.focus_run_hover_menu.close()
    assert receipt["source_manifest_unchanged"]
    if defer_paint:
        assert len(injected_delays) == 1
        assert injected_delays[0]["end"] - injected_delays[0]["begin"] >= 0.25
        assert receipt["evaluation"]["status"] == "failed", receipt["evaluation"]
        assert not receipt["evaluation"]["assertions"][
            "first_pixel_change_within_100ms"
        ]
    else:
        assert receipt["evaluation"]["status"] == "passed", receipt["evaluation"]
    assert receipt["completed"] and not errors, errors
    assert len(events) == event_count and len(handled) >= 3 and len(frames) >= 3
    if sustained:
        # Independent observed positions must show actual travel in both directions.
        offsets = [sample["offset"] for sample in samples]
        assert max(offsets) - offsets[-1] > 100
        assert any(move["after"] > move["before"] for move in handled)
        assert any(move["after"] < move["before"] for move in handled)
    assert max(s["offset"] for s in samples) - min(s["offset"] for s in samples) > 100
