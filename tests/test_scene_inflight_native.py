"""Temporal source-native regression: actual Channels, isolated synthetic media."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from itertools import pairwise
from pathlib import Path
from threading import Event, Thread

import pytest
from PIL import Image, ImageDraw

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump, seed
from yt_downloader.library_artwork_source import ArtworkAsset
from yt_downloader.platforms.macos.windowing import _native_window

logger = logging.getLogger(__name__)

application = _application

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="Mac source-native OS-injected interaction required",
)


@pytest.mark.parametrize("surface", ["library", "watch"])
@pytest.mark.parametrize("rendering", ["live", "disabled"])
def test_channels_artwork_and_layout_during_resize(
    application, tmp_path, monkeypatch, surface, rendering
):
    """Retain all violations even if final redraw repairs the visible scene."""
    import Quartz
    from AppKit import NSApplication, NSNotificationCenter
    from quality_harness.source_identity import source_manifest

    checkout = Path(__file__).resolve().parents[1]
    source_before = source_manifest(checkout)
    app = application
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path))) / (
        surface if rendering == "live" else surface + "-render-disabled"
    )
    output.mkdir(parents=True, exist_ok=True)
    # Nonuniform aspect markers make repeated/cropped artwork distinguishable.
    path = tmp_path / "calibrated.png"
    bitmap = Image.new("RGB", (640, 360), "#16334d")
    draw = ImageDraw.Draw(bitmap)
    for x in range(0, 640, 40):
        draw.line((x, 0, x, 359), fill="#f5df56", width=3)
    for y in range(0, 360, 40):
        draw.line((0, y, 639, y), fill="#dc657b", width=3)
    draw.ellipse((240, 100, 400, 260), outline="white", width=8)
    bitmap.save(path)
    rows = seed(app, tmp_path, count=40)
    for i, row in enumerate(rows):
        row["channel"] = f"Calibrated channel {i // 3}"
    app._reconcile_library_projection()
    scene = app.library_scene if surface == "library" else app.focus_watch

    def resolve(_row, _size, _role, cancelled):
        # Real worker, deterministic delayed local fallback; no provider network.
        cancelled.wait(0.018)
        return ArtworkAsset(path, "thumbnail")

    monkeypatch.setattr(scene, "_artwork_source_path", resolve)
    app._select_focus_view(surface)
    if surface == "library":
        scene.navigate("channels")
    else:
        scene._navigate("channels")
    app.geometry("980x600+100+80")
    app.deiconify()
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    pump(app, 2)
    started = time.monotonic()
    events, renders, windows, errors = [], [], [], []
    configurations = []
    native_frames = []
    lifecycle, pixel_frames = [], []
    capture_mode = os.environ.get("VODFORGE_RESIZE_CAPTURE_PIXELS", "0")
    assert capture_mode in {"0", "1", "process"}
    capture_pixels = capture_mode != "0"
    observer_stop = Event()
    released = Event()
    pointer_pattern = os.environ.get("VODFORGE_RESIZE_POINTER_PATTERN", "moving")
    assert pointer_pattern in {"moving", "stationary"}
    scene.canvas.bind(
        "<Configure>",
        lambda event: configurations.append(
            {
                "t": time.monotonic() - started,
                "width": event.width,
                "height": event.height,
            }
        ),
        add="+",
    )
    original = scene._render if rendering == "live" else lambda: None

    def sample(phase):
        canvas = scene.canvas
        images = [
            {"id": i, "bbox": canvas.bbox(i), "image": canvas.itemcget(i, "image")}
            for i in canvas.find_withtag("presentation-artwork")
        ]
        overlaps = []
        for index, a in enumerate(images):
            for b in images[index + 1 :]:
                x, y, right, bottom = a["bbox"]
                bx, by, br, bb = b["bbox"]
                if min(right, br) > max(x, bx) and min(bottom, bb) > max(y, by):
                    overlaps.append([a["id"], b["id"]])
        renders.append(
            {
                "t": time.monotonic() - started,
                "phase": phase,
                "canvas_width": canvas.winfo_width(),
                "scrollregion": str(canvas.cget("scrollregion")),
                "layout_width": float(
                    canvas.tk.splitlist(canvas.cget("scrollregion"))[2]
                ),
                "revision": scene._artwork_revision,
                "images": images,
                "overlapping_artwork": overlaps,
            }
        )

    def render():
        begin = time.monotonic()
        original()
        sample("render")
        renders[-1]["duration_ms"] = (time.monotonic() - begin) * 1000

    monkeypatch.setattr(scene, "_render", render)
    sample("before")
    native_window = _native_window(app)
    number = int(native_window.windowNumber())

    def bounds():
        values = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionIncludingWindow, number
        )
        return dict(
            next(w for w in values if int(w["kCGWindowNumber"]) == number)[
                "kCGWindowBounds"
            ]
        )

    center = NSNotificationCenter.defaultCenter()

    def native_note(note):
        frame = native_window.frame()
        lifecycle.append(
            {
                "t": time.monotonic() - started,
                "kind": str(note.name()),
                "width": float(frame.size.width),
                "height": float(frame.size.height),
                "in_live_resize": bool(native_window.inLiveResize()),
            }
        )

    tokens = [
        center.addObserverForName_object_queue_usingBlock_(
            name, native_window, None, native_note
        )
        for name in (
            "NSWindowWillStartLiveResizeNotification",
            "NSWindowDidResizeNotification",
            "NSWindowDidEndLiveResizeNotification",
        )
    ]

    def capture():
        # Keep native captures in memory during input; PNG writing follows the
        # gesture so disk/compression cannot delay event processing.
        try:
            while not observer_stop.is_set():
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
                data = bytes(
                    Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(raw))
                )
                bitmap = Image.frombytes(
                    "RGB",
                    (Quartz.CGImageGetWidth(raw), Quartz.CGImageGetHeight(raw)),
                    data,
                    "raw",
                    "BGRX",
                    Quartz.CGImageGetBytesPerRow(raw),
                )
                pixel_frames.append(
                    {
                        "begin": begin,
                        "end": time.monotonic() - started,
                        "bitmap": bitmap,
                    }
                )
                observer_stop.wait(max(0, 0.020 - (time.monotonic() - started - begin)))
        except Exception as exc:  # noqa: BLE001 - unavailable capture never passes
            errors.append("pixels: " + repr(exc))

    initial = bounds()

    def post(kind, x, y, phase):
        event = Quartz.CGEventCreateMouseEvent(
            None, kind, (float(x), float(y)), Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventSetFlags(event, 0)
        post_started = time.monotonic()
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        events.append(
            {
                "t": time.monotonic() - started,
                "phase": phase,
                "x": x,
                "y": y,
                "post_started": post_started - started,
                "post_ms": (time.monotonic() - post_started) * 1000,
                "event_timestamp_ns": int(Quartz.CGEventGetTimestamp(event)),
                "event_timestamp_available": bool(Quartz.CGEventGetTimestamp(event)),
            }
        )

    def observer():
        # Independent of input scheduling. CGWindowList can be slow: record its
        # interval rather than treating completion time as instantaneous truth.
        try:
            while not observer_stop.is_set():
                begin = time.monotonic()
                button = bool(
                    Quartz.CGEventSourceButtonState(
                        Quartz.kCGEventSourceStateCombinedSessionState,
                        Quartz.kCGMouseButtonLeft,
                    )
                )
                button_sample_ended = time.monotonic()
                geometry = bounds()
                end = time.monotonic()
                windows.append(
                    {
                        "t": end - started,
                        "sample_started": begin - started,
                        "sample_ms": (end - begin) * 1000,
                        "button_sample_started": begin - started,
                        "button_sample_ended": button_sample_ended - started,
                        "phase": "released" if released.is_set() else "pressed",
                        "bounds": geometry,
                        "button": button,
                    }
                )
                observer_stop.wait(max(0, 0.010 - (time.monotonic() - begin)))
        except Exception as exc:  # noqa: BLE001 - observer faults invalidate evidence
            errors.append("observer: " + repr(exc))

    def wait_until(deadline):
        time.sleep(max(0, deadline - time.monotonic()))

    def driver():
        try:
            x = initial["X"] + initial["Width"] - 2
            y = initial["Y"] + initial["Height"] - 2
            post(Quartz.kCGEventMouseMoved, x, y, "position")
            time.sleep(0.15)
            post(Quartz.kCGEventLeftMouseDown, x, y, "press")
            drag_started = time.monotonic()
            for step in range(1, 25):
                wait_until(drag_started + (step - 1) * 0.045)
                post(
                    Quartz.kCGEventLeftMouseDragged, x + step * 8, y + step * 2, "drag"
                )
            wait_until(drag_started + 24 * 0.045)
            post(Quartz.kCGEventLeftMouseUp, x + 192, y + 48, "release")
            released.set()
            free_started = time.monotonic()
            for step in range(16):
                wait_until(free_started + step * 0.045)
                dx, dy = (step * 5, step * 3) if pointer_pattern == "moving" else (0, 0)
                post(
                    Quartz.kCGEventMouseMoved,
                    x + 192 - dx,
                    y + 48 - dy,
                    "free-pointer",
                )
            wait_until(free_started + 16 * 0.045)
        except Exception as exc:  # noqa: BLE001 - preserve driver failure; never qualify as product evidence
            errors.append(repr(exc))
        finally:
            post(
                Quartz.kCGEventLeftMouseUp,
                initial["X"] + 20,
                initial["Y"] + 20,
                "cleanup-release",
            )

    capture_process = None
    if capture_mode == "process":
        capture_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "quality_harness.window_capture",
                str(number),
                str(started),
                str(output),
            ]
        )
        ready_deadline = time.monotonic() + 5
        while (
            not (output / "capture.ready").exists()
            and time.monotonic() < ready_deadline
        ):
            if capture_process.poll() is not None:
                break
            time.sleep(0.01)
        if not (output / "capture.ready").exists():
            (output / "capture.stop").touch()
            capture_process.wait(timeout=10)
            for token in tokens:
                center.removeObserver_(token)
            pytest.fail("Independent recorder failed to capture a baseline")
    recorder = Thread(target=capture, daemon=True) if capture_mode == "1" else None
    if recorder is not None:
        recorder.start()
    sampler = Thread(target=observer, daemon=True)
    sampler.start()
    native_profile = None
    if os.environ.get("VODFORGE_RESIZE_SAMPLE_STACKS") == "1":
        native_profile = subprocess.Popen(
            [
                "/usr/bin/sample",
                str(os.getpid()),
                "2",
                "1",
                "-file",
                str(output / "native-stacks.txt"),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    worker = Thread(target=driver, daemon=True)
    worker.start()
    gaps = []
    previous = time.monotonic()
    deadline = previous + 15

    def service():
        nonlocal previous
        now = time.monotonic()
        gaps.append((now - previous) * 1000)
        previous = now
        frame = native_window.frame()
        native_frames.append(
            {
                "t": time.monotonic() - started,
                "width": float(frame.size.width),
                "height": float(frame.size.height),
            }
        )
        if worker.is_alive() and now < deadline:
            app.after(5, service)
        else:
            app.quit()

    app.after(0, service)
    try:
        app.mainloop()
    finally:
        worker.join(1)
        observer_stop.set()
        sampler.join(1)
        if recorder is not None:
            recorder.join(2)
        if capture_process is not None:
            (output / "capture.stop").touch()
            try:
                capture_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                capture_process.kill()
                capture_process.wait()
                errors.append("Independent recorder did not stop")
            if capture_process.returncode != 0:
                errors.append("Independent recorder exited unsuccessfully")
            capture_report = output / "capture.json"
            if capture_report.exists():
                captured = json.loads(capture_report.read_text())
                pixel_frames.extend(captured["frames"])
                errors.extend(captured["errors"])
            else:
                errors.append("Independent recorder report missing")
        for token in tokens:
            center.removeObserver_(token)
    if native_profile is not None:
        native_profile.wait(timeout=10)
    import hashlib

    for index, pixel in enumerate(pixel_frames):
        if "bitmap" not in pixel:
            continue
        bitmap = pixel.pop("bitmap")
        name = f"resize-frame-{index:04d}.png"
        pixel.update(
            {
                "file": name,
                "size": list(bitmap.size),
                "sha256": hashlib.sha256(bitmap.tobytes()).hexdigest(),
            }
        )
        bitmap.save(output / name, compress_level=0)
    pump(app, 1)
    sample("after")
    press = next(e["t"] for e in events if e["phase"] == "press")
    release = next(e["t"] for e in events if e["phase"] == "release")
    in_flight = [r for r in renders if press < r["t"] < release]
    source_after = source_manifest(checkout)
    final_drag = next(e for e in reversed(events) if e["phase"] == "drag")
    expected_size = (initial["Width"] + 192, initial["Height"] + 48)
    first_final = next(
        (
            w
            for w in windows
            if (w["bounds"]["Width"], w["bounds"]["Height"]) == expected_size
        ),
        None,
    )
    pressed_samples = [
        w for w in windows if w["button"] and w["sample_started"] >= press
    ]
    last_pressed = pressed_samples[-1] if pressed_samples else None
    observed_up = next(
        (
            w
            for w in windows
            if last_pressed is not None
            and w["button_sample_started"] >= last_pressed["button_sample_ended"]
            and not w["button"]
        ),
        None,
    )
    from quality_harness.resize_observations import released_geometry_samples

    observed_release_geometry = released_geometry_samples(windows, observed_up)
    native_end = next(
        (
            row
            for row in lifecycle
            if row["kind"] == "NSWindowDidEndLiveResizeNotification"
        ),
        None,
    )
    native_release_geometry = [
        row
        for row in windows
        if native_end is not None and row["sample_started"] >= native_end["t"]
    ]
    checks = {
        "observed_button_press_and_release": last_pressed is not None
        and observed_up is not None,
        "stable_after_observed_button_up": len(
            {tuple(sorted(w["bounds"].items())) for w in observed_release_geometry}
        )
        == 1,
        "native_resize_end_observed": native_end is not None,
        "stable_after_native_resize_end": bool(native_release_geometry)
        and len({tuple(sorted(w["bounds"].items())) for w in native_release_geometry})
        == 1,
        "source_unchanged": source_before["sha256"] == source_after["sha256"],
        "calibrated_artwork_observed": any(len(r["images"]) >= 2 for r in renders),
        "driver_completed": not worker.is_alive()
        and not sampler.is_alive()
        and (recorder is None or not recorder.is_alive())
        and not errors,
        "actual_window_resize": any(
            w["bounds"]["Width"] > initial["Width"] + 60 for w in windows
        ),
        "content_adapts_while_pressed": len(
            {
                r["layout_width"]
                for r in in_flight
                if abs(r["layout_width"] - (r["canvas_width"] - 4)) <= 1
            }
        )
        >= 3,
        "no_overlapping_artwork_at_any_observed_render": not any(
            r["overlapping_artwork"] for r in renders
        ),
        "released_window_stops": len(
            {
                tuple(sorted(w["bounds"].items()))
                for w in windows
                if w["sample_started"] >= release
            }
        )
        == 1,
    }
    report = {
        "input": "OS-injected; not physical input or presented-frame proof",
        "surface": surface,
        "rendering": rendering,
        "source": str(Path(__file__).resolve()),
        "source_before": source_before,
        "source_after": source_after,
        "runtime": {"python": sys.version, "tk": app.tk.call("info", "patchlevel")},
        "release_observations": {
            "last_drag_posted": final_drag["t"],
            "release_posted": release,
            "last_observed_button_pressed": last_pressed,
            "first_observed_button_released": observed_up,
            "os_release_transition_interval": (
                [
                    last_pressed["button_sample_started"],
                    observed_up["button_sample_ended"],
                ]
                if last_pressed is not None and observed_up is not None
                else None
            ),
            "expected_final_size_from_input": expected_size,
            "first_final_size_sample": first_final,
            "first_final_sample_after_release_ms": (
                (first_final["t"] - release) * 1000 if first_final else None
            ),
            "interpretation": "Sampling completion is an observation bound, not actual presentation time. Post-release geometry changes alone do not establish pointer-follow.",
        },
        "events": events,
        "windows": windows,
        "renders": renders,
        "configurations": configurations,
        "native_frames": native_frames,
        "native_lifecycle": lifecycle,
        "pixel_frames": pixel_frames,
        "pixel_capture_enabled": capture_pixels,
        "pixel_capture_mode": capture_mode,
        "pixel_capture_assessment": {
            "status": "diagnostic_only",
            "reason": "Continuous samples retained for review; no claim of zero unsampled changes.",
            "maximum_gap_ms": max(
                ((b["begin"] - a["begin"]) * 1000 for a, b in pairwise(pixel_frames)),
                default=None,
            ),
            "maximum_capture_ms": max(
                ((row["end"] - row["begin"]) * 1000 for row in pixel_frames),
                default=None,
            ),
        },
        "pixel_capture_scope": "Sampled own-window server images, not display-refresh timestamps; hover may legitimately change pixels.",
        "pointer_pattern": pointer_pattern,
        "clock_origin_monotonic": started,
        "observer": "Independent 10ms target; actual sample duration/gaps recorded. Shared-process scheduling can still perturb delivery.",
        "pump_gaps_ms": gaps,
        "errors": errors,
        "checks": checks,
        "limits": [
            "Canvas state is not compositor frame evidence.",
            "One lower-right outward drag; other edges and reverse loads remain unproven.",
            "No latency threshold is asserted by this diagnostic.",
            "Posted input is not an acknowledgement that AppKit processed it.",
            "Native frame and Canvas commit are not compositor presentation.",
            "Geometry starts after the button-state read; include the first observed-up geometry. Samples spanning posted release remain excluded from posted-release assertion.",
            "Combined-session button state includes injected input; it is not physical-device proof.",
        ],
    }
    (output / "channels-inflight.json").write_text(json.dumps(report, indent=2))
    from yt_downloader.platform_services import capture_own_widget

    capture = capture_own_widget(scene)
    if capture is not None:
        capture.save(output / "channels-inflight-after.png")
    if rendering == "disabled":
        assert checks["source_unchanged"] and checks["calibrated_artwork_observed"]
        assert checks["observed_button_press_and_release"]
        assert checks["driver_completed"] and checks["actual_window_resize"]
        assert not checks["content_adapts_while_pressed"], (
            "Negative control escaped: viewport changes were mistaken for content rendering"
        )
    else:
        assert all(checks.values()), {k: v for k, v in checks.items() if not v}


def test_sidebar_position_events_do_not_rebuild_current_pixels(
    application, monkeypatch
):
    app = application
    app._select_focus_view("library")
    scene = app.library_scene
    pump(app, 0.2)
    calls = []
    original = scene._draw_sidebar

    def draw():
        calls.append(True)
        original()

    monkeypatch.setattr(scene, "_draw_sidebar", draw)
    width, height = scene.sidebar.winfo_width(), scene.sidebar.winfo_height()
    scene.sidebar.event_generate("<Configure>", width=width, height=height)
    calls.clear()
    for position in range(20):
        scene.sidebar.event_generate(
            "<Configure>", x=position, y=position, width=width, height=height
        )
    assert calls == [], "Position-only native Configure replayed sidebar rasterization"
    before = scene.sidebar.find_all()
    old_box = scene._sidebar_targets[-1][0]
    old_y = scene._sidebar_storage_y
    scene.sidebar.event_generate("<Configure>", width=width, height=height + 10)
    delta = max(343, height + 10 - 141) - old_y
    assert calls == [] and scene.sidebar.find_all() == before
    assert scene._sidebar_targets[-1][0] == (
        old_box[0],
        old_box[1] + delta,
        old_box[2],
        old_box[3] + delta,
    ), "Storage hit target must follow its pixels"
    assert scene.sidebar.coords("sidebar-divider")[-1] == height + 10
    scene.navigate("channels")
    assert len(calls) == 1, "Navigation must refresh even when geometry is unchanged"


@pytest.mark.parametrize("surface", ["library", "watch"])
@pytest.mark.parametrize(
    "edge,focus_loss",
    [
        ("lower_right", False),
        ("left", False),
        ("bottom", False),
        ("lower_right", True),
    ],
)
def test_resize_release_reentry_does_not_retain_drag(
    application, tmp_path, surface, edge, focus_loss
):
    """Separate retained-drag oracle; does not waive delayed-completion failures."""
    import tkinter as tk

    import Quartz
    from AppKit import NSApplication, NSNotificationCenter
    from quality_harness.source_identity import source_manifest

    app = application
    checkout = Path(__file__).resolve().parents[1]
    before = source_manifest(checkout)
    rows = seed(app, tmp_path, count=40)
    for i, row in enumerate(rows):
        row["channel"] = f"Release channel {i // 3}"
    app._reconcile_library_projection()
    app._select_focus_view(surface)
    scene = app.library_scene if surface == "library" else app.focus_watch
    if surface == "library":
        scene.navigate("channels")
    else:
        scene._navigate("channels")
    app.geometry("980x600+260+80")
    app.deiconify()
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    pump(app, 0.8)
    native = _native_window(app)
    number = int(native.windowNumber())
    origin = time.monotonic()
    events, samples, lifecycle, errors, pointers = [], [], [], [], []
    ended, stop, done = Event(), Event(), Event()
    center = NSNotificationCenter.defaultCenter()

    def bounds():
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionIncludingWindow, number
        )
        return dict(
            next(w for w in windows if int(w["kCGWindowNumber"]) == number)[
                "kCGWindowBounds"
            ]
        )

    def resize_ended(note):
        lifecycle.append({"t": time.monotonic() - origin, "kind": "native_resize_end"})
        ended.set()

    token = center.addObserverForName_object_queue_usingBlock_(
        "NSWindowDidEndLiveResizeNotification", native, None, resize_ended
    )
    helper = None
    focus_tokens = []
    focus_observations = []
    if focus_loss:
        helper = tk.Toplevel(app)
        helper.title("VODForge isolated focus target")
        helper.geometry("180x120+40+100")
        pump(app, 0.1)
        other_native = _native_window(helper)
        native.makeKeyAndOrderFront_(None)
        pump(app, 0.1)
        assert native.isKeyWindow(), "Target window must own focus before the drag"
        resize_count = [0]

        def lose_focus(note):
            if native.inLiveResize():
                resize_count[0] += 1
                if resize_count[0] == 3:
                    other_native.makeKeyAndOrderFront_(None)
                    focus_observations.append(
                        {
                            "t": time.monotonic() - origin,
                            "kind": "controlled_native_focus_transfer",
                            "target_is_key": bool(native.isKeyWindow()),
                            "helper_is_key": bool(other_native.isKeyWindow()),
                            "button": bool(
                                Quartz.CGEventSourceButtonState(
                                    Quartz.kCGEventSourceStateCombinedSessionState,
                                    Quartz.kCGMouseButtonLeft,
                                )
                            ),
                        }
                    )

        focus_tokens.append(
            center.addObserverForName_object_queue_usingBlock_(
                "NSWindowDidResizeNotification", native, None, lose_focus
            )
        )
    initial = bounds()
    x, y, w, h = (initial[k] for k in ("X", "Y", "Width", "Height"))
    start = {
        "lower_right": (x + w - 3, y + h - 3),
        "left": (x + 2, y + h / 2),
        "bottom": (x + w / 2, y + h - 2),
    }[edge]
    delta = {"lower_right": (16, 6), "left": (-16, 0), "bottom": (0, 6)}[edge]
    last = start

    def post(kind, point, phase):
        nonlocal last
        last = point
        event = Quartz.CGEventCreateMouseEvent(
            None, kind, point, Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventSetFlags(event, 0)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        events.append(
            {
                "t": time.monotonic() - origin,
                "phase": phase,
                "point": point,
                "kind": int(kind),
            }
        )

    def sample():
        try:
            while not stop.is_set():
                begin = time.monotonic() - origin
                button = bool(
                    Quartz.CGEventSourceButtonState(
                        Quartz.kCGEventSourceStateCombinedSessionState,
                        Quartz.kCGMouseButtonLeft,
                    )
                )
                button_end = time.monotonic() - origin
                geometry = bounds()
                samples.append(
                    {
                        "sample_started": begin,
                        "t": time.monotonic() - origin,
                        "button_sample_ended": button_end,
                        "button": button,
                        "bounds": geometry,
                    }
                )
                stop.wait(0.01)
        except Exception as exc:
            logger.exception("Native retained-drag driver or observer failed")
            errors.append(type(exc).__name__)

    def sample_pointer():
        try:
            while not stop.is_set():
                begin = time.monotonic() - origin
                pointer = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
                pointers.append(
                    {
                        "sample_started": begin,
                        "t": time.monotonic() - origin,
                        "pointer": [float(pointer.x), float(pointer.y)],
                    }
                )
                stop.wait(0.02)
        except Exception as exc:
            logger.exception("Native cursor observer failed")
            errors.append(type(exc).__name__)

    def drive():
        try:
            post(Quartz.kCGEventMouseMoved, start, "position")
            time.sleep(0.15)
            post(Quartz.kCGEventLeftMouseDown, start, "press")
            for step in range(1, 9):
                time.sleep(0.06)
                post(
                    Quartz.kCGEventLeftMouseDragged,
                    (start[0] + delta[0] * step, start[1] + delta[1] * step),
                    "drag",
                )
            # Release outside the original window without a second button press.
            outside = (x - 35, y - 25)
            post(Quartz.kCGEventLeftMouseUp, outside, "release_outside")
            end_observed = ended.wait(1)
            events.append(
                {
                    "t": time.monotonic() - origin,
                    "phase": "native_end_wait",
                    "observed": end_observed,
                }
            )
            current = bounds()
            cx, cy, cw, ch = (current[k] for k in ("X", "Y", "Width", "Height"))
            route = [
                (cx + cw - 2, cy + ch - 2),
                (cx + cw + 40, cy + ch + 40),
                (cx + 2, cy + ch / 2),
                (cx - 35, cy + ch / 2),
                (cx + cw / 2, cy + ch - 2),
                (cx + cw / 2, cy + ch + 35),
                (cx + cw / 2, cy + ch / 2),
            ]
            for point in route:
                post(Quartz.kCGEventMouseMoved, point, "free_reentry")
                time.sleep(0.08)
            time.sleep(0.15)
        except Exception as exc:
            logger.exception("Native retained-drag driver or observer failed")
            errors.append(type(exc).__name__)
        finally:
            post(Quartz.kCGEventLeftMouseUp, last, "cleanup_release")
            done.set()

    sampler = Thread(target=sample, daemon=True)
    driver = Thread(target=drive, daemon=True)
    cursor_sampler = Thread(target=sample_pointer, daemon=True)
    sampler.start()
    cursor_sampler.start()
    driver.start()
    try:
        deadline = time.monotonic() + 6
        while not done.is_set() and time.monotonic() < deadline:
            app.update()
            time.sleep(0.005)
        driver.join(1)
        pump(app, 0.1)
    finally:
        stop.set()
        sampler.join(1)
        cursor_sampler.join(1)
        center.removeObserver_(token)
        for focus_token in focus_tokens:
            center.removeObserver_(focus_token)
        if helper is not None:
            helper.destroy()
    free = [e for e in events if e["phase"] == "free_reentry"]
    window_states = [s for s in samples if free and s["sample_started"] >= free[0]["t"]]
    sample_gaps = [
        (b["t"] - a["sample_started"]) * 1000 for a, b in pairwise(window_states)
    ]
    checks = {
        "free_reentry_observation_complete": bool(free and window_states)
        and len(window_states) >= 2
        and window_states[-1]["sample_started"] >= free[-1]["t"] + 0.1
        and bool(sample_gaps)
        and max(sample_gaps) <= 50,
        "source_unchanged": before["sha256"] == source_manifest(checkout)["sha256"],
        "driver_completed": not driver.is_alive()
        and not sampler.is_alive()
        and not cursor_sampler.is_alive()
        and not errors,
        "native_resize_ended_before_free_reentry": bool(
            lifecycle and free and lifecycle[-1]["t"] <= free[0]["t"]
        ),
        "actual_resize": any(
            abs(s["bounds"]["Width"] - w) >= 40 or abs(s["bounds"]["Height"] - h) >= 20
            for s in samples
        ),
        "press_observed": any(s["button"] for s in samples),
        "seven_free_reentries": len(free) == 7,
        "free_pointer_positions_observed": bool(free)
        and all(
            any(
                s["sample_started"] >= event["t"]
                and abs(s["pointer"][0] - event["point"][0]) <= 2
                and abs(s["pointer"][1] - event["point"][1]) <= 2
                for s in pointers
            )
            for event in free
        ),
        "released_during_free_reentry": bool(window_states)
        and not any(s["button"] for s in window_states),
        "no_retained_drag_after_native_end": bool(window_states)
        and len({tuple(sorted(s["bounds"].items())) for s in window_states}) == 1,
    }
    if focus_loss:
        checks["focus_lost_while_button_pressed"] = any(
            row["button"] and not row["target_is_key"] and row["helper_is_key"]
            for row in focus_observations
        )
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    (output / f"release-reentry-{surface}-{edge}-focus-{focus_loss}.json").write_text(
        json.dumps(
            {
                "scope": "OS-injected outside release and seven free reentries; no second click; optional controlled native focus transfer, not physical-input or delayed-completion acceptance",
                "focus_transfer": focus_observations,
                "source_before": before,
                "source_after": source_manifest(checkout),
                "clock_origin_monotonic": origin,
                "window_number": number,
                "process_id": os.getpid(),
                "initial": initial,
                "events": events,
                "samples": samples,
                "pointer_samples": pointers,
                "free_sample_gaps_ms": sample_gaps,
                "lifecycle": lifecycle,
                "errors": errors,
                "checks": checks,
            },
            indent=2,
        )
    )
    assert all(checks.values()), {k: v for k, v in checks.items() if not v}


@pytest.mark.parametrize("surface", ["library", "watch"])
@pytest.mark.parametrize("wrong_owner", [False, True])
def test_distinct_artwork_pixels_during_stepped_resize(
    application, tmp_path, monkeypatch, surface, wrong_owner
):
    """Bounded presented identity; separate from the unchanged fast resize gates."""
    _exercise_artwork_during_resize(
        application, tmp_path, monkeypatch, surface, wrong_owner=wrong_owner
    )


@pytest.mark.parametrize("surface", ["library", "watch"])
@pytest.mark.parametrize("distorted", [False, True])
def test_artwork_aspect_during_stepped_resize(
    application, tmp_path, monkeypatch, surface, distorted
):
    """Cover-fit geometry must remain correct before, during and after resize."""
    _exercise_artwork_during_resize(
        application, tmp_path, monkeypatch, surface, aspect=True, distorted=distorted
    )


@pytest.mark.parametrize("wrong_owner", [False, True])
def test_watch_hero_artwork_during_stepped_resize(
    application, tmp_path, monkeypatch, wrong_owner
):
    """Hero artwork must remain visible while its viewport dimensions change."""
    _exercise_artwork_during_resize(
        application, tmp_path, monkeypatch, "watch", wrong_owner=wrong_owner, hero=True
    )


@pytest.mark.parametrize("surface", ["library", "watch"])
@pytest.mark.parametrize("distorted", [False, True])
def test_artwork_pixels_during_fast_resize(
    application, tmp_path, monkeypatch, surface, distorted
):
    """The fast input cadence must not hide broken pixels behind correct bounds."""
    _exercise_artwork_during_resize(
        application,
        tmp_path,
        monkeypatch,
        surface,
        aspect=True,
        distorted=distorted,
        fast=True,
    )


def _exercise_artwork_during_resize(
    application,
    tmp_path,
    monkeypatch,
    surface,
    *,
    wrong_owner=False,
    aspect=False,
    distorted=False,
    hero=False,
    fast=False,
):
    import Quartz
    from AppKit import NSApplication
    from quality_harness.artwork_observations import (
        inspect_artwork_centers,
        inspect_artwork_shapes,
    )
    from quality_harness.source_identity import source_manifest

    app = application
    checkout = Path(__file__).resolve().parents[1]
    before = source_manifest(checkout)
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path))) / (
        (
            "artwork-fast-"
            if fast
            else "artwork-hero-"
            if hero
            else "artwork-aspect-"
            if aspect
            else "artwork-identity-"
        )
        + surface
        + ("-distorted" if distorted else "-wrong-owner" if wrong_owner else "-valid")
    )
    output.mkdir(parents=True, exist_ok=True)
    colors = [
        (224, 48, 48),
        (48, 208, 64),
        (48, 80, 224),
        (224, 192, 48),
        (208, 48, 208),
        (48, 208, 208),
    ]
    palette = {f"Identity channel {i}": color for i, color in enumerate(colors)}
    paths = {}
    for index, (owner, color) in enumerate(palette.items()):
        path = tmp_path / (owner + ".png")
        size = (
            (1600, 500)
            if hero
            else (((320, 160) if index % 2 else (160, 320)) if aspect else (160, 160))
        )
        image = Image.new("RGB", size, color)
        cx, cy = size[0] / 2, size[1] / 2
        ImageDraw.Draw(image).ellipse(
            (cx - 60, cy - 60, cx + 60, cy + 60), outline="white", width=5
        )
        image.save(path)
        paths[owner] = path
    if distorted:
        from PIL import ImageOps

        original_fit = ImageOps.fit

        def stretch(source, size, *args, **kwargs):
            if source.size in {(320, 160), (160, 320)} and size[0] == size[1]:
                return source.resize(size, Image.Resampling.LANCZOS)
            return original_fit(source, size, *args, **kwargs)

        monkeypatch.setattr(ImageOps, "fit", stretch)
    rows = seed(app, tmp_path, count=18)
    for i, row in enumerate(rows):
        row["channel"] = f"Identity channel {i // 3}"
    app._reconcile_library_projection()
    scene = app.library_scene if surface == "library" else app.focus_watch
    monkeypatch.setattr(
        scene,
        "_artwork_source_path",
        lambda row, *_args: ArtworkAsset(paths[row["channel"]], "thumbnail"),
    )
    app._select_focus_view(surface)
    (scene.navigate if surface == "library" else scene._navigate)(
        "home" if hero else "channels"
    )
    app.geometry("1280x760+20+80" if hero else "980x600+100+80")
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    pump(app, 2)
    canvas = scene.canvas
    native = _native_window(app)
    number = int(native.windowNumber())
    original_image = scene._artwork_image
    original_create = canvas.create_image
    original_render = scene._render
    pending = {}
    items = {}
    layout = {"generation": 0, "busy": False, "regions": []}
    events, frames, errors = [], [], []
    stop = Event()
    origin = time.monotonic()

    def requested(row, **kwargs):
        pending["owner"] = row["channel"]
        result = original_image(row, **kwargs)
        # Independent expected identity stays bound to the caller's record.
        # The fault returns a real, cached image of another owner at the same size.
        if wrong_owner:
            substitute = next(r for r in rows if r["channel"] != row["channel"])
            return original_image(substitute, **kwargs)
        return result

    def created(*args, **kwargs):
        item = original_create(*args, **kwargs)
        if "presentation-artwork" in kwargs.get("tags", ""):
            items[item] = pending["owner"]
        return item

    def render():
        nonlocal layout
        generation = layout["generation"] + 1
        layout = {"generation": generation, "busy": True, "regions": []}
        original_render()
        regions = []
        for item, owner in items.items():
            bbox = canvas.bbox(item)
            if bbox is None:
                continue
            left, top, right, bottom = bbox
            left -= canvas.canvasx(0)
            right -= canvas.canvasx(0)
            top -= canvas.canvasy(0)
            bottom -= canvas.canvasy(0)
            if (
                0 <= left < right <= canvas.winfo_width()
                and 0 <= top < bottom <= canvas.winfo_height()
            ):
                regions.append({"owner": owner, "bbox": [left, top, right, bottom]})
        controls = []
        if fast and surface == "library":
            for item in canvas.find_all():
                if canvas.type(item) == "window" and canvas.itemcget(
                    item, "window"
                ) == str(scene._search_field):
                    box = canvas.bbox(item)
                    if box:
                        controls.append(
                            {
                                "owner": "library-search",
                                "bbox": [
                                    box[0] - canvas.canvasx(0),
                                    box[1] - canvas.canvasy(0),
                                    box[2] - canvas.canvasx(0),
                                    box[3] - canvas.canvasy(0),
                                ],
                            }
                        )
        layout = {
            "generation": generation,
            "busy": False,
            "regions": regions,
            "controls": controls,
            "canvas_origin": [canvas.winfo_rootx(), canvas.winfo_rooty()],
            "canvas_width": canvas.winfo_width(),
            "root_width": app.winfo_width(),
            "committed": time.monotonic() - origin,
        }

    monkeypatch.setattr(scene, "_artwork_image", requested)
    monkeypatch.setattr(canvas, "create_image", created)
    monkeypatch.setattr(scene, "_render", render)
    render()
    pump(app, 0.3)

    def bounds():
        return dict(
            next(
                w
                for w in Quartz.CGWindowListCopyWindowInfo(
                    Quartz.kCGWindowListOptionIncludingWindow, number
                )
                if int(w["kCGWindowNumber"]) == number
            )["kCGWindowBounds"]
        )

    initial = bounds()
    baseline = {
        "bounds": initial,
        "button": bool(
            Quartz.CGEventSourceButtonState(
                Quartz.kCGEventSourceStateCombinedSessionState,
                Quartz.kCGMouseButtonLeft,
            )
        ),
        "native_live_resize": bool(native.inLiveResize()),
    }
    (output / "input-baseline.json").write_text(json.dumps(baseline, indent=2))
    assert not baseline["button"] and not baseline["native_live_resize"], baseline

    def capture():
        retained_bytes = 0
        try:
            while not stop.is_set():
                begin = time.monotonic() - origin
                snapshot = layout
                first = bounds()
                button = bool(
                    Quartz.CGEventSourceButtonState(
                        Quartz.kCGEventSourceStateCombinedSessionState,
                        Quartz.kCGMouseButtonLeft,
                    )
                )
                pointer = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
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
                profile = Quartz.CGColorSpaceCopyICCData(
                    Quartz.CGImageGetColorSpace(raw)
                )
                if profile is None:
                    raise RuntimeError("Capture color profile unavailable")
                profile = bytes(profile)
                last = bounds()
                end = time.monotonic() - origin
                current = layout
                stable = (
                    not snapshot["busy"]
                    and current is snapshot
                    and first == last
                    and image.size == (int(first["Width"]), int(first["Height"]))
                    and snapshot.get("root_width") == first["Width"]
                )
                retained_bytes += image.width * image.height * 3
                if len(frames) >= 120 or retained_bytes > 384 * 1024 * 1024:
                    raise RuntimeError(
                        "Own-window observation exceeds frame/byte allowance"
                    )
                # Associate raw acquisition with layout now; color conversion,
                # geometry analysis and PNG compression happen after input.
                frames.append(
                    {
                        "begin": begin,
                        "end": end,
                        "file": f"frame-{len(frames):03d}.png",
                        "stable": stable,
                        "button": button,
                        "bounds": first,
                        "pointer": [pointer.x, pointer.y],
                        "layout": snapshot,
                        "_image": image,
                        "_profile": profile,
                    }
                )
                stop.wait(max(0, 0.035 - ((time.monotonic() - origin) - begin)))
        except Exception as exc:  # noqa: BLE001 - observer failure invalidates evidence
            errors.append(repr(exc))

    def post(kind, x, y, phase):
        event = Quartz.CGEventCreateMouseEvent(
            None, kind, (x, y), Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventSetFlags(event, 0)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        events.append({"t": time.monotonic() - origin, "phase": phase, "x": x, "y": y})

    def drive():
        x = initial["X"] + initial["Width"] - 2
        y = initial["Y"] + initial["Height"] - 2
        try:
            time.sleep(0.4)
            post(Quartz.kCGEventMouseMoved, x, y, "position")
            time.sleep(0.15)
            post(Quartz.kCGEventLeftMouseDown, x, y, "press")
            if fast:
                drag_started = time.monotonic()
                for step in range(1, 25):
                    time.sleep(
                        max(0, drag_started + (step - 1) * 0.045 - time.monotonic())
                    )
                    post(
                        Quartz.kCGEventLeftMouseDragged,
                        x + step * 8,
                        y + step * 2,
                        "drag",
                    )
                time.sleep(max(0, drag_started + 24 * 0.045 - time.monotonic()))
                post(Quartz.kCGEventLeftMouseUp, x + 192, y + 48, "release")
                free_started = time.monotonic()
                for step in range(16):
                    time.sleep(max(0, free_started + step * 0.045 - time.monotonic()))
                    post(
                        Quartz.kCGEventMouseMoved,
                        x + 192 - step * 5,
                        y + 48 - step * 3,
                        "free-pointer",
                    )
                time.sleep(max(0, free_started + 16 * 0.045 - time.monotonic()))
            else:
                for step in range(1, 9):
                    post(
                        Quartz.kCGEventLeftMouseDragged,
                        x + step * 20,
                        y + step * 4,
                        "drag",
                    )
                    time.sleep(0.18)
                post(Quartz.kCGEventLeftMouseUp, x + 160, y + 32, "release")
                time.sleep(0.4)
        except Exception as exc:  # noqa: BLE001 - retain driver faults
            errors.append(repr(exc))
        finally:
            post(Quartz.kCGEventLeftMouseUp, x + 160, y + 32, "cleanup")

    recorder = Thread(target=capture, daemon=True)
    driver = Thread(target=drive, daemon=True)
    recorder.start()
    driver.start()
    deadline = time.monotonic() + 12

    def service():
        if driver.is_alive() and time.monotonic() < deadline:
            app.after(10, service)
        else:
            app.quit()

    app.after(0, service)
    try:
        app.mainloop()
    finally:
        driver.join(1)
        stop.set()
        recorder.join(2)
    import io

    from PIL import ImageCms
    from quality_harness.transition_observations import compare_unchanged_regions

    last_profile = transform = None
    control_reference = None
    reference_controls = []
    scheduled_press = next(e["t"] for e in events if e["phase"] == "press")
    for frame in frames:
        image, profile = frame.pop("_image"), frame.pop("_profile")
        if profile != last_profile:
            transform = ImageCms.buildTransformFromOpenProfiles(
                ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                ImageCms.createProfile("sRGB"),
                "RGB",
                "RGB",
            )
            last_profile = profile
        image = ImageCms.applyTransform(image, transform)
        snapshot, geometry = frame["layout"], frame["bounds"]
        observations = []
        if frame["stable"]:
            x, y = snapshot["canvas_origin"]
            translated = [
                {
                    "owner": r["owner"],
                    **({"identity_point": (0.88, 0.2)} if hero else {}),
                    "bbox": [
                        r["bbox"][0] + x - geometry["X"],
                        r["bbox"][1] + y - geometry["Y"],
                        r["bbox"][2] + x - geometry["X"],
                        r["bbox"][3] + y - geometry["Y"],
                    ],
                }
                for r in snapshot["regions"]
            ]
            observations = inspect_artwork_centers(image, translated, palette)
            if aspect:
                shapes = inspect_artwork_shapes(image, translated)
                for observation, shape in zip(observations, shapes, strict=True):
                    observation["shape"] = shape
        frame["observations"] = observations
        frame["control_observations"] = []
        if frame["stable"] and snapshot.get("controls"):
            x, y = snapshot["canvas_origin"]
            controls = [
                {
                    "owner": row["owner"],
                    "bbox": [
                        row["bbox"][0] + x - geometry["X"],
                        row["bbox"][1] + y - geometry["Y"],
                        row["bbox"][2] + x - geometry["X"],
                        row["bbox"][3] + y - geometry["Y"],
                    ],
                }
                for row in snapshot["controls"]
            ]
            if control_reference is None and frame["end"] < scheduled_press:
                control_reference, reference_controls = image.copy(), controls
            if control_reference is not None:
                frame["control_observations"] = compare_unchanged_regions(
                    image, control_reference, controls, reference_controls
                )
        image.save(output / frame["file"])
    press = next(e["t"] for e in events if e["phase"] == "press")
    release = next(e["t"] for e in events if e["phase"] == "release")
    required_owners = 1 if hero else 2
    qualified = [
        f for f in frames if f["stable"] and len(f["observations"]) >= required_owners
    ]
    prior = [f for f in qualified if f["end"] < press]
    active = [
        f for f in qualified if press < f["begin"] < f["end"] < release and f["button"]
    ]
    after = [f for f in qualified if f["begin"] > release and not f["button"]]
    enrolled_owners = {o["owner"] for o in prior[0]["observations"]} if prior else set()
    neutral = [f for f in frames if f["end"] < press]
    checks = {
        "neutral_before_scheduled_press": bool(neutral)
        and not any(f["button"] for f in neutral),
        "visible_owners_remain_present": bool(enrolled_owners)
        and all(
            enrolled_owners <= {o["owner"] for o in f["observations"]}
            for f in frames
            if f["stable"]
        ),
        "completed": not driver.is_alive() and not recorder.is_alive() and not errors,
        "source_unchanged": before["sha256"] == source_manifest(checkout)["sha256"],
        "before_during_after_observed": bool(prior and active and after),
        "three_pressed_widths": len(
            {
                f["bounds"]["Width"]
                for f in active
                if f["bounds"]["Width"] != initial["Width"]
            }
        )
        >= 3,
        "distinct_expected_owners": all(
            len({o["owner"] for o in f["observations"]}) >= required_owners
            for f in qualified
        ),
        "all_sampled_identities_correct": bool(qualified)
        and all(o["matched"] for f in qualified for o in f["observations"]),
    }
    if fast and surface == "library":
        checks["unchanged_control_pixels_preserved"] = bool(qualified) and all(
            f["control_observations"]
            and all(o["matched"] for o in f["control_observations"])
            for f in qualified
        )
    if aspect:
        checks["all_sampled_shapes_correct"] = bool(qualified) and all(
            o["shape"]["matched"] for f in qualified for o in f["observations"]
        )
    receipt = {
        "surface": surface,
        "wrong_owner": wrong_owner,
        "aspect": aspect,
        "distorted": distorted,
        "hero": hero,
        "fast": fast,
        "source": before,
        "baseline": baseline,
        "events": events,
        "frames": frames,
        "errors": errors,
        "checks": checks,
        "limits": [
            (
                "OS injected 24-step/45ms fast resize with free-pointer tail; pixel fixture is separate from geometry gate."
                if fast
                else "OS injected stepped resize, not continuous smoothness or release stability."
            ),
            (
                "Hero identity patch and continued presence; not full hero aspect or composition."
                if hero
                else "Calibrated avatar aspect/center/circumference; not hero, banner or media composition."
                if aspect
                else "Center patch identity only; not aspect ratio or full composition."
            ),
            "Captures crossing layout or geometry changes are ambiguous and excluded.",
            "Window server samples do not establish display refresh timestamps.",
        ],
    }
    (
        output / ("artwork-aspect.json" if aspect else "artwork-identity.json")
    ).write_text(json.dumps(receipt, indent=2))
    assert all(
        v
        for k, v in checks.items()
        if k not in {"all_sampled_identities_correct", "all_sampled_shapes_correct"}
    ), checks
    if aspect:
        assert checks["all_sampled_shapes_correct"] is not distorted, checks
        if distorted:
            for phase in (prior, active, after):
                assert any(
                    not o["shape"]["matched"] for f in phase for o in f["observations"]
                ), "Distortion must be detected before, during and after resize"
    assert checks["all_sampled_identities_correct"] is not wrong_owner, checks
    if wrong_owner:
        for phase in (prior, active, after):
            assert any(not o["matched"] for f in phase for o in f["observations"]), (
                "Wrong-owner control must be detected before, during and after resize"
            )
