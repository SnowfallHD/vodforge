"""Owned view reveal under real Tk; no desktop read or external window capture."""

from __future__ import annotations

import os
import sys
import time
import tkinter as tk

import pytest

from tests.test_archive_native import application as _application

application = _application

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1" or sys.platform != "darwin",
    reason="explicit Mac native display required",
)


def test_view_capture_and_transition_replacement_teardown_are_owned():
    from yt_downloader.platform_services import capture_own_widget
    from yt_downloader.ui_transition import ViewTransition, cancel_view_transition

    root = tk.Tk()
    root.geometry("700x440+100+100")
    first = tk.Frame(root, bg="#234567")
    second = tk.Frame(root, bg="#573421")
    first.place(x=20, y=40, width=640, height=340)
    second.place(x=20, y=40, width=640, height=340)
    errors = []
    root.report_callback_exception = lambda *args: errors.append(str(args[1]))
    transition = root._view_transition = ViewTransition(root)

    def pump(seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            root.update()
            time.sleep(0.002)

    try:
        pump(0.2)
        bitmap = capture_own_widget(second)
        assert bitmap.size == (640, 340)
        assert (
            max(abs(a - b) for a, b in zip(bitmap.getpixel((320, 170)), (87, 52, 33)))
            <= 8
        )
        transition.prepare(second)
        transition.reveal(second)
        pump(0.045)
        assert transition._overlay is not None
        assert transition._target is second
        transition.prepare(second)
        first.tkraise()
        transition.reveal(first)
        assert transition._overlay is not None
        assert transition._target is first
        pump(0.045)
        assert transition._overlay is not None
        cancel_view_transition(first)
        assert transition._overlay is None and transition._timer is None
        pump(0.2)
        assert transition._overlay is None
        for _ in range(8):
            transition.prepare(first)
            transition.reveal(second)
            pump(0.04)
            transition.cancel()
        assert not first.winfo_children() and not second.winfo_children()
        transition.prepare(first)
        transition.reveal(second)
        root.destroy()
        assert transition._timer is None and transition._image is None
        assert not errors
    finally:
        if root.tk.call("info", "commands", "."):
            root.destroy()


def test_new_view_does_not_blur_after_its_sharp_pixels_are_visible(tmp_path):
    """Observe native rendered pixels throughout the reveal, not timer lifetime."""
    import json
    from pathlib import Path

    from PIL import ImageChops, ImageStat

    from yt_downloader.platform_services import capture_own_widget
    from yt_downloader.ui_transition import ViewTransition

    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.geometry("420x300+100+100")
    frame = tk.Frame(root)
    frame.pack(fill="both", expand=True)
    canvas = tk.Canvas(frame, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    for x in range(0, 440, 8):
        canvas.create_rectangle(x, 0, x + 4, 320, fill="white", outline="")
    root.update()
    transition = ViewTransition(root)
    snapshots = []
    started = time.monotonic()

    def observe():
        bitmap = capture_own_widget(frame)
        assert bitmap is not None, "Native rendered-view capture unavailable"
        region = bitmap.crop((80, 80, 320, 220)).convert("L")
        contrast = ImageStat.Stat(
            ImageChops.difference(region, ImageChops.offset(region, 1, 0))
        ).mean[0]
        index = len(snapshots)
        bitmap.save(output / f"transition-pixels-{index:02d}.png")
        snapshots.append(
            {
                "t": time.monotonic() - started,
                "contrast": contrast,
                "overlay": transition._overlay is not None,
            }
        )

    try:
        observe()
        previous = tk.Frame(root, bg="#234567")
        previous.place(x=0, y=0, relwidth=1, relheight=1)
        previous.lift()
        root.update()
        # The old implementation has no prepare phase; keep its visible
        # sequence observable in the same before/fix pixel regression.
        prepare = getattr(transition, "prepare", None)
        if prepare is not None:
            prepare(previous)
        previous.place_forget()
        frame.lift()
        transition.reveal(frame)
        deadline = time.monotonic() + 0.35
        while time.monotonic() < deadline:
            root.update()
            observe()
            time.sleep(0.005)
        baseline = snapshots[0]["contrast"]
        observed_overlay = [row for row in snapshots if row["overlay"]]
        report = {
            "scope": "native view-rendered pixels; capture overhead included, not physical display refresh timestamps",
            "snapshots": snapshots,
            "baseline": baseline,
        }
        (output / "transition-pixels.json").write_text(json.dumps(report, indent=2))
        assert observed_overlay, "Capture cadence failed to observe the transition"
        target_seen = False
        for row in snapshots[1:]:
            if row["contrast"] >= baseline * 0.9:
                target_seen = True
            if target_seen:
                assert row["contrast"] >= baseline * 0.9, (
                    "Already-visible sharp target regressed to blurry pixels during reveal",
                    snapshots,
                )
        assert target_seen, "Destination pixels were never revealed"
    finally:
        transition.cancel()
        root.destroy()


@pytest.mark.parametrize("viewport,media_count", [((980, 600), 18), ((1280, 760), 180)])
@pytest.mark.parametrize("draw_pending", [True, False])
def test_actual_tabs_never_mix_previous_and_destination_regions(
    application, tmp_path, monkeypatch, draw_pending, viewport, media_count
):
    import io
    import json
    from itertools import pairwise
    from pathlib import Path
    from threading import Event, Thread

    import Quartz
    from AppKit import NSApplication
    from PIL import Image, ImageCms
    from quality_harness.source_identity import source_manifest
    from quality_harness.transition_observations import (
        classify_view_regions,
        content_regions,
    )

    from tests.test_archive_native import pump, seed
    from yt_downloader import ui_transition
    from yt_downloader.library_artwork_source import ArtworkAsset
    from yt_downloader.platforms.macos.windowing import _native_window

    app = application
    retained_regions = []
    if not draw_pending:
        original_finish = ui_transition.ViewTransition._finish

        def retain_outgoing_region(transition, generation):
            if generation != transition._generation or transition._overlay is None:
                return original_finish(transition, generation)
            # Leave actual old pixels over half of the mapped destination.
            # This is a visible native fault, not an edit to captured evidence.
            width = max(1, transition._size[0] // 2)
            transition._overlay.configure(anchor="nw")
            transition._overlay.place_configure(width=width)
            transition._overlay.lift()
            retained_regions.append(
                {"at": time.monotonic(), "width": width, "generation": generation}
            )
            transition._timer = transition.root.after(
                160, lambda: original_finish(transition, generation)
            )

        monkeypatch.setattr(
            ui_transition.ViewTransition, "_finish", retain_outgoing_region
        )
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path))) / (
        "actual-tabs" if draw_pending else "actual-tabs-retained-region"
    )
    if media_count != 18:
        output = output.with_name(output.name + "-large")
    output.mkdir(parents=True, exist_ok=True)
    source = source_manifest(Path(__file__).resolve().parents[1])
    rows = seed(app, tmp_path, count=media_count)
    for index, row in enumerate(rows):
        row["channel"] = f"Channel {index // 3}"
    app._reconcile_library_projection()
    # Activity -> an empty Forge no longer supplies four distinct regions under
    # continuous shared materials. Exercise a realistic populated run instead;
    # retain the fixed independent region rule and actual partial-reveal fault.
    from scripts.focus_ui_preview import PREVIEW_THUMBNAILS

    app._focus_active_override = True
    app.focus_active_title_var.set("Alpine mornings — a quiet escape")
    app.focus_active_detail_var.set("Northlight Studio")
    app.focus_active_profile_var.set("1080p Full HD  •  Auto CBR")
    app.focus_active_duration_var.set("32:47")
    app.progress_var.set(73)
    app.status_var.set("ETA 1m 26s  •  8.7 MB/s")
    app.focus_run_status_var.set("73%  •  1m 26s left")
    app.focus_transfer_var.set("5.23 GB / 7.12 GB")
    app._load_thumbnail_file(PREVIEW_THUMBNAILS / "alpine-lake.jpg", target="active")
    app._set_focus_run_controls_visible(True)
    log_lines = "\n".join(
        [
            "[info] Preparing Alpine mornings — a quiet escape",
            "[info] Selected video H.264 1920x1080 and AAC stereo",
            *[
                f"[download] {percent}% of 7.12 GiB at 8.7 MiB/s"
                for percent in range(5, 74, 5)
            ],
        ]
    )
    app._set_text(app.focus_log, log_lines, disabled=True)
    app._set_text(app.log, log_lines, disabled=True)
    app.activity_summary.request(
        title=app.focus_active_title_var.get(),
        status="Downloading",
        detail=app.status_var.get(),
    )
    assert app._focus_active_thumbnail_source_image is not None
    path = tmp_path / "diagnostic.png"
    Image.effect_noise((320, 180), 80).convert("RGB").save(path)
    for scene in (app.library_scene, app.focus_watch):
        monkeypatch.setattr(
            scene, "_artwork_source_path", lambda *_: ArtworkAsset(path, "thumbnail")
        )
    app.geometry(f"{viewport[0]}x{viewport[1]}+60+50")
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    for route in ("library", "watch", "activity", "forge"):
        app._select_focus_view(route)
        pump(app, 0.8)
    number = int(_native_window(app).windowNumber())
    frames, events, errors = [], [], []
    stop = Event()
    start = time.monotonic()
    routes = ["library", "watch", "activity", "forge", "watch", "library"]

    def capture():
        try:
            while not stop.is_set():
                begin = time.monotonic() - start
                raw = Quartz.CGWindowListCreateImage(
                    Quartz.CGRectNull,
                    Quartz.kCGWindowListOptionIncludingWindow,
                    number,
                    Quartz.kCGWindowImageBoundsIgnoreFraming
                    | Quartz.kCGWindowImageNominalResolution,
                )
                if raw is None:
                    raise RuntimeError("Capture unavailable")
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
                profile = bytes(
                    Quartz.CGColorSpaceCopyICCData(Quartz.CGImageGetColorSpace(raw))
                )
                # Acquisition stays independent of color conversion and disk I/O.
                # Retain the actual profile; apply it after the input run.
                frames.append(
                    ({"begin": begin, "end": time.monotonic() - start}, image, profile)
                )
                stop.wait(0.005)
        except Exception as exc:  # noqa: BLE001 - capture failure makes evidence unavailable
            errors.append(repr(exc))

    def navigate(index=0):
        if index == len(routes):
            app.after(400, app.quit)
            return
        route = routes[index]
        begin = time.monotonic() - start
        app._focus_nav_buttons[route].invoke()
        events.append({"begin": begin, "end": time.monotonic() - start, "route": route})
        app.after(350, lambda: navigate(index + 1))

    worker = Thread(target=capture, daemon=True)
    worker.start()
    app.after(350, navigate)
    try:
        app.mainloop()
    finally:
        stop.set()
        worker.join(2)
    last_profile = transform = None
    for index, (record, image, profile) in enumerate(frames):
        if profile != last_profile:
            transform = ImageCms.buildTransformFromOpenProfiles(
                ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                ImageCms.createProfile("sRGB"),
                "RGB",
                "RGB",
            )
            last_profile = profile
        image = ImageCms.applyTransform(image, transform)
        record["file"] = f"frame-{index:03d}.png"
        image.save(output / record["file"])
        frames[index] = (record, image)
    records = [f for f, _ in frames]
    images = {record["file"]: image for record, image in frames}
    evaluations = []
    for n, event in enumerate(events):
        boundary = (
            events[n + 1]["begin"]
            if n + 1 < len(events)
            else records[-1]["end"] + 0.001
        )
        prior = [f for f in records if f["end"] < event["begin"]]
        later = [f for f in records if event["end"] + 0.2 < f["end"] < boundary]
        assert len(prior) >= 2 and len(later) >= 2, "Missing reference observations"
        old, new = images[prior[-1]["file"]], images[later[-1]["file"]]
        assert old.size == new.size == viewport, (
            "Native viewport did not match the requested fixture"
        )
        # Use fixed-size regions so sparse controls are not diluted merely
        # because the viewport is larger. The compact fixture keeps its grid.
        boxes = content_regions(viewport)
        for record in records:
            if record["end"] < event["begin"] or record["begin"] > boundary:
                continue
            result = classify_view_regions(images[record["file"]], old, new, boxes)
            evaluations.append(
                {"route": event["route"], "frame": record["file"], **result}
            )
    report = {
        "source": source,
        "events": events,
        "frames": records,
        "mutation": None if draw_pending else "retained-outgoing-region",
        "retained_regions": retained_regions,
        "viewport": viewport,
        "media_count": media_count,
        "evaluations": evaluations,
        "errors": errors,
        "source_unchanged": source_manifest(Path(__file__).resolve().parents[1])[
            "sha256"
        ]
        == source["sha256"],
        "scope": "Actual tab command invocation and sampled own-window pixels; not physical input or display-refresh proof",
    }
    (output / "tabs.json").write_text(json.dumps(report, indent=2))
    assert not errors and not worker.is_alive() and report["source_unchanged"]
    # Include two pre-input reference samples; capture warmup earlier than
    # those samples is retained but is not part of the interaction claim.
    pre_input = [f for f in records if f["end"] < events[0]["begin"]]
    measured = [f for f in records if f["begin"] >= pre_input[-2]["begin"]]
    assert max(b["begin"] - a["begin"] for a, b in pairwise(measured)) <= 0.05
    assert max(f["end"] - f["begin"] for f in measured) <= 0.05
    assert evaluations
    if draw_pending:
        assert all(e["status"] == "passed" for e in evaluations), [
            e for e in evaluations if e["status"] != "passed"
        ]
    else:
        assert any(row["at"] >= start for row in retained_regions)
        assert any(e["mixed_generations"] for e in evaluations), (
            "Retained outgoing pixels escaped the mixed-content oracle"
        )


def test_destination_replaced_during_child_drawing_keeps_new_transition(
    application, tmp_path, monkeypatch
):
    from tests.test_archive_native import pump, seed
    from yt_downloader import ui_transition

    app = application
    seed(app, tmp_path, count=18)
    app._select_focus_view("watch")
    pump(app, 1)
    app._select_focus_view("library")
    pump(app, 0.4)
    observed, returned = [], []
    original = ui_transition.present_pending_drawing

    def drawing(canvas):
        # Inject a real successor navigation from the idle work serviced by the
        # shared drawing owner. The old completion may not cancel its cover.
        monkeypatch.setattr(ui_transition, "present_pending_drawing", original)
        app.after_idle(lambda: app._select_focus_view("activity"))
        original(canvas)
        transition = app._view_transition
        observed.append(
            (transition._generation, transition._overlay, transition._target)
        )

    transition = app._view_transition
    original_finish = transition._finish

    def finish(generation):
        original_finish(generation)
        if observed and not returned:
            returned.append(
                (transition._generation, transition._overlay, transition._target)
            )

    monkeypatch.setattr(transition, "_finish", finish)
    monkeypatch.setattr(ui_transition, "present_pending_drawing", drawing)
    app._select_focus_view("watch")
    deadline = time.monotonic() + 2
    while not observed and time.monotonic() < deadline:
        app.update()
        time.sleep(0.002)
    assert observed
    generation, cover, target = observed[0]
    assert cover is not None and target is app._focus_views["activity"]
    assert returned == [(generation, cover, target)]
    assert app._focus_selected_view == "activity"
    pump(app, 0.4)
    assert app._view_transition._overlay is None
    assert app._focus_selected_view == "activity"


def test_rapid_tabs_and_internal_navigation_retire_old_reveals(
    application, tmp_path, monkeypatch
):
    from tests.test_archive_native import pump, seed

    app = application
    seed(app, tmp_path, count=18)
    for scene in (app.library_scene, app.focus_watch):
        monkeypatch.setattr(scene, "_artwork_source_path", lambda *_: None)
    routes = ["watch", "library", "activity", "forge", "watch", "library"]
    accepted = []

    def navigate(index=0):
        app._focus_nav_buttons[routes[index]].invoke()
        accepted.append(routes[index])
        if index + 1 < len(routes):
            app.after(10, lambda: navigate(index + 1))
        else:
            app.library_scene.navigate("channels")
            assert app._view_transition._overlay is None

    app.after(0, navigate)
    deadline = time.monotonic() + 4
    while len(accepted) < len(routes) and time.monotonic() < deadline:
        app.update()
        time.sleep(0.002)
    assert accepted == routes
    pump(app, 0.4)
    assert app._focus_selected_view == "library"
    assert app._view_transition._overlay is None and app._view_transition._timer is None
    assert [
        name for name, frame in app._focus_views.items() if frame.winfo_ismapped()
    ] == ["library"]


def test_native_bitmap_fast_path_matches_same_rep_png(application, tmp_path):
    import io
    import json
    from pathlib import Path

    from AppKit import NSBitmapImageFileTypePNG
    from PIL import Image

    from tests.test_archive_native import pump, seed
    from yt_downloader.platforms.macos.surfaces import _bitmap_rep_image
    from yt_downloader.platforms.macos.windowing import _native_window

    app = application
    seed(app, tmp_path, count=18)
    app.geometry("1280x760+60+50")
    app._select_focus_view("watch")
    pump(app, 0.6)
    view = _native_window(app).contentView()
    bounds = view.bounds()
    rep = view.bitmapImageRepForCachingDisplayInRect_(bounds)
    view.cacheDisplayInRect_toBitmapImageRep_(bounds, rep)
    encodings = []

    class Proxy:
        def __getattr__(self, name):
            return getattr(rep, name)

        def representationUsingType_properties_(self, *args):
            encodings.append(True)
            return rep.representationUsingType_properties_(*args)

    started = time.monotonic()
    image = _bitmap_rep_image(Proxy())
    direct_ms = (time.monotonic() - started) * 1000
    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
    with Image.open(io.BytesIO(bytes(data))) as reference:
        assert image.tobytes() == reference.convert("RGBA").tobytes()
    assert not encodings, "Supported opaque native format unexpectedly used the encoder"
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    (output / "bitmap-fidelity.json").write_text(
        json.dumps(
            {
                "size": image.size,
                "direct_ms": direct_ms,
                "same_rep_png_equal": True,
                "encoding_calls_on_fast_path": len(encodings),
                "scope": "Native pixel fidelity and detached ownership, not a performance threshold",
            },
            indent=2,
        )
    )


def test_press_on_outgoing_cover_cannot_activate_unseen_destination(application):
    import tkinter as tk

    from tests.test_archive_native import pump
    from yt_downloader.ui_button_contract import ProductButton
    from yt_downloader.ui_transition import ViewTransition

    app = application
    calls = []
    old = tk.Frame(app, background="#182334")
    new = tk.Frame(app, background="#223318")
    old.place(x=100, y=150, width=460, height=220)
    tk.Label(old, text="Previous page action").place(x=30, y=30)
    button = ProductButton(
        new,
        text="Different destination action",
        command=lambda: calls.append("destination"),
    )
    button.place(x=30, y=30, width=300, height=44)
    pump(app, 0.1)
    transition = ViewTransition(app)
    try:
        transition.prepare(old)
        new.place(x=100, y=150, width=460, height=220)
        new.lift()
        app.update_idletasks()
        transition.reveal(new)
        cover = transition._overlay
        assert cover is not None
        x = button.winfo_rootx() + 80 - cover.winfo_rootx()
        y = button.winfo_rooty() + 20 - cover.winfo_rooty()
        cover.event_generate("<ButtonPress-1>", x=x, y=y)
        button.event_generate("<ButtonRelease-1>", x=80, y=20)
        assert calls == [], "A press on old covered content activated a different owner"
        assert transition._overlay is None
        button.event_generate("<ButtonPress-1>", x=80, y=20)
        button.event_generate("<ButtonRelease-1>", x=80, y=20)
        assert calls == ["destination"], "A fresh visible action must still work"
    finally:
        transition.cancel()
        old.destroy()
        new.destroy()
