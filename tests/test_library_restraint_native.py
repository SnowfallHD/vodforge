"""Opt-in native Library restraint and complete visible action-label geometry."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.focus_ui_preview import isolated_preview_services
from tests.test_native_thumbnail_rendering import application as _application
from yt_downloader import app as app_module
from yt_downloader.analytics_startup import AnalyticsStartup
from yt_downloader.engagement_ui import EngagementUI
from yt_downloader.library_annotations import LibraryAnnotation

application = _application

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1" or sys.platform != "darwin",
    reason="explicit Mac native display and OS input required",
)


def test_home_recent_row_renders_only_when_reachable_in_viewport(
    application, tmp_path, monkeypatch
):
    from tests.test_archive_native import pump, seed
    from yt_downloader.archive_browser import archive_row_owner

    app = application
    seed(app, tmp_path, count=25)
    app.geometry("1100x600+30+30")
    app._select_focus_view("library")
    scene = app.library_scene
    scene.navigate("home")
    pump(app, 0.3)
    calls = []
    original = scene._media_card

    def draw(*args, **kwargs):
        calls.append((args[1], args[4], args[5]))
        return original(*args, **kwargs)

    monkeypatch.setattr(scene, "_media_card", draw)
    for width in (1100, 1180, 1100):
        app.geometry(f"{width}x600")
        pump(app, 0.1)
        scene.canvas.yview_moveto(0)
        calls.clear()
        scene._render()
        assert not calls, "Recent cards below the viewport still rebuild during resize"
        assert scene._rendered_count == 0
        assert scene._matching_count == 25
    # The normal scroll notification must admit the same canonical recent row.
    scene.canvas.yview_moveto(1)
    pump(app, 0.3)
    assert calls and scene._rendered_count > 0
    top = scene.canvas.canvasy(0)
    bottom = top + scene.canvas.winfo_height()
    assert all(y < bottom and y + width * 9 // 16 + 151 > top for _, y, width in calls)
    expected = {archive_row_owner(scene._records[index]) for index, _, _ in calls}
    assert {owner for _bounds, owner in scene._context_targets} == expected
    details = [
        (bounds, action)
        for bounds, action in scene._targets
        if getattr(action, "func", None) == scene.show_details
    ]
    assert details
    index = details[0][1].args[0]
    details[0][1]()
    pump(app, 0.1)
    assert scene._route == "detail"
    assert scene._detail_owner == archive_row_owner(scene._records[index])


def test_default_library_missing_media_dismissal_does_not_activate_underlying_item(
    application, tmp_path, monkeypatch
):
    """Real default scene and missing-media owner; OS clicks, no legacy fixture."""
    import copy

    import Quartz
    from AppKit import NSApplication, NSWorkspace

    from tests.test_archive_models import saved
    from tests.test_archive_native import native_descendants, pump, wait_for
    from yt_downloader.history import save_history
    from yt_downloader.platform_services import capture_own_widget

    app = application
    app.geometry("1100x700+0+30")
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    rows = [
        saved(tmp_path / name / "missing.mp4", video=name)
        for name in ("original", "unrelated")
    ]
    app.download_history = rows
    save_history(app.history_path, rows)
    app._reconcile_library_projection()
    app._select_focus_view("library")
    scene = app.library_scene
    scene.show_details(0)
    pump(app, 0.3)
    assert scene.winfo_ismapped() and not app.video_tree.winfo_ismapped()
    requests, actions, admissions = [], [], []
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    clicks = []
    request = app._archive_request_playback
    action = scene._action
    admit = app._start_or_queue_download_job

    def observe_request(info, **kwargs):
        # Deferred storage readiness re-enters this method with the same
        # accepted operation. Count new user intents, not its continuation.
        if kwargs.get("accepted") is None:
            requests.append(info["id"])
        return request(info, **kwargs)

    def observe_action(*args):
        actions.append(list(args))
        return action(*args)

    def observe_admit(*args, **kwargs):
        admissions.append(True)
        return admit(*args, **kwargs)

    monkeypatch.setattr(app, "_archive_request_playback", observe_request)
    monkeypatch.setattr(scene, "_action", observe_action)
    monkeypatch.setattr(app, "_start_or_queue_download_job", observe_admit)

    def click(x, y):
        assert (
            NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier()
            == os.getpid()
        )
        hit = app.winfo_containing(int(x), int(y))
        clicks.append(
            {
                "point": [x, y],
                "tk_hit": str(hit),
                "class": hit.winfo_class() if hit else None,
            }
        )
        for kind in (
            Quartz.kCGEventMouseMoved,
            Quartz.kCGEventLeftMouseDown,
            Quartz.kCGEventLeftMouseUp,
        ):
            event = Quartz.CGEventCreateMouseEvent(
                None, kind, (x, y), Quartz.kCGMouseButtonLeft
            )
            Quartz.CGEventSetFlags(event, 0)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            pump(app, 0.05)
        pump(app, 0.2)

    def play():
        box = next(
            box
            for box, item, *_ in scene._button_labels
            if scene.canvas.itemcget(item, "text") == "Play"
        )
        region = tuple(float(v) for v in scene.canvas.cget("scrollregion").split())
        scene.canvas.yview_moveto(
            max(
                0, ((box[1] + box[3]) / 2 - scene.canvas.winfo_height() / 2) / region[3]
            )
        )
        pump(app, 0.15)
        box = next(
            box
            for box, item, *_ in scene._button_labels
            if scene.canvas.itemcget(item, "text") == "Play"
        )
        y = (box[1] + box[3]) / 2 - scene.canvas.canvasy(0)
        assert 0 < y < scene.canvas.winfo_height()
        click(
            scene.canvas.winfo_rootx() + (box[0] + box[2]) / 2,
            scene.canvas.winfo_rooty() + y,
        )

    def back():
        panel = app.__dict__.get("_archive_overlay")
        if panel is None:
            return None
        labels = [
            str(w.cget("text"))
            for w in native_descendants(panel)
            if "text" in tuple(w.keys())
        ]
        if "Media needs attention" not in labels:
            return None
        return next(
            w
            for w in native_descendants(panel)
            if "text" in tuple(w.keys()) and w.cget("text") == "Back to browse"
        )

    baseline = {
        "history": app.history_path.read_bytes(),
        "rows": copy.deepcopy(app.download_history),
        "queued": app.run_recovery.store.load_queued_jobs(),
    }
    play()
    capture_own_widget(app).save(output / "missing-media-after-play.png")
    (output / "missing-media-after-play.json").write_text(
        json.dumps(
            {
                "requests": requests,
                "actions": actions,
                "clicks": clicks,
                "overlay": str(app.__dict__.get("_archive_overlay")),
                "host": str(app.__dict__.get("_archive_playback_host")),
                "status": app.status_var.get(),
                "rows": [r["id"] for r in app.metadata_items],
                "labels": [
                    str(w.cget("text"))
                    for w in native_descendants(app)
                    if "text" in tuple(w.keys()) and w.winfo_ismapped()
                ],
            },
            indent=2,
        )
        + "\n"
    )
    wait_for(app, lambda: back() is not None)
    assert requests == ["original"]
    counts = (len(requests), len(actions), len(admissions))
    button = back()
    capture_own_widget(app).save(output / "missing-media-before-dismiss.png")
    point = (
        button.winfo_rootx() + button.winfo_width() / 2,
        button.winfo_rooty() + button.winfo_height() / 2,
    )
    assert app.winfo_containing(*map(int, point)) is button
    click(*point)
    wait_for(app, lambda: app._archive_overlay is None)
    pump(app, 0.3)
    assert (len(requests), len(actions), len(admissions)) == counts
    assert app.__dict__.get("_media_player_window") is None
    assert app.active_job is None and not app.pending_jobs
    assert app.history_path.read_bytes() == baseline["history"]
    assert app.download_history == baseline["rows"]
    assert app.run_recovery.store.load_queued_jobs() == baseline["queued"]
    assert scene.winfo_ismapped() and not app.video_tree.winfo_ismapped()
    capture_own_widget(app).save(output / "missing-media-after-dismiss.png")
    restoration = app.__dict__.get("_archive_restore_reveal")
    if restoration is not None:
        (output / "missing-media-restoration.json").write_text(
            json.dumps(
                {
                    "active": restoration.active,
                    "timer": str(restoration.timer),
                    "incoming": [str(w) for w in restoration.incoming],
                    "not_ready": [
                        {
                            "widget": str(w),
                            "class": w.winfo_class(),
                            "manager": w.winfo_manager(),
                            "mapped": w.winfo_ismapped(),
                            "width": w.winfo_width(),
                            "height": w.winfo_height(),
                        }
                        for root in restoration.incoming
                        for w in restoration._managed(root)
                        if not w.winfo_ismapped()
                        or w.winfo_width() <= 1
                        or w.winfo_height() <= 1
                    ],
                },
                indent=2,
            )
            + "\n"
        )
    scene.show_details(1)
    pump(app, 0.2)
    play()
    capture_own_widget(app).save(output / "missing-media-fresh-input.png")
    (output / "missing-media-fresh-input.json").write_text(
        json.dumps(
            {
                "requests": requests,
                "actions": actions,
                "clicks": clicks,
                "overlay": str(app.__dict__.get("_archive_overlay")),
                "status": app.status_var.get(),
                "detail_owner": scene._detail_owner,
                "dismissal_state_checks_passed": True,
            },
            indent=2,
        )
        + "\n"
    )
    wait_for(app, lambda: back() is not None)
    assert requests == ["original", "unrelated"]
    assert admissions == [] and app.history_path.read_bytes() == baseline["history"]
    (output / "missing-media-dismissal.json").write_text(
        json.dumps(
            {
                "scope": "Default Library source-native OS clicks; missing files, no decode/package claim",
                "requests": requests,
                "actions": actions,
                "admissions": admissions,
                "dismissal_action_counts_unchanged": True,
                "history_unchanged": True,
                "queue_unchanged": True,
                "default_scene_restored": True,
                "fresh_intended_input_reaches_second_subject": True,
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("width", [1414, 980, 820])
def test_library_browse_selection_and_details_have_complete_contextual_controls(
    tmp_path, width
):
    import ctypes
    import subprocess

    import objc
    import Quartz
    from AppKit import NSApplication

    from tests.test_archive_models import saved

    fixture = os.environ.get("VODFORGE_LIBRARY_FIXTURE")
    rows = (
        json.loads(Path(fixture).read_text())
        if fixture
        else [
            dict(
                saved(tmp_path / f"{i}.mp4", video=str(i), channel="Fixture channel"),
                duration=100,
            )
            for i in range(8)
        ]
    )
    evidence = {
        "window_width": width,
        "scope": "Source native Tk with OS-injected pointer; synthetic records",
        "checks": [],
        "captures": [],
        "callback_errors": [],
        "telemetry": [],
    }
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    app = None

    def pump(seconds=0.25):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.update()
            time.sleep(0.005)

    def check(name, truth):
        evidence["checks"].append({"name": name, "passed": bool(truth)})
        assert truth, name

    def button(label):
        scene = app.library_scene
        bounds = (
            next(
                box
                for box, action in scene._targets
                if getattr(getattr(action, "func", None), "__name__", "")
                == "_open_item_menu"
            )
            if label == "More"
            else next(
                box
                for box, item, _c, _a in scene._button_labels
                if scene.canvas.itemcget(item, "text") == label
            )
        )
        left, top, right, bottom = bounds
        y = (top + bottom) / 2
        visible_top = scene.canvas.canvasy(0)
        if y - visible_top > scene.canvas.winfo_height() - 20:
            scene.canvas.yview_scroll(
                int((y - visible_top - scene.canvas.winfo_height() + 120) / 20) + 1,
                "units",
            )
            pump()
        point(
            scene.canvas.winfo_rootx() + (left + right) / 2,
            scene.canvas.winfo_rooty() + y - scene.canvas.canvasy(0),
        )

    def point(x, y):
        for kind in (
            Quartz.kCGEventMouseMoved,
            Quartz.kCGEventLeftMouseDown,
            Quartz.kCGEventLeftMouseUp,
        ):
            event = Quartz.CGEventCreateMouseEvent(
                None, kind, (float(x), float(y)), Quartz.kCGMouseButtonLeft
            )
            Quartz.CGEventSetFlags(event, 0)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            time.sleep(0.04)
        pump(0.4)

    def capture(name):
        scene = app.library_scene
        labels = []
        for box, item, _c, _a in scene._button_labels:
            text = scene.canvas.itemcget(item, "text")
            if not text:
                continue
            bounds = scene.canvas.bbox(item)
            labels.append(text)
            check(
                name + " label " + text,
                bool(bounds)
                and bounds[0] >= box[0] - 2
                and bounds[1] >= box[1] - 2
                and bounds[2] <= box[2] + 2
                and bounds[3] <= box[3] + 2,
            )
            check(
                name + " target " + text,
                box[0] >= 0 and box[2] <= scene.canvas.winfo_width() + 2,
            )
        check(name + " nonvacuous labels", bool(labels))
        get_root = ctypes.CDLL(None).TkMacOSXGetRootControl
        get_root.argtypes = (ctypes.c_void_p,)
        get_root.restype = ctypes.c_void_p
        view = objc.objc_object(c_void_p=int(get_root(int(app.winfo_id()))))
        wid = int(view.window().windowNumber())
        path = output / f"library-{width}-{name}.png"
        result = subprocess.run(
            ["/usr/sbin/screencapture", "-x", "-o", "-l", str(wid), str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        evidence["captures"].append(
            {
                "name": name,
                "path": str(path),
                "window_id": wid,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "labels": labels,
            }
        )

    try:
        with (
            isolated_preview_services(),
            patch.object(AnalyticsStartup, "start", lambda _: None),
            patch.object(EngagementUI, "start", lambda _: None),
        ):
            app = app_module.DownloaderApp()
            app.report_callback_exception = lambda *_a: evidence[
                "callback_errors"
            ].append(str(_a[1]))
            app.geometry(f"{width}x1008+70+50")
            app.deiconify()
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            app.download_history = rows
            app._reconcile_library_projection()
            annotations = {}
            for i, row in enumerate(app.metadata_items):
                owner = str(
                    row.get("vodforge_annotation_owner")
                    or row.get("vodforge_projection_owner")
                    or ""
                )
                if owner:
                    annotations[owner] = LibraryAnnotation(
                        tags=("Nature", "Travel", "Favorites"),
                        category=("Nature", "Audio", "City", "Ambience")[i % 4],
                    )
            app.library_annotations.replace_many(annotations)
            app._reconcile_library_projection()
            app._select_focus_view("library")
            scene = app.library_scene
            scene.navigate("home")
            original_usage = scene._on_usage
            scene._on_usage = lambda feature, action, **dims: (
                evidence["telemetry"].append(
                    {"feature": feature, "action": action, "dimensions": dims}
                ),
                original_usage(feature, action, **dims),
            )
            pump(3)
            capture("browse")
            texts = [
                scene.canvas.itemcget(i, "text")
                for i in scene.canvas.find_all()
                if scene.canvas.type(i) == "text"
            ]
            check(
                "all category destinations are readable",
                all(
                    label in texts
                    for label in ("Channels", "Playlists", "Videos", "Audio")
                ),
            )
            check(
                "browsing hides selection",
                not scene._selection_mode and not scene._selected,
            )
            button("Select")
            check("native Select opens selection mode", scene._selection_mode)
            # Select the first collection via its real card target.
            box = next(
                box
                for box, callback in scene._targets
                if getattr(callback, "func", None) == scene._toggle_selection
                and box[2] - box[0] > 30
            )
            scene.canvas.yview_moveto(0)
            pump()
            point(
                scene.canvas.winfo_rootx() + (box[0] + box[2]) / 2,
                scene.canvas.winfo_rooty()
                + (box[1] + box[3]) / 2
                - scene.canvas.canvasy(0),
            )
            check("native card selects its members", len(scene._selected) > 0)
            capture("selection")
            button("Done")
            check(
                "native Done clears selection mode",
                not scene._selection_mode and not scene._selected,
            )
            scene.show_details(0)
            pump(0.8)
            capture("detail-top")
            labels = [
                scene.canvas.itemcget(i, "text")
                for i in scene.canvas.find_all()
                if scene.canvas.type(i) == "text"
            ]
            check(
                "duplicate action bar absent",
                "Additional Actions" not in labels and "Reveal in Folder" not in labels,
            )
            check("one folder action", labels.count("Show in Folder") == 1)
            check(
                "advanced actions use one contextual overflow",
                sum(
                    getattr(getattr(action, "func", None), "__name__", "")
                    == "_open_item_menu"
                    for _, action in scene._targets
                )
                == 1
                and "More" not in labels
                and "Open File" not in labels
                and "Update location" not in labels,
            )
            native_menus = []
            menu_commands = []
            original_menu = app_module.ContextMenu

            def actual_menu(*args, **kwargs):
                menu = original_menu(*args, **kwargs)
                add_command = menu.add_command

                def observed_command(**options):
                    callback = options["command"]
                    label = options["label"]

                    def invoke():
                        menu_commands.append(label)
                        return callback()

                    return add_command(**{**options, "command": invoke})

                menu.add_command = observed_command
                native_menus.append(menu)
                return menu

            def dismiss():
                for menu in native_menus:
                    menu.unpost()

            # AppKit tracks its native menu outside Tk's timer loop. A separate
            # OS-input driver must dismiss it, guarded to this exact QA process.
            escape_code = (
                "import time,sys,Quartz; from AppKit import NSWorkspace; time.sleep(1.2); "
                "pid=NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier(); "
                f"sys.exit(2) if pid != {os.getpid()} else None; "
                "[(Quartz.CGEventSetFlags(e,0),Quartz.CGEventPost(Quartz.kCGHIDEventTap,e),time.sleep(.05)) "
                "for e in [Quartz.CGEventCreateKeyboardEvent(None,53,True),Quartz.CGEventCreateKeyboardEvent(None,53,False)]]"
            )
            with patch.object(app_module, "ContextMenu", actual_menu):
                driver = subprocess.Popen([sys.executable, "-c", escape_code])
                try:
                    button("More")
                    check(
                        "native menu Escape driver targets QA process",
                        driver.wait(timeout=8) == 0,
                    )
                finally:
                    if driver.poll() is None:
                        driver.terminate()
                        driver.wait(timeout=8)
                pump(0.3)
            check("native More opens real contextual menus", len(native_menus) == 3)
            check(
                "Escape dismisses without invoking an item action", menu_commands == []
            )
            root_menu, files, _copy = native_menus
            entries = lambda menu: [
                menu.entrycget(i, "label")
                for i in range(menu.index("end") + 1)
                if menu.type(i) != "separator"
            ]
            check(
                "native More labels complete",
                entries(root_menu)
                == [
                    "Play",
                    "Show in Folder",
                    "Add to Collection\u2026",
                    "Edit notes, tags & category\u2026",
                    "File options",
                    "Copy",
                    "Delete\u2026",
                ],
            )
            check(
                "native file options reachable",
                "Copy file path" in entries(files)
                and "Update file location\u2026" in entries(files),
            )
            from yt_downloader.library_scene_facts import saved_file_path

            expected = saved_file_path(app.metadata_items[0])
            later = saved_file_path(app.metadata_items[1])
            check("menu subjects have distinct file paths", expected != later)
            scene.show_details(1)
            pump(0.2)
            files.invoke(
                next(
                    i
                    for i in range(files.index("end") + 1)
                    if files.entrycget(i, "label") == "Copy file path"
                )
            )
            check(
                "retained menu command keeps original subject after selection changes",
                app.clipboard_get() == expected,
            )
            check(
                "exactly the requested menu command ran",
                menu_commands == ["Copy file path"],
            )
            evidence["menu_commands"] = menu_commands
            dismiss()
            scene.canvas.yview_moveto(1)
            pump(0.5)
            capture("detail-bottom")
            check("native callbacks clean", not evidence["callback_errors"])
            evidence["passed"] = True
    finally:
        if app is not None:
            app.destroy()
        (output / f"library-{width}.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )


def test_native_more_menu_lifetime_stays_bounded_across_repeated_openings(monkeypatch):
    import tkinter as tk
    from unittest.mock import Mock

    from tests.test_scene_navigation import records

    root = tk.Tk()
    root.withdraw()
    root.metadata_items = list(records(2))
    root._archive_usage = Mock()
    root._library_scene_owner_action = Mock()
    root._run_library_copy_action = Mock()
    for name in (
        "_copy_tags",
        "_copy_description",
        "_copy_personal_tags",
        "_copy_personal_note",
        "_copy_thumbnail_url",
        "_copy_youtube_url",
    ):
        setattr(root, name, Mock())
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda *_a, **_k: None)

    def menus(widget):
        return sum(
            isinstance(child, tk.Menu) + menus(child)
            for child in widget.winfo_children()
        )

    try:
        app_module.DownloaderApp._show_library_scene_menu(root, 0)
        initial_menus = menus(root)
        initial_commands = len(root.tk.call("info", "commands"))
        assert initial_menus == 3
        for index in range(20):
            app_module.DownloaderApp._show_library_scene_menu(root, index % 2)
            assert menus(root) == initial_menus
            assert len(root.tk.call("info", "commands")) == initial_commands
    finally:
        root.destroy()
