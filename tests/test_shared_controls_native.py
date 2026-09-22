"""Real Tk controls plus OS keyboard; isolated callback data, no user-file writes."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from threading import Thread

import pytest

from tests.test_native_thumbnail_rendering import application as _application

application = _application

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="requires explicit Mac native controls and OS keyboard",
)


@pytest.mark.parametrize("kind", ["locations", "ancestry", "chapters"])
def test_readonly_native_list_selection_and_rendered_focus(application, tmp_path, kind):
    import tkinter as tk
    from tkinter import ttk

    import Quartz
    from AppKit import NSApplication
    from PIL import ImageChops

    from tests.test_archive_native import pump
    from yt_downloader.media_player_ui import ChapterList
    from yt_downloader.platform_services import capture_own_widget

    app = application
    host = tk.Toplevel(app)
    host.geometry("600x340+0+30")
    other = ttk.Button(host, text="Other focus target")
    other.pack()
    if kind == "chapters":
        tree = ChapterList(
            host,
            [
                {"title": "Opening", "start_time": 0},
                {"title": "Second chapter", "start_time": 12},
            ],
        )
    else:
        tree = ttk.Treeview(
            host,
            show="tree",
            selectmode="browse",
            takefocus=True,
            style="ArchiveLocations.Treeview"
            if kind == "locations"
            else "Archive.Folders.Treeview",
        )
        tree.insert("", "end", iid="0", text="Original folder")
        tree.insert("", "end", iid="1", text="Second folder")
    tree.pack(fill="both", expand=True, padx=15, pady=15)
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))

    def key(code):
        for down in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(None, code, down)
            Quartz.CGEventSetFlags(event, 0)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            pump(app, 0.04)

    def capture(label):
        pump(app, 0.08)
        image = capture_own_widget(tree)
        assert image is not None
        image.save(output / f"list-{kind}-{label}.png")
        return image.convert("RGB")

    def different(first, second):
        return sum(
            pixel != (0, 0, 0)
            for pixel in ImageChops.difference(first, second).get_flattened_data()
        )

    try:
        pump(app, 0.2)
        before = {iid: tree.item(iid) for iid in tree.get_children()}
        tree.selection_set("0")
        tree.focus("0")
        other.focus_force()
        unfocused = capture("selected-unfocused")
        assert tree.focus_get() is other
        tree.focus_force()
        focused = capture("selected-focused")
        assert tree.focus_get() is tree and "focus" in tree.state()
        x, y, width, height = tree.bbox("0")
        sx, sy = (
            focused.width / tree.winfo_width(),
            focused.height / tree.winfo_height(),
        )
        region = tuple(
            round(v) for v in (x * sx, y * sy, (x + width) * sx, (y + height) * sy)
        )
        focus_pixels = different(unfocused.crop(region), focused.crop(region))
        key(125)  # OS Down
        assert tree.selection() == ("1",) and tree.focus() == "1"
        moved = capture("second-selected")
        key(7)  # OS x: a readonly tree must not edit a row.
        assert {iid: tree.item(iid) for iid in tree.get_children()} == before
        assert different(focused, moved) > 0
        # Negative: leave the actual focus on the other control. A selected row
        # alone must not be misclassified as the focused rendering.
        tree.selection_set("0")
        tree.focus("0")
        other.focus_force()
        withheld = capture("focus-withheld-negative")
        negative_pixels = different(unfocused.crop(region), withheld.crop(region))
        evidence = {
            "kind": kind,
            "style": tree.cget("style"),
            "focus_changed_pixels": focus_pixels,
            "focus_row_rgb_region": region,
            "withheld_focus_changed_pixels": negative_pixels,
            "os_down_selected_second": True,
            "readonly_rows_unchanged": True,
            "scope": "Production native list styles/ChapterList in isolated app; current theme",
        }
        (output / f"list-{kind}.json").write_text(json.dumps(evidence, indent=2) + "\n")
        assert focus_pixels > width * height * sx * sy / 4, (
            "Actual keyboard focus has no substantial rendered distinction"
        )
        assert negative_pixels == 0, (
            "Focus-withheld negative must remain visually unfocused"
        )
    finally:
        host.destroy()


def test_mp3_metadata_checkbox_mode_focus_and_durable_setting(application, tmp_path):
    import Quartz
    from AppKit import NSApplication, NSWorkspace

    from tests.test_archive_native import native_descendants, pump, wait_for
    from yt_downloader.platform_services import capture_own_widget
    from yt_downloader.settings_store import load_settings
    from yt_downloader.ui_theme import THEME
    from yt_downloader.ui_widgets import ModernCheckbox

    app = application
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    app.output_type_var.set("MP4")
    app._show_focus_settings()
    dialog = app._focus_settings_dialog
    dialog.popup.geometry("900x800+0+30")
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    pump(app, 0.2)

    def checkbox():
        return next(
            w
            for w in native_descendants(app._focus_settings_dialog.popup)
            if isinstance(w, ModernCheckbox)
            and w.variable is app.mp3_embed_metadata_var
        )

    control = checkbox()
    assert not control.winfo_ismapped()
    app.output_type_var.set("MP3")
    pump(app, 0.2)
    assert control.winfo_ismapped() and "disabled" not in control.state()
    assert control._text == "Embed title, artist, and tags"
    original = bool(control.variable.get())
    consent = bool(app.anonymous_usage_analytics_var.get())
    path = app.settings_persistence.path

    def focus_control():
        current = checkbox()
        surface = app._focus_settings_dialog.dialog_surface
        y = current.winfo_rooty() - surface.body.winfo_rooty()
        surface.viewport.yview_moveto(
            max(0, y - 80) / max(1, surface.body.winfo_height())
        )
        current.focus_force()
        pump(app, 0.08)
        assert current.focus_get() is current
        assert current._label.cget("fg") == THEME["text"]
        return current

    def space():
        assert (
            NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier()
            == os.getpid()
        )
        for down in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(None, 49, down)
            Quartz.CGEventSetFlags(event, 0)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            pump(app, 0.05)

    focus_control()
    space()
    assert bool(control.variable.get()) is not original
    wait_for(
        app, lambda: load_settings(path).get("mp3_embed_metadata") is (not original)
    )
    assert load_settings(path)["mp3_embed_metadata"] is not original
    capture_own_widget(control).save(output / "mp3-metadata-focused.png")
    app.output_type_var.set("MP4")
    pump(app, 0.15)
    assert not control.winfo_ismapped()
    app.output_type_var.set("MP3")
    pump(app, 0.15)
    assert control.winfo_ismapped() and bool(control.variable.get()) is not original
    dialog.close()
    app._show_focus_settings()
    pump(app, 0.15)
    control = focus_control()
    assert bool(control.variable.get()) is not original
    space()
    assert bool(control.variable.get()) is original
    wait_for(app, lambda: load_settings(path).get("mp3_embed_metadata") is original)
    assert bool(app.anonymous_usage_analytics_var.get()) is consent
    (output / "mp3-metadata-result.json").write_text(
        json.dumps(
            {
                "scope": "Actual isolated Settings; OS Space; normal debounced persistence; current theme only",
                "hidden_in_mp4": True,
                "shown_enabled_in_mp3": True,
                "focus_and_label": True,
                "initial": original,
                "toggled_persisted": not original,
                "reopen_retained": True,
                "restored_persisted": original,
                "consent_unchanged": True,
                "limits": "No MP3 export/ID3 output, six-theme pixels, physical input or packaged claim",
            },
            indent=2,
        )
        + "\n"
    )
    app._focus_settings_dialog.close()


def test_collection_footer_placeholder_scoped_keys_and_input_lifetime(tmp_path):
    import subprocess
    import tkinter as tk

    import Quartz
    from AppKit import (
        NSApplication,
        NSApplicationActivateIgnoringOtherApps,
        NSRunningApplication,
    )

    from yt_downloader.library_collection_ui import LibraryCollectionDialog
    from yt_downloader.ui_styles import apply_product_styles
    from yt_downloader.ui_widgets import ActionDialogSurface, KeyboardScope

    root = tk.Tk()
    root.title("VODForge isolated UI checks")
    root.geometry("600x500+280+140")
    apply_product_styles(root)
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "scope": "Real Tk collection geometry and OS Return/Escape, synthetic collection data; no physical trackpad claim",
        "checks": [],
        "captures": [],
        "errors": [],
    }
    root.report_callback_exception = lambda *args: result["errors"].append(str(args[1]))

    def pump(seconds=0.2):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)

    def check(name, value):
        result["checks"].append({"name": name, "passed": bool(value)})
        assert value, name

    def key(code):
        def send():
            for down in (True, False):
                event = Quartz.CGEventCreateKeyboardEvent(None, code, down)
                Quartz.CGEventSetFlags(event, 0)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                time.sleep(0.06)

        thread = Thread(target=send, daemon=True)
        thread.start()
        pump(0.4)
        thread.join(1)
        check("OS input driver completed", not thread.is_alive())

    def capture(dialog, name):
        path = output / (name + ".png")
        windows = [
            w
            for w in Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID
            )
            if w.get("kCGWindowOwnerPID") == os.getpid()
            and w.get("kCGWindowName") == dialog.popup.title()
        ]
        check("unique popup window for capture", len(windows) == 1)
        subprocess.run(
            [
                "/usr/sbin/screencapture",
                "-x",
                "-o",
                "-l",
                str(windows[0]["kCGWindowNumber"]),
                str(path),
            ],
            check=True,
        )
        result["captures"].append(str(path))

    saved, parent_keys = [], []
    try:
        KeyboardScope(root, {"<Escape>": lambda: parent_keys.append("escape")})
        dialog = LibraryCollectionDialog(
            root,
            [(str(i), f"Saved video {i:03}") for i in range(200)],
            lambda name, owners: saved.append((name, owners)),
        )
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        dialog.popup.lift()
        dialog.name_entry.focus_force()
        pump()
        for width, height in [(540, 480), (640, 520), (500, 400)]:
            dialog.popup.geometry(f"{width}x{height}+300+160")
            pump()
            check(
                f"Save footer visible {width}",
                dialog.dialog_surface.action_is_visible(dialog.save_button),
            )
            check(f"Save labeled {width}", dialog.save_button.cget("text") == "Save")
            check(
                f"Save usable height {width}", dialog.save_button.winfo_height() >= 28
            )
            check(
                f"Empty focus preserves hint {width}",
                dialog.name_entry._placeholder.winfo_ismapped(),
            )
            check(f"Placeholder is not stored {width}", dialog.name.get() == "")
        capture(dialog, "collection-empty")
        dialog.name_entry.focus_force()
        key(36)
        check("invalid Enter keeps popup", dialog.popup.winfo_exists() and not saved)
        check("invalid Enter explains error", bool(dialog.error.get()))
        dialog.name.set("QA collection")
        pump()
        check(
            "Typing hides placeholder",
            not dialog.name_entry._placeholder.winfo_ismapped(),
        )
        dialog.name.set("")
        pump()
        check(
            "Clearing restores placeholder",
            dialog.name_entry._placeholder.winfo_ismapped(),
        )
        dialog.name.set("QA collection")
        dialog.items.selection_set(17)
        capture(dialog, "collection-selected")
        dialog.name_entry.focus_force()
        key(36)
        check("Enter saves correct item once", saved == [("QA collection", ("17",))])
        check("Enter closes popup", not dialog.popup.winfo_exists())
        dialog = LibraryCollectionDialog(
            root, [("one", "One video")], lambda *args: saved.append(args)
        )
        dialog.name.set("Second collection")
        dialog.items.selection_set(0)
        dialog.items.focus_force()
        pump()
        key(36)
        check(
            "Enter from list saves once",
            saved[-1] == ("Second collection", ("one",)) and len(saved) == 2,
        )
        dialog = LibraryCollectionDialog(
            root, [("one", "One video")], lambda *args: saved.append(args)
        )
        nested = tk.Toplevel(dialog.popup)
        nested.title("Nested editor")
        nested.geometry("280x180+350+220")
        surface = ActionDialogSurface(nested, modal=True)
        surface.bind_keys({"<Escape>": nested.destroy})
        nested.focus_force()
        pump()
        key(53)
        check(
            "nested Escape closes nested only",
            not nested.winfo_exists() and dialog.popup.winfo_exists(),
        )
        check(
            "nested close restores collection grab", root.grab_current() is dialog.popup
        )
        dialog.name_entry.focus_force()
        pump()
        key(53)
        check("Escape closes active popup", not dialog.popup.winfo_exists())
        check("Escape did not cascade to parent", parent_keys == [])
        command_counts = []
        for _ in range(12):
            repeated = LibraryCollectionDialog(
                root, [("one", "One video")], lambda *args: None
            )
            pump(0.03)
            repeated.popup.destroy()
            pump(0.03)
            command_counts.append(len(root.tk.call("info", "commands")))
        result["tcl_command_counts"] = command_counts
        check(
            "repeated dialogs keep bounded Tcl commands",
            max(command_counts) - min(command_counts) <= 2,
        )
        check("No callback errors", not result["errors"])
        result["passed"] = True
    finally:
        root.destroy()
        (output / "shared-controls-native.json").write_text(
            json.dumps(result, indent=2) + chr(10)
        )
        restore = os.environ.get("VODFORGE_RESTORE_APP_PID")
        if restore:
            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(
                int(restore)
            )
            if app:
                app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)


@pytest.mark.parametrize(
    "size,bold", [(14, True), (14, False), (15, False), (22, True)]
)
@pytest.mark.parametrize("scale", [1.0, 2.0])
def test_scene_text_fitting_honors_actual_canvas_boundary(size, bold, scale):
    """Font.measure can round down where the Mac Canvas wraps another line."""
    import tkinter as tk
    import tkinter.font as tkfont
    from types import SimpleNamespace

    from yt_downloader.library_scene_ui import LibraryScene
    from yt_downloader.scene_components import ScenePainter, scene_font

    root = tk.Tk()
    root.withdraw()
    try:
        root.tk.call("tk", "scaling", scale)
        root._text_fonts = {}
        canvas = tk.Canvas(root)
        view = SimpleNamespace(
            canvas=canvas,
            _fit=lambda value, width, lines, font: LibraryScene._fit(
                root, value, width, lines, font
            ),
        )
        painter = ScenePainter(view)
        font_spec = scene_font(size, bold=bold)
        font = tkfont.Font(
            root=root, family=font_spec[0], size=font_spec[1], weight=font_spec[2]
        )
        for text in (
            "Molokini crater Maui snorkel",
            "Long channel title with WWW and iii",
            "日本語のタイトル and café",
            "WWWi" * 30,
            "First line\nSecond line continuing across the available width",
        ):
            measured = font.measure(text)
            for width in (70, 130, measured - 1, measured, measured + 1):
                for lines in (1, 2):
                    item = painter.text(
                        10, 10, text, width=width, size=size, bold=bold, lines=lines
                    )
                    box = canvas.bbox(item)
                    assert box is not None
                    assert box[3] - box[1] <= lines * font.metrics("linespace"), (
                        text,
                        width,
                        lines,
                        canvas.itemcget(item, "text"),
                        box,
                    )
                    assert box[2] <= 10 + width + 2
                    canvas.delete(item)
    finally:
        root.destroy()


@pytest.mark.parametrize("target_name", ["self", "_box", "_label"])
def test_checkbox_pointer_admission_waits_for_valid_release(target_name):
    import tkinter as tk

    from yt_downloader.ui_widgets import ModernCheckbox

    root = tk.Tk()
    value = tk.BooleanVar(root, False)
    calls = []
    control = ModernCheckbox(
        root,
        text="Keep a copy",
        variable=value,
        command=lambda: calls.append(value.get()),
    )
    control.pack(padx=10, pady=10)
    root.update()
    target = control if target_name == "self" else getattr(control, target_name)
    try:
        target.event_generate("<ButtonPress-1>", x=5, y=5)
        root.update()
        assert not value.get() and not calls, "Checkbox must not commit on mouse-down"
        target.event_generate("<ButtonRelease-1>", x=-100, y=-100)
        root.update()
        assert not value.get() and not calls
        target.event_generate("<ButtonPress-1>", x=5, y=5)
        control.state(["disabled"])
        control.state(["!disabled"])
        target.event_generate("<ButtonRelease-1>", x=5, y=5)
        root.update()
        assert not value.get() and not calls
        target.event_generate("<ButtonPress-1>", x=5, y=5)
        target.event_generate("<ButtonRelease-1>", x=5, y=5)
        root.update()
        assert value.get() and calls == [True]
    finally:
        root.destroy()


@pytest.mark.parametrize(
    "compact,separated", [(False, False), (True, False), (False, True)]
)
def test_segmented_selection_commits_only_current_released_segment(compact, separated):
    import tkinter as tk

    from yt_downloader.ui_widgets import SegmentedSelector

    root = tk.Tk()
    value = tk.StringVar(root, "First")
    control = SegmentedSelector(
        root,
        variable=value,
        values=("First", "Second"),
        compact=compact,
        separated=separated,
    )
    control.pack()
    root.update()
    second = control._labels["Second"]
    try:
        second.event_generate("<ButtonPress-1>", x=5, y=5)
        root.update()
        assert value.get() == "First", "Selection must not commit on mouse-down"
        second.event_generate("<ButtonRelease-1>", x=-20, y=-20)
        root.update()
        assert value.get() == "First"
        second.event_generate("<ButtonPress-1>", x=5, y=5)
        control._labels["First"].event_generate("<ButtonRelease-1>", x=5, y=5)
        root.update()
        assert value.get() == "First"
        second.event_generate("<ButtonPress-1>", x=5, y=5)
        second.event_generate("<ButtonRelease-1>", x=5, y=5)
        root.update()
        assert value.get() == "Second"
    finally:
        root.destroy()


@pytest.mark.parametrize("replacement", [("new",), (), ("B", "A")])
def test_choice_option_replacement_retires_queued_selection(replacement):
    import tkinter as tk

    from yt_downloader.ui_styles import apply_product_styles
    from yt_downloader.ui_widgets import ChoiceDropdown, ChoiceMenu

    root = tk.Tk()
    root.geometry("600x420+200+120")
    apply_product_styles(root)
    value = tk.StringVar(root, "A")
    field = ChoiceDropdown(root, textvariable=value, values=("A", "B"))
    field.pack(padx=20, pady=20)
    events = []
    field.bind("<<ComboboxSelected>>", lambda _event: events.append(value.get()))
    try:
        root.update()
        root.focus_force()
        field.open_popover()
        assert field._popover is not None
        old_menu = next(
            w for w in field._popover.winfo_children() if isinstance(w, ChoiceMenu)
        )
        old_menu.selection_set(1)
        field.configure(values=replacement)
        # Simulate an already queued keyboard commit from the retired menu.
        field._commit_listbox(old_menu)
        root.update()
        assert value.get() == "A" and events == []
        assert field._popover is None

        field.configure(values=("fresh A", "fresh B"))
        field.open_popover()
        assert field._popover is not None
        menu = next(
            w for w in field._popover.winfo_children() if isinstance(w, ChoiceMenu)
        )
        menu.selection_set(1)
        field._commit_listbox(menu)
        root.update()
        assert value.get() == "fresh B" and events == ["fresh B"]
    finally:
        root.destroy()


def test_identical_choice_options_preserve_current_menu_intent():
    import tkinter as tk

    from yt_downloader.ui_styles import apply_product_styles
    from yt_downloader.ui_widgets import ChoiceDropdown, ChoiceMenu

    root = tk.Tk()
    root.geometry("600x420+200+120")
    apply_product_styles(root)
    value = tk.StringVar(root, "A")
    field = ChoiceDropdown(root, textvariable=value, values=("A", "B"))
    field.pack(padx=20, pady=20)
    try:
        root.update()
        root.focus_force()
        field.open_popover()
        popup = field._popover
        assert popup is not None
        menu = next(w for w in popup.winfo_children() if isinstance(w, ChoiceMenu))
        menu.selection_set(1)
        field.configure(values=["A", "B"])
        assert field._popover is popup
        field._commit_listbox(menu)
        root.update()
        assert value.get() == "B" and field._popover is None
    finally:
        root.destroy()


@pytest.mark.parametrize("orient", ["vertical", "horizontal"])
@pytest.mark.parametrize("retirement", ["hidden_parent", "content_fits"])
def test_scrollbar_retired_drag_cannot_move_remapped_or_replaced_content(
    orient, retirement
):
    """Tk-dispatched events; no physical-pointer or smoothness claim."""
    import tkinter as tk

    from yt_downloader.ui_widgets import SleekScrollbar

    root = tk.Tk()
    root.geometry("420x340+280+140")
    host = tk.Frame(root)
    host.pack(fill="both", expand=True)
    calls = []
    control = SleekScrollbar(
        host, command=lambda *args: calls.append(args), orient=orient
    )
    control.pack(fill="y" if orient == "vertical" else "x", expand=True)
    root.update()
    control.set(0.0, 0.25)

    def event(name, position):
        control.event_generate(
            name,
            x=4 if orient == "vertical" else position,
            y=position if orient == "vertical" else 4,
        )
        root.update()

    try:
        event("<ButtonPress-1>", 10)
        event("<B1-Motion>", 50)
        assert calls and calls[-1][0] == "moveto" and calls[-1][1] > 0
        calls.clear()
        if retirement == "hidden_parent":
            host.pack_forget()
            root.update()
            host.pack(fill="both", expand=True)
            root.update()
        else:
            control.set(0, 1)
            control.set(0, 0.25)
        event("<B1-Motion>", 100)
        event("<ButtonRelease-1>", 100)
        assert calls == [], (
            "Retired drag moved new or remapped content without a fresh press"
        )
        event("<ButtonPress-1>", 10)
        event("<B1-Motion>", 70)
        event("<ButtonRelease-1>", 70)
        assert len(calls) == 1 and calls[0][1] > 0, "Fresh drag must remain usable"
    finally:
        root.destroy()


@pytest.mark.parametrize("orient", ["vertical", "horizontal"])
def test_scrollbar_drag_survives_cross_axis_pointer_exit_until_release(orient):
    """Leaving a narrow thumb must not interrupt an otherwise active drag."""
    import tkinter as tk

    from yt_downloader.ui_widgets import SleekScrollbar

    root = tk.Tk()
    root.geometry("420x340+280+140")
    calls = []
    control = SleekScrollbar(
        root, command=lambda *args: calls.append(args), orient=orient
    )
    control.pack(fill="y" if orient == "vertical" else "x", expand=True)
    root.update()
    control.set(0, 0.25)
    try:
        control.event_generate(
            "<ButtonPress-1>",
            x=4 if orient == "vertical" else 10,
            y=10 if orient == "vertical" else 4,
        )
        control.event_generate("<Leave>")
        control.event_generate(
            "<B1-Motion>",
            x=-20 if orient == "vertical" else 100,
            y=100 if orient == "vertical" else -20,
        )
        root.update()
        assert len(calls) == 1 and calls[0][0] == "moveto" and calls[0][1] > 0
        control.event_generate("<ButtonRelease-1>")
        control.event_generate("<B1-Motion>", x=150, y=150)
        root.update()
        assert len(calls) == 1, "Released drag must not follow later motion"
    finally:
        root.destroy()


@pytest.mark.parametrize("orient", ["vertical", "horizontal"])
def test_scrollbar_os_drag_preserves_axis_owner_and_stops_on_release(orient, tmp_path):
    """Real Canvas movement under Quartz input; not physical-device acceptance."""
    import tkinter as tk

    import Quartz
    from AppKit import NSApplication

    from yt_downloader.ui_widgets import SleekScrollbar

    root = tk.Tk()
    root.title("VODForge isolated scrollbar interaction")
    root.geometry("480x360+60+140")
    host = tk.Frame(root)
    host.pack(fill="both", expand=True, padx=20, pady=20)
    canvas = tk.Canvas(
        host,
        width=420,
        height=280,
        highlightthickness=0,
        scrollregion=(0, 0, 1600, 1600),
    )
    canvas.pack(side="left" if orient == "vertical" else "top")
    trace = []
    view = canvas.yview if orient == "vertical" else canvas.xview
    other = canvas.xview if orient == "vertical" else canvas.yview

    def move(*args):
        before = view()
        view(*args)
        trace.append(
            {
                "t": time.monotonic(),
                "args": args,
                "before": before,
                "after": view(),
                "other": other(),
            }
        )

    control = SleekScrollbar(host, command=move, orient=orient)
    control.pack(
        side="right" if orient == "vertical" else "bottom",
        fill="y" if orient == "vertical" else "x",
    )
    canvas.configure(
        **{"yscrollcommand" if orient == "vertical" else "xscrollcommand": control.set}
    )
    for i in range(30):
        canvas.create_text(40, 20 + i * 40, text=f"Saved item {i}")
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    root.lift()

    def pump():
        until = time.monotonic() + 0.15
        while time.monotonic() < until:
            root.update()
            time.sleep(0.005)

    received = []
    for sequence in ("<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>"):
        control.bind(
            sequence,
            lambda event, name=sequence: received.append(
                {
                    "sequence": name,
                    "t": time.monotonic(),
                    "x": event.x,
                    "y": event.y,
                }
            ),
            add="+",
        )
    events = []
    last = (0, 0)

    def post(kind, point):
        nonlocal last
        last = point
        event = Quartz.CGEventCreateMouseEvent(
            None, kind, point, Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventSetFlags(event, 0)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        events.append({"t": time.monotonic(), "kind": int(kind), "point": point})

    result = {
        "scope": "OS-injected source-native scrollbar and actual Canvas fractions; no physical or smoothness claim",
        "orientation": orient,
        "events": events,
        "moves": trace,
        "passed": False,
        "received": received,
    }
    try:
        pump()
        start = (
            (control.winfo_rootx() + 4, control.winfo_rooty() + 10)
            if orient == "vertical"
            else (control.winfo_rootx() + 10, control.winfo_rooty() + 4)
        )
        outside = (
            (start[0] - 35, start[1] + 120)
            if orient == "vertical"
            else (start[0] + 120, start[1] - 35)
        )
        further = (
            (outside[0], outside[1] + 50)
            if orient == "vertical"
            else (outside[0] + 50, outside[1])
        )
        initial, other_initial = view(), other()
        geometry = root.geometry()

        def drive():
            for kind, point in (
                (Quartz.kCGEventMouseMoved, start),
                (Quartz.kCGEventLeftMouseDown, start),
                (Quartz.kCGEventLeftMouseDragged, outside),
                (Quartz.kCGEventLeftMouseUp, outside),
                (Quartz.kCGEventMouseMoved, further),
            ):
                post(kind, point)
                time.sleep(0.15)

        driver = Thread(target=drive, daemon=True)
        driver.start()
        while driver.is_alive():
            pump()
        driver.join(1)
        pump()
        released = next(
            e["t"] for e in events if e["kind"] == Quartz.kCGEventLeftMouseUp
        )
        assert {row["sequence"] for row in received} == {
            "<ButtonPress-1>",
            "<B1-Motion>",
            "<ButtonRelease-1>",
        }, (
            "Native input did not reach the intended control; this fixture cannot qualify behavior"
        )
        active_moves = [m for m in trace if m["t"] < released]
        assert active_moves, "Content must respond during the actual pressed interval"
        dragged = active_moves[-1]["after"]
        assert dragged[0] > initial[0] + 0.05, (
            "Actual content must follow a drag outside the thin track"
        )
        assert other() == other_initial and all(
            m["other"] == other_initial for m in trace
        )
        assert root.geometry() == geometry, (
            "Scrollbar input must not resize or move the window"
        )
        assert view() == dragged, "Actual content followed pointer motion after release"
        assert len(events) == 5 and events[-1]["t"] - events[0]["t"] < 2
        result.update(
            initial=initial,
            dragged=dragged,
            after_release=view(),
            window_geometry=geometry,
            passed=True,
        )
    finally:
        Quartz.CGEventPost(
            Quartz.kCGHIDEventTap,
            Quartz.CGEventCreateMouseEvent(
                None, Quartz.kCGEventLeftMouseUp, last, Quartz.kCGMouseButtonLeft
            ),
        )
        root.destroy()
        output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        output.mkdir(parents=True, exist_ok=True)
        (output / f"scrollbar-os-{orient}.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )


@pytest.mark.parametrize("hidden_target", ["canvas", "ancestor"])
def test_canvas_action_press_cannot_survive_hide_and_remap(hidden_target):
    import tkinter as tk

    from yt_downloader.ui_canvas_actions import CanvasActions

    root = tk.Tk()
    root.geometry("280x200+300+160")
    host = tk.Frame(root)
    host.pack(fill="both", expand=True)
    canvas = tk.Canvas(host, width=220, height=140)
    canvas.pack()
    calls = []
    targets = [((10, 10, 100, 60), lambda: calls.append("selected"))]
    CanvasActions(canvas, lambda: targets)
    root.update()
    try:
        canvas.event_generate("<ButtonPress-1>", x=30, y=30)
        root.update()
        assert calls == []
        hidden = canvas if hidden_target == "canvas" else host
        hidden.pack_forget()
        root.update()
        hidden.pack()
        root.update()
        canvas.event_generate("<ButtonRelease-1>", x=30, y=30)
        root.update()
        assert calls == [], "A release revived a press from the hidden view"
        canvas.event_generate("<ButtonPress-1>", x=30, y=30)
        canvas.event_generate("<ButtonRelease-1>", x=30, y=30)
        root.update()
        assert calls == ["selected"], (
            "Fresh intent must still activate the retained target"
        )
    finally:
        root.destroy()


@pytest.mark.parametrize(
    "lifetime", ["external_variable", "animation_timer", "initial_idle"]
)
def test_progress_indicator_destruction_releases_native_work(lifetime):
    import tkinter as tk

    from yt_downloader.ui_widgets import SleekProgressbar

    root = tk.Tk()
    root.geometry("300x160+320+160")
    value = tk.DoubleVar(root, 0)
    initial_traces = value.trace_info()
    pending_before = set(root.tk.splitlist(root.tk.call("after", "info")))
    control = SleekProgressbar(root, variable=value)
    control.pack(fill="x", padx=20)
    try:
        if lifetime != "initial_idle":
            root.update()
        if lifetime == "animation_timer":
            control.start(20)
        owned_pending = (
            set(root.tk.splitlist(root.tk.call("after", "info"))) - pending_before
        )
        if lifetime in {"animation_timer", "initial_idle"}:
            assert owned_pending, "Fixture must create pending native work"
        control.destroy()
        if lifetime == "external_variable":
            assert value.trace_info() == initial_traces, (
                "Destroyed indicator retained its shared variable subscription"
            )
        else:
            pending_after = set(root.tk.splitlist(root.tk.call("after", "info")))
            assert not (owned_pending & pending_after), (
                "Destroyed indicator left queued Tcl work"
            )
        successor = SleekProgressbar(root, variable=value)
        successor.pack(fill="x", padx=20)
        value.set(50)
        root.update()
        rectangles = [
            successor.coords(item)
            for item in successor.find_all()
            if successor.type(item) == "rectangle"
        ]
        assert any(
            abs(box[2] - successor.winfo_width() * 0.5) <= 1 for box in rectangles
        )
        successor.destroy()
        assert value.trace_info() == initial_traces
    finally:
        root.destroy()


@pytest.mark.parametrize(
    "compact,separated", [(False, False), (True, False), (False, True)]
)
@pytest.mark.parametrize("selected", ["First", "Second"])
def test_segmented_keyboard_focus_is_visible_without_moving_content(
    compact, separated, selected, tmp_path
):
    import tkinter as tk

    from PIL import ImageChops

    from yt_downloader.platform_services import capture_own_widget
    from yt_downloader.ui_widgets import SegmentedSelector

    root = tk.Tk()
    root.geometry("360x180+240+160")
    value = tk.StringVar(root, selected)
    control = SegmentedSelector(
        root,
        variable=value,
        values=("First", "Second"),
        compact=compact,
        separated=separated,
    )
    control.pack(pady=25)
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    name = f"segment-focus-{compact}-{separated}-{selected}"
    try:
        root.update()
        root.focus_force()
        root.update()
        second = control._labels["Second"]
        size = (control.winfo_width(), control.winfo_height())
        before = capture_own_widget(control)
        assert before is not None
        before.save(output / f"{name}-before.png")
        second.focus_force()
        root.update()
        assert root.focus_get() is second
        focused = capture_own_widget(control)
        assert focused is not None
        focused.save(output / f"{name}-during.png")
        assert ImageChops.difference(
            before.convert("RGB"), focused.convert("RGB")
        ).getbbox(), (
            "Keyboard focus moved onto the option without any visible indication"
        )
        assert value.get() == selected, "Focus alone must not select"
        assert (control.winfo_width(), control.winfo_height()) == size
        root.focus_force()
        root.update()
        after = capture_own_widget(control)
        assert after is not None
        after.save(output / f"{name}-after.png")
        assert (
            ImageChops.difference(before.convert("RGB"), after.convert("RGB")).getbbox()
            is None
        )
        second.focus_force()
        root.update()
        second.event_generate("<space>")
        root.update()
        assert value.get() == "Second"
    finally:
        root.destroy()


@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("retired", [False, True])
def test_native_run_menu_retains_execution_owner(monkeypatch, tmp_path, index, retired):
    import tkinter as tk
    from dataclasses import replace
    from types import MethodType

    from tests.test_run_identity import make_job
    from yt_downloader.app import DownloaderApp

    root = tk.Tk()
    menus = []
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda menu, *args: menus.append(menu))
    job = make_job(tmp_path)
    root.active_job = job
    calls = []
    root._cancel = lambda: calls.append("cancel")
    root._skip_video = lambda: calls.append("skip_item")
    root._skip_url = lambda: calls.append("skip_source")
    root._youtube_url_for_run_record = lambda _: ""
    root._select_focus_view = lambda _: None
    root._run_focus_active_action = MethodType(
        DownloaderApp._run_focus_active_action, root
    )
    try:
        DownloaderApp._show_focus_run_actions_menu(root, {"kind": "active", "job": job})
        assert isinstance(menus[-1], tk.Menu)
        root.active_job = replace(job, run_id="successor") if retired else job
        menus[-1].invoke(index)
        root.update()
        assert calls == (
            [] if retired else [["cancel", "skip_item", "skip_source"][index]]
        )
    finally:
        root.destroy()


@pytest.mark.parametrize("surface", ["library", "watch"])
@pytest.mark.parametrize("retirement", ["replacement", "owner_hidden"])
def test_context_menu_lifetime_is_bounded_to_current_surface(
    monkeypatch, surface, retirement
):
    import tkinter as tk

    from yt_downloader.library_scene_ui import LibraryScene
    from yt_downloader.watch_scene_ui import WatchSceneMixin

    root = tk.Tk()
    host = tk.Frame(root)
    host.pack()
    host._records = ({"id": "item", "vodforge_output_dir": "/synthetic/item"},)
    host._set_sort = lambda _: None
    host._on_details = lambda _: None
    host._scene_open = lambda _: None
    menus = []
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda menu, *args: menus.append(menu))
    root.update()

    def open_menu():
        if surface == "library":
            LibraryScene._sort_menu(host)
        else:
            WatchSceneMixin._scene_more(host, 0)

    try:
        for _ in range(12):
            open_menu()
        if retirement == "replacement":
            assert sum(bool(menu.winfo_exists()) for menu in menus) == 1, (
                "Repeated openings retained old native menus and their callbacks"
            )
            assert menus[-1].winfo_exists()
        else:
            host.pack_forget()
            root.update()
            assert not any(menu.winfo_exists() for menu in menus), (
                "Menus outlived the surface that supplied their action targets"
            )
    finally:
        root.destroy()


@pytest.mark.parametrize("retirement", ["replacement", "owner_hidden", "destroy"])
def test_context_menu_queued_callbacks_retire_without_disabling_fresh_actions(
    retirement,
):
    import tkinter as tk

    from yt_downloader.ui_context_menu import ContextMenu

    root = tk.Tk()
    host = tk.Frame(root)
    host.pack()
    root.update()
    baseline = set(root.tk.splitlist(root.tk.call("info", "commands")))
    calls, callbacks = [], []
    menu = ContextMenu(host, tearoff=False)
    original_register = menu._register

    def register(command, *args):
        callbacks.append(command)
        return original_register(command, *args)

    menu._register = register
    menu.add_command(label="Current action", command=lambda: calls.append("original"))
    try:
        # tk_popup can return before Windows delivers selection: merely
        # unposting must not destroy that still-owned pending command.
        menu.unpost()
        callbacks[0]()
        assert calls == ["original"]
        if retirement == "replacement":
            successor = ContextMenu(host, tearoff=False)
        elif retirement == "owner_hidden":
            host.pack_forget()
            root.update()
            host.pack()
            root.update()
            successor = ContextMenu(host, tearoff=False)
        else:
            menu.destroy()
            successor = ContextMenu(host, tearoff=False)
        callbacks[0]()
        assert calls == ["original"], "An old queued callback survived owner retirement"
        successor.add_command(
            label="Fresh action", command=lambda: calls.append("fresh")
        )
        successor.invoke(0)
        assert calls == ["original", "fresh"]
        menu.destroy()
        successor.destroy()
        assert set(root.tk.splitlist(root.tk.call("info", "commands"))) == baseline
    finally:
        root.destroy()


def test_context_menu_cascades_share_lifetime_but_other_windows_do_not():
    import tkinter as tk

    from yt_downloader.ui_context_menu import ContextMenu

    root = tk.Tk()
    other = tk.Toplevel(root)
    calls = []
    try:
        parent = ContextMenu(root, tearoff=False)
        cascade = ContextMenu(parent, tearoff=False)
        cascade.add_command(
            label="Nested action", command=lambda: calls.append("nested")
        )
        parent.add_cascade(label="Options", menu=cascade)
        separate = ContextMenu(other, tearoff=False)
        separate.add_command(
            label="Other window", command=lambda: calls.append("other")
        )
        assert parent.winfo_exists() and cascade.winfo_exists()
        cascade.invoke(0)
        successor = ContextMenu(root, tearoff=False)
        assert not parent.winfo_exists() and not cascade.winfo_exists()
        assert separate.winfo_exists() and successor.winfo_exists()
        separate.invoke(0)
        assert calls == ["nested", "other"]
    finally:
        root.destroy()


@pytest.mark.parametrize("change", ["same", "reordered", "removed"])
def test_watch_native_menu_resolves_original_media_at_commit(monkeypatch, change):
    import tkinter as tk

    from yt_downloader.watch_scene_ui import WatchSceneMixin

    root = tk.Tk()
    menus, calls, usage = [], [], []
    root._records = (
        {"id": "original", "vodforge_output_dir": "/synthetic/original"},
        {"id": "later", "vodforge_output_dir": "/synthetic/later"},
    )
    root._scene_open = lambda *_: None
    root._on_details = lambda index: calls.append(root._records[index]["id"])
    root._on_usage = lambda *args: usage.append(args)
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda menu, *args: menus.append(menu))
    try:
        WatchSceneMixin._scene_more(root, 0)
        if change == "reordered":
            root._records = tuple(reversed(root._records))
        elif change == "removed":
            root._records = root._records[1:]
        menus[-1].invoke(0)
        root.update()
        assert calls == ([] if change == "removed" else ["original"])
        assert usage == ([("watch", "details_retired")] if change == "removed" else [])
    finally:
        root.destroy()


@pytest.mark.parametrize("value_at_start", [0, 50, 100])
def test_player_volume_focus_is_visible_and_instance_local(value_at_start, tmp_path):
    import tkinter as tk

    from PIL import ImageChops

    from yt_downloader.media_player_ui import PlayerVolumeControl
    from yt_downloader.platform_services import capture_own_widget

    root = tk.Tk()
    root.geometry("360x180+60+100")
    value, other_value = tk.IntVar(root, value_at_start), tk.IntVar(root, 25)
    calls, other_calls = [], []
    control = PlayerVolumeControl(root, variable=value, command=calls.append)
    other = PlayerVolumeControl(root, variable=other_value, command=other_calls.append)
    control.pack(pady=20)
    other.pack(pady=20)
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    name = f"volume-focus-{value_at_start}"
    try:
        root.update()
        root.focus_force()
        root.update()
        before = capture_own_widget(control)
        other_before = capture_own_widget(other)
        assert before is not None and other_before is not None
        before.save(output / f"{name}-before.png")
        size = control.winfo_width(), control.winfo_height()
        control.focus_force()
        root.update()
        assert root.focus_get() is control
        during = capture_own_widget(control)
        other_during = capture_own_widget(other)
        assert during is not None and other_during is not None
        during.save(output / f"{name}-during.png")
        assert ImageChops.difference(
            before.convert("RGB"), during.convert("RGB")
        ).getbbox(), "Volume received keyboard focus without visible feedback"
        assert (
            ImageChops.difference(
                other_before.convert("RGB"), other_during.convert("RGB")
            ).getbbox()
            is None
        )
        assert (control.winfo_width(), control.winfo_height()) == size
        assert value.get() == value_at_start and other_value.get() == 25
        assert calls == other_calls == []
        root.focus_force()
        root.update()
        after = capture_own_widget(control)
        assert after is not None
        after.save(output / f"{name}-after.png")
        assert (
            ImageChops.difference(before.convert("RGB"), after.convert("RGB")).getbbox()
            is None
        )
        control.focus_force()
        root.update()
        control.event_generate("<Right>" if value_at_start < 100 else "<Left>")
        root.update()
        expected = value_at_start + (5 if value_at_start < 100 else -5)
        assert value.get() == expected and calls == [str(expected)]
        assert other_value.get() == 25 and other_calls == []
        control.destroy()
        assert value.trace_info() == []
    finally:
        root.destroy()


@pytest.mark.parametrize(
    "kind", ["checkbox", "segment", "choice", "placeholder", "search"]
)
@pytest.mark.parametrize("keep_external_owner", [False, True])
def test_destroyed_controls_release_variable_ownership_on_ui_thread(
    kind, keep_external_owner
):
    import tkinter as tk
    import weakref

    from yt_downloader.library_search_ui import LibrarySearchField
    from yt_downloader.ui_styles import apply_product_styles
    from yt_downloader.ui_widgets import (
        ChoiceDropdown,
        ModernCheckbox,
        PlaceholderEntry,
        SegmentedSelector,
    )

    root = tk.Tk()
    root.withdraw()
    apply_product_styles(root)
    value = (
        tk.BooleanVar(root, False)
        if kind == "checkbox"
        else tk.StringVar(root, "First")
    )
    reference = weakref.ref(value)
    external = value if keep_external_owner else None
    if kind == "checkbox":
        control = ModernCheckbox(
            root, text="Keep", variable=value, command=lambda bound=value: bound.get()
        )
    elif kind == "segment":
        control = SegmentedSelector(root, variable=value, values=("First", "Second"))
    elif kind == "placeholder":
        control = PlaceholderEntry(root, textvariable=value, placeholder="Name")
    elif kind == "search":
        control = LibrarySearchField(root, variable=value)
    else:
        control = ChoiceDropdown(root, textvariable=value, values=("First", "Second"))
    registered_commands = set(control._tclCommands or ())
    owned_idle = {
        token
        for token in root.tk.call("after", "info")
        if root.tk.splitlist(root.tk.call("after", "info", token))[0]
        in registered_commands
    }
    if kind == "search":
        assert owned_idle, "Exercise destruction before initial refresh"
    try:
        del value
        control.destroy()
        assert owned_idle.isdisjoint(root.tk.call("after", "info"))
        # Keep the dead widget alive deliberately. Its former variable/callback
        # must not depend on cyclic GC (which may run in a media/input worker).
        assert (reference() is not None) == keep_external_owner
        if kind == "placeholder":
            control._sync_placeholder()
            assert control._focus_placeholder(None) == "break"
            control.apply_theme()
        elif kind == "search":
            control._refresh()
            assert control._focus_entry(None) == "break"
            assert not control.set_compact(True)
            control.apply_theme()
        if external is not None:
            assert external.trace_info() == []
            external.set(True if kind == "checkbox" else "Second")
            assert external.get() == (True if kind == "checkbox" else "Second")
    finally:
        root.destroy()


@pytest.mark.parametrize("kind", ["collection", "file_action", "inline"])
def test_modal_dialog_returns_keyboard_focus_to_origin(kind):
    import tkinter as tk

    from yt_downloader.library_collection_ui import LibraryCollectionDialog
    from yt_downloader.library_file_actions_ui import FileActionDialog
    from yt_downloader.ui_styles import apply_product_styles
    from yt_downloader.ui_widgets import ActionDialogSurface

    root = tk.Tk()
    root.geometry("680x540+60+100")
    apply_product_styles(root)
    origin = tk.Entry(root)
    origin.pack()
    root.update()
    origin.focus_force()
    root.update()
    try:
        assert root.focus_get() is origin
        if kind == "collection":
            dialog = LibraryCollectionDialog(
                root, [("saved", "Saved video")], lambda *_: None
            )
            popup = dialog.popup
            target = dialog.name_entry
        elif kind == "file_action":
            dialog = FileActionDialog(root, "Move saved media", lambda: None)
            popup = dialog.popup
            target = dialog.secondary
        else:
            popup = tk.Frame(root)
            popup.place(x=30, y=50, width=500, height=350)
            surface = ActionDialogSurface(popup, modal=True)
            target = tk.Entry(surface.body)
            target.pack()
        root.update()
        target.focus_force()
        root.update()
        assert root.focus_get() is target and root.grab_current() is popup
        popup.destroy()
        root.update()
        assert root.grab_current() is None
        assert root.focus_get() is origin, (
            "Closing the dialog lost the user's keyboard location"
        )
    finally:
        root.destroy()


@pytest.mark.parametrize("dismissal", ["later", "external", "repair", "escape"])
def test_update_recovery_retires_callbacks_and_restores_origin(monkeypatch, dismissal):
    import tkinter as tk

    from yt_downloader import update_recovery as module
    from yt_downloader.ui_styles import apply_product_styles

    root = tk.Tk()
    root.geometry("700x600+60+100")
    apply_product_styles(root)
    origin = tk.Entry(root)
    origin.pack()
    root.update()
    origin.focus_force()
    root.update()
    commands, repaired, opened = {}, [], []
    button_type = module.ProductButton

    def button(*args, **kwargs):
        commands[kwargs["text"]] = kwargs.get("command")
        return button_type(*args, **kwargs)

    monkeypatch.setattr(module, "ProductButton", button)
    monkeypatch.setattr(tk.Misc, "wait_window", lambda *_: None)
    monkeypatch.setattr(module.webbrowser, "open", lambda *_: opened.append(True))
    before_binding = root.bind("<Configure>")
    try:
        module.show_update_recovery(
            root, "Synthetic update problem", lambda: repaired.append(True)
        )
        root.update()
        popup = root.children["update_recovery"]
        popup.focus_force()
        root.update()
        assert root.grab_current() is popup
        if dismissal == "external":
            popup.destroy()
        elif dismissal == "escape":
            popup.event_generate("<Escape>")
        else:
            commands["Repair VODForge" if dismissal == "repair" else "Later"]()
        root.update()
        assert root.grab_current() is None
        assert root.focus_get() is origin
        assert root.bind("<Configure>") == before_binding
        # Already queued callbacks from the retired popup must have no effect.
        commands["Repair VODForge"]()
        commands["Open download page"]()
        commands["Technical details"]()
        assert repaired == ([True] if dismissal == "repair" else [])
        assert opened == []
    finally:
        root.destroy()


@pytest.mark.parametrize("state", ["nested", "successor", "origin_destroyed"])
def test_modal_focus_restoration_respects_current_ownership(state):
    import tkinter as tk

    from yt_downloader.ui_widgets import ActionDialogSurface

    root = tk.Tk()
    root.geometry("680x540+60+100")
    parent = tk.Frame(root)
    parent.pack(fill="both", expand=True)
    origin = tk.Entry(parent)
    origin.pack()
    root.update()
    origin.focus_force()
    root.update()
    if state == "nested":
        parent.grab_set()
    popup = tk.Frame(parent)
    popup.place(x=20, y=40, width=480, height=320)
    surface = ActionDialogSurface(popup, modal=True)
    target = tk.Entry(surface.body)
    target.pack()
    root.update()
    target.focus_force()
    root.update()
    try:
        if state == "successor":
            successor = tk.Frame(parent)
            successor.place(x=25, y=45, width=480, height=320)
            successor.grab_set()
            new_focus = tk.Entry(successor)
            new_focus.pack()
            root.update()
            new_focus.focus_force()
            root.update()
        elif state == "origin_destroyed":
            origin.destroy()
        popup.destroy()
        root.update()
        if state == "successor":
            assert root.grab_current() is successor
            assert root.focus_get() is new_focus
        elif state == "nested":
            assert root.grab_current() is parent
            assert root.focus_get() is origin
        else:
            assert root.grab_current() is None
    finally:
        root.destroy()


@pytest.mark.parametrize("retired_part", ["field", "canvas"])
def test_field_chrome_releases_image_and_retires_late_requests(retired_part):
    import tkinter as tk
    import weakref

    from yt_downloader.ui_chrome import RoundedFieldBorder

    root = tk.Tk()
    root.geometry("500x180+60+100")
    first = tk.Frame(root, width=220, height=40)
    first.pack(pady=10)
    other = tk.Frame(root, width=220, height=40)
    other.pack(pady=10)
    chrome = RoundedFieldBorder(first)
    survivor = RoundedFieldBorder(other)
    try:
        root.update()
        assert chrome._image is not None and survivor._image is not None
        retired_image = weakref.ref(chrome._image)
        live_image = survivor._image
        (first if retired_part == "field" else chrome.canvas).destroy()
        assert retired_image() is None, "Destroyed field retained a Tk image"
        chrome.request(True, True)
        root.update()
        assert survivor._image is live_image
        assert survivor.canvas.winfo_exists()
    finally:
        root.destroy()


def test_product_chrome_releases_images_only_when_its_root_is_destroyed():
    import tkinter as tk
    import weakref
    from tkinter import ttk

    from yt_downloader.ui_styles import apply_product_styles

    root = tk.Tk()
    root.withdraw()
    apply_product_styles(root)
    owner = root._product_chrome_owner
    style = ttk.Style(root)
    references = [weakref.ref(image) for image in owner.images.values()]
    assert references
    child = tk.Toplevel(root)
    child.withdraw()
    child.destroy()
    assert all(reference() is not None for reference in references)
    try:
        root.destroy()
        assert all(reference() is None for reference in references)
        owner.request(style)
        assert not owner.images
    finally:
        if root.tk.call("info", "commands", "."):
            root.destroy()
