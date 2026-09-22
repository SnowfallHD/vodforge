"""Bounded real-control geometry and lifetime checks for the DPI slice."""

import gc
import os
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk

import pytest

from yt_downloader.ui_layout import install_window_logical_metrics
from yt_downloader.ui_styles import apply_product_styles
from yt_downloader.ui_theme import FONT_UI, THEME
from yt_downloader.ui_widgets import ChoiceDropdown, PillAction, ProductEntry

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="explicit native run required",
)


def pump(root):
    until = time.monotonic() + 0.12
    while time.monotonic() < until:
        root.update()
        time.sleep(0.005)


@pytest.mark.parametrize("dpi", [None, 192])
@pytest.mark.parametrize("check", ["width", "ellipsis"])
def test_choice_menu_measures_the_font_it_draws(dpi, check, tmp_path):
    import json

    from tests.test_matte_native import save_native_capture
    from yt_downloader.ui_widgets import ChoiceMenu

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        root.geometry("900x320+40+40")
        values = ("Minimum widths WWW iii 0123456789", "Editing — café 東京 " * 4)
        menu = ChoiceMenu(root, values)
        menu.pack(anchor="nw", padx=20, pady=20)
        pump(root)
        scale = 2 if dpi else 1

        def measure(text):
            return int(root.tk.call("font", "measure", menu._font, text))

        expected_width = max(map(measure, values)) + 52 * scale
        requested_width = menu.winfo_reqwidth()
        if check == "ellipsis":
            menu.configure(width=240 * scale)
            pump(root)
        items = [item for item in menu.find_all() if menu.type(item) == "text"]
        drawn = [menu.itemcget(item, "text") for item in items]
        available = menu.winfo_width() - 36 * scale
        expected = [
            value
            if measure(value) <= available
            else max(
                (
                    value[:n] + "…"
                    for n in range(len(value) + 1)
                    if measure(value[:n] + "…") <= available
                ),
                key=len,
            )
            for value in values
        ]
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        name = f"choice-font-{dpi or 'default'}-{check}"
        save_native_capture(menu, out / f"{name}.png")
        (out / f"{name}.json").write_text(
            json.dumps(
                {
                    "font": menu._font,
                    "requested_width": requested_width,
                    "expected_width": expected_width,
                    "available": available,
                    "drawn": drawn,
                    "expected": expected,
                    "scope": "Mac source native; injected DPI is not physical Windows DPI",
                },
                indent=2,
            )
        )
        if check == "width":
            assert requested_width == expected_width
        else:
            assert drawn == expected
        menu._move(1)
        assert menu.get(menu.curselection()[0]) == values[1]
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_context_action_measurement_matches_drawn_font(dpi, tmp_path):
    import json

    from tests.test_matte_native import save_native_capture

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        root.geometry("760x180+40+40")
        text = "Minimum widths WWW iii 0123456789 — café 東京"
        value = tk.StringVar(root, text)
        action = PillAction(root, textvariable=value, command=lambda: None, width=280)
        action.pack(anchor="nw", padx=20, pady=20)
        pump(root)
        font = action.itemcget(action._text_item, "font")
        exact = int(root.tk.call("font", "measure", font, text))
        measured = action._text_font.measure(text)
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        name = f"action-font-{dpi or 'default'}"
        save_native_capture(action, out / f"{name}.png")
        (out / f"{name}.json").write_text(
            json.dumps(
                {
                    "drawn_font": font,
                    "exact": exact,
                    "measured": measured,
                    "drawn_text": action.itemcget(action._text_item, "text"),
                },
                indent=2,
            )
        )
        assert measured == exact
        assert value.get() == text
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_search_field_scales_labels_icon_padding_and_preserves_editing(dpi, tmp_path):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.library_search_ui import LibrarySearchField

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        root.geometry("900x220+40+40")
        value = tk.StringVar(root, "")
        search = LibrarySearchField(root, variable=value, shortcut_hint="⌘K")
        search.pack(anchor="nw", padx=20, pady=20)
        pump(root)
        scale = 2 if dpi else 1
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(search, out / f"search-{dpi or 'default'}-idle.png")
        expected_font = -29 if dpi else FONT_UI[1]
        labels = [
            child for child in search.winfo_children() if isinstance(child, tk.Label)
        ]
        for widget in (search.entry, *labels):
            assert int(root.tk.splitlist(widget.cget("font"))[1]) == expected_font
        assert search._search_icon.width() == 16 * scale
        assert int(search.entry.pack_info()["pady"]) == 8 * scale
        root.focus_force()
        search.entry.focus_set()
        search.entry.insert(0, "café 東京 query")
        search.entry.selection_range(0, 4)
        search.entry.icursor(4)
        pump(root)
        assert not search._placeholder.winfo_ismapped()
        before = value.get()
        search.set_compact(True)
        search.apply_theme()
        pump(root)
        assert value.get() == before
        assert search.entry.index("sel.first") == 0
        assert search.entry.index("sel.last") == 4
        assert search.entry.index("insert") == 4
        assert search._search_icon.width() == 16 * scale
        save_native_capture(
            search, out / f"search-{dpi or 'default'}-focused-compact.png"
        )
        assert all(child.cget("bg") == search.entry.cget("bg") for child in labels)
        search.entry.delete(0, "end")
        root.focus_set()
        pump(root)
        assert search._placeholder.winfo_ismapped()
        search.destroy()
        value.set("safe after retirement")
        pump(root)
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_placeholder_entry_shares_font_inset_and_focus_material(dpi, tmp_path):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.ui_widgets import PlaceholderEntry

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        root.geometry("780x200+40+40")
        apply_product_styles(root)
        value = tk.StringVar(root, "")
        field = PlaceholderEntry(
            root, textvariable=value, placeholder="Name this collection"
        )
        field.pack(anchor="nw", padx=20, pady=20)
        root.focus_force()
        field.focus_set()
        pump(root)
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(field, out / f"placeholder-{dpi or 'default'}-focused.png")
        assert field._placeholder.winfo_ismapped()
        assert str(field._placeholder.cget("font")) == str(field.cget("font"))
        assert field._placeholder.winfo_x() == (36 if dpi else 18)
        assert field._placeholder.cget("bg") == THEME["focus_surface"]
        assert value.get() == ""
        field.insert(0, "café 東京")
        field.selection_range(0, 4)
        field.icursor(4)
        field.apply_theme()
        pump(root)
        assert not field._placeholder.winfo_ismapped()
        assert value.get() == "café 東京"
        assert (
            field.index("sel.first"),
            field.index("sel.last"),
            field.index("insert"),
        ) == (0, 4, 4)
        field.delete(0, "end")
        root.focus_set()
        pump(root)
        assert field._placeholder.winfo_ismapped()
        assert field._placeholder.cget("bg") == THEME["surface"]
        save_native_capture(field, out / f"placeholder-{dpi or 'default'}-restored.png")
        field.destroy()
        value.set("safe after retirement")
        pump(root)
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_editable_section_scales_and_keeps_failed_edits(dpi, tmp_path):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.ui_editable_text import EditableTextSection

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        apply_product_styles(root)
        root.geometry("1000x780+40+40")
        saved = []
        accept = [False]

        def save(owner, value):
            saved.append((owner, value))
            return accept[0]

        section = EditableTextSection(
            root, title="Notes", save=save, changed=lambda: None
        )
        section.pack(fill="both", expand=True, padx=20, pady=20)
        original = "Original text\nSecond line"
        section.present("owner", original, "Saved with this video")
        pump(root)
        scale = 2 if dpi else 1
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(section, out / f"editor-{dpi or 'default'}-readonly.png")
        actual = root.tk.call("font", "actual", section.text.cget("font"), "-size")
        # Compare to an independently specified pixel font; actual may use points.
        expected = root.tk.call("font", "actual", (FONT_UI[0], -15 * scale), "-size")
        assert actual == expected
        assert section._font.cget("size") == -15 * scale
        assert int(section.text.cget("padx")) == 10 * scale
        assert int(section.text.cget("pady")) == 8 * scale
        assert section._copy_icon.width() == 16 * scale
        assert section.height_for_width(700) > section.header.winfo_reqheight()
        root.focus_force()
        section.begin()
        section.text.insert("end", "\ncafé 東京 edit")
        pump(root)
        edited = section.text.get("1.0", "end-1c")
        section.commit()
        assert section._editing and section.text.get("1.0", "end-1c") == edited
        assert saved == [("owner", edited)]
        assert "Could not save" in section.caption.cget("text")
        pump(root)
        save_native_capture(section, out / f"editor-{dpi or 'default'}-failed-save.png")
        accept[0] = True
        section.commit()
        assert not section._editing and section.text.cget("state") == "disabled"
        assert saved == [("owner", edited), ("owner", edited)]
        section.begin()
        section.text.insert("end", "discard")
        section.cancel()
        assert section.text.get("1.0", "end-1c") == edited
        assert section._keys is None
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_dialog_shell_uses_its_own_admitted_window_metrics(dpi, tmp_path):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.ui_button_contract import ProductButton
    from yt_downloader.ui_layout import window_logical_metrics
    from yt_downloader.ui_widgets import ActionDialogSurface

    root = tk.Tk()
    try:
        install_window_logical_metrics(root, dpi=192)
        apply_product_styles(root)
        root.geometry("500x260+40+40")
        popup = tk.Toplevel(root)
        if dpi:
            install_window_logical_metrics(popup, dpi=dpi)
        popup.geometry("900x650+80+80")
        surface = ActionDialogSurface(
            popup, protect_status=True, allow_body_scroll=True
        )
        scale = 2 if dpi else 1
        assert window_logical_metrics(surface.body).scale == scale
        assert window_logical_metrics(root).scale == 2
        tk.Label(
            surface.body,
            text="Dialog body",
            font=window_logical_metrics(popup).font(FONT_UI),
        ).pack()
        status = tk.Label(
            surface.status,
            text="Changes are not saved yet",
            font=window_logical_metrics(popup).font(FONT_UI),
        )
        status.pack()
        calls = []
        save = ProductButton(
            surface.footer, text="Save", command=lambda: calls.append("save")
        )
        save.pack(side="right")
        pump(root)
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(popup, out / f"dialog-{dpi or 'default'}.png")
        assert surface.shell.winfo_x() == 24 * scale
        assert surface.shell.winfo_y() == 22 * scale
        assert tuple(
            map(int, popup.tk.splitlist(surface.footer.grid_info()["pady"]))
        ) == (18 * scale, 0)
        assert surface.protected_content_is_visible(status)
        assert surface.action_is_visible(save)
        save.invoke()
        assert calls == ["save"]
        popup.destroy()
        pump(root)
        assert window_logical_metrics(root).scale == 2
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_chapter_list_scales_rows_columns_and_keeps_selection(dpi, tmp_path):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.media_player_ui import ChapterList

    root = tk.Tk()
    try:
        apply_product_styles(root)
        ordinary = ChapterList(root, [{"title": "Ordinary sibling", "start_time": 0}])
        ordinary.pack()
        popup = tk.Toplevel(root)
        if dpi:
            install_window_logical_metrics(popup, dpi=dpi)
        popup.geometry("800x600+40+40")
        rows = [
            {"title": f"Chapter {n} — café 東京", "start_time": n * 12}
            for n in range(20)
        ]
        chapters = ChapterList(popup, rows)
        chapters.pack(fill="both", expand=True, padx=20, pady=20)
        pump(root)
        scale = 2 if dpi else 1
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(chapters, out / f"chapters-{dpi or 'default'}-resting.png")
        assert chapters.bbox("0")[3] == 38 * scale
        font = ttk.Style(root).lookup(chapters.cget("style"), "font")
        assert int(root.tk.splitlist(font)[1]) == (-27 if dpi else 10)
        assert ordinary.bbox("0")[3] == 38
        assert int(chapters.column("time", "width")) == 50 * scale
        assert int(chapters.column("title", "minwidth")) == 80 * scale
        original = [chapters.item(str(n), "values") for n in range(20)]
        popup.focus_force()
        chapters.focus_set()
        chapters.selection_set("0")
        chapters.focus("0")
        pump(root)
        chapters.event_generate("<Down>")
        pump(root)
        assert chapters.curselection() == (1,)
        chapters.see("19")
        pump(root)
        assert chapters.bbox("19")
        save_native_capture(chapters, out / f"chapters-{dpi or 'default'}-scrolled.png")
        assert [chapters.item(str(n), "values") for n in range(20)] == original
        apply_product_styles(root)
        pump(root)
        assert chapters.bbox("19")[3] == 38 * scale
        assert chapters.curselection() == (1,)
        popup.destroy()
        pump(root)
        assert ordinary.bbox("0")[3] == 38
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_volume_units_preserve_exact_pointer_values_and_transport_icons(dpi, tmp_path):
    from types import SimpleNamespace

    from tests.test_matte_native import save_native_capture
    from yt_downloader.media_player_ui import PlayerTransportButton, PlayerVolumeControl

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        apply_product_styles(root)
        root.geometry("520x260+40+40")
        value = tk.IntVar(root, 25)
        calls = []
        volume = PlayerVolumeControl(root, variable=value, command=calls.append)
        volume.pack(pady=20)
        transport = PlayerTransportButton(root, command=lambda: None)
        transport.pack()
        pump(root)
        scale = 2 if dpi else 1
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(volume, out / f"volume-{dpi or 'default'}-resting.png")
        assert (volume.winfo_width(), volume.winfo_height()) == (92 * scale, 22 * scale)
        assert transport._icons["Play"].width() == 18 * scale
        root.focus_force()
        for x, expected in ((8 * scale, 0), (46 * scale, 50), (84 * scale, 100)):
            volume._set_from_pointer(SimpleNamespace(x=x))
            pump(root)
            assert value.get() == expected
        assert calls == ["0", "50", "100"]
        thumb = [item for item in volume.find_all() if volume.type(item) == "oval"]
        assert len(thumb) == 1
        x1, y1, x2, y2 = volume.coords(thumb[0])
        assert (x2 - x1, y2 - y1) == (12 * scale, 12 * scale)
        tracks = [item for item in volume.find_all() if volume.type(item) == "line"]
        assert float(volume.itemcget(tracks[0], "width")) == 6 * scale
        assert volume.coords(tracks[0]) == [
            8 * scale,
            12 * scale,
            84 * scale,
            12 * scale,
        ]
        volume._step(-5)
        assert value.get() == 95 and calls[-1] == "95"
        volume.apply_theme()
        transport.configure(text="Pause")
        transport.apply_theme()
        pump(root)
        assert transport._icons["Pause"].width() == 18 * scale
        assert volume._focus_image.width() == 92 * scale
        assert volume._focus_image.height() == 22 * scale
        save_native_capture(volume, out / f"volume-{dpi or 'default'}-focused.png")
        save_native_capture(transport, out / f"transport-{dpi or 'default'}-pause.png")
        volume.destroy()
        value.set(12)
        assert calls == ["0", "50", "100", "95"]
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_progress_scales_track_but_preserves_fraction_and_timer_retirement(
    dpi, tmp_path
):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.ui_widgets import SleekProgressbar

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        root.geometry("500x180+40+40")
        value = tk.DoubleVar(root, 25)
        progress = SleekProgressbar(root, variable=value, maximum=100)
        progress.place(x=20, y=40, width=400)
        pump(root)
        scale = 2 if dpi else 1
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(progress, out / f"progress-{dpi or 'default'}-quarter.png")
        assert progress.winfo_height() == 5 * scale
        rectangles = [
            item for item in progress.find_all() if progress.type(item) == "rectangle"
        ]
        x1, y1, x2, y2 = progress.coords(rectangles[-1])
        assert (x1, x2) == (0, 100)  # Actual400px width, never converted again.
        assert y2 - y1 == 3 * scale
        value.set(75)
        progress.apply_theme()
        pump(root)
        rectangles = [
            item for item in progress.find_all() if progress.type(item) == "rectangle"
        ]
        assert progress.coords(rectangles[-1])[2] == 300
        progress.start(50)
        token = progress._after_id
        assert token in root.tk.call("after", "info")
        progress.destroy()
        assert token not in root.tk.call("after", "info")
        assert value.trace_info() == []
        value.set(12)
        pump(root)
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
@pytest.mark.parametrize("kind", ["locations", "folders"])
def test_active_archive_list_rows_scale_at_actual_constructor(dpi, kind, tmp_path):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.archive_browser_ui import ArchiveBrowser
    from yt_downloader.archive_library_ui import ArchiveLibraryMixin
    from yt_downloader.ui_widgets import _tinted_ui_icon

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        apply_product_styles(root)
        root.geometry("1100x800+40+30")
        if kind == "locations":
            browser = ArchiveBrowser(
                root,
                on_select=lambda: None,
                on_activate=lambda *_: None,
                on_menu=lambda *_: None,
                on_folder=lambda *_: None,
                on_relink=lambda *_: None,
            )
            browser.pack(fill="both", expand=True)
            tree = browser.location_list
        else:
            root._archive_copy_path = lambda: None
            root._archive_location_menu = lambda: None
            root._archive_parent_tooltip = lambda: "Folder path"
            root._load_focus_icon = lambda name, size, color: _tinted_ui_icon(
                name, size=(size, size), color=color, widget=root
            )
            frame = ttk.Frame(root)
            frame.pack(fill="both", expand=True)
            ArchiveLibraryMixin._build_archive_location_panel(root, frame)
            tree = root._archive_ancestors
        for n in range(8):
            tree.insert("", "end", iid=str(n), text=f"Folder {n} — café 東京")
        pump(root)
        scale = 2 if dpi else 1
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(tree, out / f"{kind}-{dpi or 'default'}.png")
        assert tree.bbox("0")[3] == (52 if kind == "locations" else 34) * scale
        if kind == "locations":
            assert browser.navigation.winfo_width() == 184 * scale
            assert tree.winfo_width() >= 140 * scale
        assert (
            int(tree.column("#0", "minwidth"))
            == (100 if kind == "locations" else 120) * scale
        )
        font = ttk.Style(root).lookup(tree.cget("style"), "font")
        assert int(root.tk.splitlist(font)[1]) == (-27 if dpi else 10)
        tree.selection_set("0")
        tree.focus("0")
        root.focus_force()
        tree.focus_set()
        pump(root)
        tree.event_generate("<Down>")
        pump(root)
        assert tree.selection() == ("1",)
        tree.see("7")
        pump(root)
        assert tree.bbox("7")
        assert tree.item("7", "text") == "Folder 7 — café 東京"
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_player_transport_timeline_geometry_and_seek_mapping(dpi, tmp_path):
    from functools import partial
    from types import SimpleNamespace

    from tests.test_matte_native import save_native_capture
    from yt_downloader.media_player_ui import MediaPlayerWindow

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        apply_product_styles(root)
        root.geometry("1180x260+40+40")
        root.columnconfigure(0, weight=1)
        seeks = []
        state = SimpleNamespace(
            embedded=True,
            playback=SimpleNamespace(
                snapshot=SimpleNamespace(duration=100, position=0, volume=50)
            ),
            _chapters=[
                {"start_time": 0, "end_time": 50},
                {"start_time": 100, "end_time": 100},
            ],
            _heatmap=[{"start_time": 0, "end_time": 100, "value": 1.0}],
            _timeline_signature=None,
            _timeline_progress=None,
            _timeline_handle=None,
            _toggle=lambda: None,
            _schedule_volume=lambda *_: None,
            _media_intent_current=lambda: True,
            _seek_to=seeks.append,
            _on_feature=lambda *_: None,
        )
        state._draw_timeline_base = partial(
            MediaPlayerWindow._draw_timeline_base, state
        )
        state._timeline_clicked = partial(MediaPlayerWindow._timeline_clicked, state)
        MediaPlayerWindow._build_transport(state, root)
        pump(root)
        scale = 2 if dpi else 1
        assert state.timeline.winfo_height() == 28 * scale
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        for position in (0, 50, 100):
            MediaPlayerWindow._update_timeline_value(
                state, SimpleNamespace(duration=100, position=position)
            )
            pump(root)
            bounds = state.timeline.bbox("all")
            assert 0 <= bounds[0] < bounds[2] <= state.timeline.winfo_width()
            assert 0 <= bounds[1] < bounds[3] <= state.timeline.winfo_height()
            coords = state.timeline.coords(state._timeline_handle)
            assert (coords[2] - coords[0], coords[3] - coords[1]) == (
                8 * scale,
                12 * scale,
            )
        width = state.timeline.winfo_width()
        for x in (10 * scale, width / 2, width - 10 * scale):
            state._timeline_clicked(SimpleNamespace(x=x, y=0))
        assert seeks == [0, 50, 100]
        for child in (
            state.play_button,
            state.time_label,
            state.status_label,
            state.volume_label,
            state.volume_control,
        ):
            assert (
                child.winfo_rootx() + child.winfo_width()
                <= root.winfo_rootx() + root.winfo_width()
            )
        save_native_capture(
            state.transport, out / f"transport-timeline-{dpi or 'default'}.png"
        )
    finally:
        root.destroy()


def build_fixture(root, *, dpi=None):
    metrics = install_window_logical_metrics(root, dpi=dpi) if dpi else None
    px = metrics.px if metrics else lambda n: n
    root.geometry(f"{px(680)}x{px(420)}+40+40")
    root.configure(bg=THEME["bg"])
    apply_product_styles(root)
    values = tk.StringVar(
        root, "A long editable destination with natural selection behavior"
    )
    selected = tk.StringVar(root, "Everyday")
    calls = []
    field = ProductEntry(root, textvariable=values)
    field.place(x=px(20), y=px(40), width=px(400), height=px(34))
    choice = ChoiceDropdown(
        root, textvariable=selected, values=("Everyday", "Editing", "Archival")
    )
    choice.place(x=px(20), y=px(100), width=px(300))
    action = PillAction(
        root,
        textvariable=tk.StringVar(root, "Choose destination"),
        command=lambda: calls.append("action"),
        width=300,
    )
    action.place(x=px(20), y=px(170))
    other = ttk.Button(root, text="Other focus")
    other.place(x=px(440), y=px(40))
    pump(root)
    return {
        "field": field,
        "choice": choice,
        "action": action,
        "other": other,
        "values": values,
        "selected": selected,
        "calls": calls,
        "metrics": metrics,
    }


@pytest.mark.parametrize("dpi", [None, 96, 192])
def test_shared_control_geometry_font_and_popup_lifetime(dpi):
    root = tk.Tk()
    try:
        f = build_fixture(root, dpi=dpi)
        scale = dpi // 96 if dpi else 1
        field, choice, action = (f[n] for n in ("field", "choice", "action"))
        assert action.winfo_height() == 34 * scale
        assert field.winfo_height() == 34 * scale
        actual_font = tkfont.Font(root=root, font=field.cget("font"))
        assert actual_font.metrics("linespace") < field.winfo_height()
        assert actual_font.measure("Editing") < choice.winfo_width() - 36 * scale
        field.selection_range(2, 12)
        assert field.selection_present() and field.index("sel.first") == 2
        assert field.index("sel.last") == 12
        field.icursor("end")
        field.insert("end", "!")
        assert f["values"].get().endswith("!")
        field.delete(field.index("end") - 1, "end")
        original_images = set(root.tk.call("image", "names"))
        original_commands = set(root.tk.call("info", "commands"))
        for _ in range(3):
            choice.open_popover()
            pump(root)
            menu = choice._popover.winfo_children()[0]
            assert menu.row_height == 34 * scale
            assert menu.index_at(20 * scale, 6 * scale + 51 * scale) == 1
            assert menu.index_at(20 * scale, 5 * scale) is None
            assert menu.winfo_rooty() >= root.winfo_rooty()
            assert (
                menu.winfo_rooty() + menu.winfo_height()
                <= root.winfo_rooty() + root.winfo_height()
            )
            choice._close_popover()
            del menu
            gc.collect()
            pump(root)
        assert set(root.tk.call("image", "names")) == original_images
        assert set(root.tk.call("info", "commands")) == original_commands
        choice.state(["disabled"])
        choice.open_popover()
        assert choice._popover is None
        choice.state(["!disabled"])
        # No opt-in writes Tk's interpreter-global point scaling or font roles.
        assert FONT_UI[1] > 0
    finally:
        root.destroy()


def test_density_entry_styles_survive_toplevel_retirement_without_growth():
    root = tk.Tk()
    root.withdraw()
    apply_product_styles(root)
    baseline = ttk.Style(root).layout("Product.TEntry")
    try:
        handles = {}
        warm_images = None
        for cycle in range(3):
            for dpi in (96, 192):
                top = tk.Toplevel(root)
                install_window_logical_metrics(top, dpi=dpi)
                before_images = set(root.tk.call("image", "names"))
                field = ProductEntry(top)
                field.pack()
                pump(root)
                scale = dpi // 96
                added = set(root.tk.call("image", "names")) - before_images
                if scale in handles:
                    assert not added
                    current = handles[scale]
                else:
                    assert len(added) == 2
                    current = tuple(sorted(added))
                    handles[scale] = current
                assert all(
                    root.tk.call("image", "width", name) == 28 * scale
                    for name in current
                )
                field.insert(0, "Still editable")
                assert field.get() == "Still editable"
                top.destroy()
                del field, top
                gc.collect()
                assert all(name in root.tk.call("image", "names") for name in current)
            current_images = set(root.tk.call("image", "names"))
            if warm_images is not None:
                assert current_images == warm_images
            warm_images = current_images
        assert ttk.Style(root).layout("Product.TEntry") == baseline
    finally:
        root.destroy()


def test_product_entry_uses_default_or_owned_density_style_but_never_the_wrong_one():
    """Exercise the default and opt-in paths with real ttk style ownership."""
    root = tk.Tk()
    root.withdraw()
    apply_product_styles(root)
    try:
        default = ProductEntry(root)
        assert default.cget("style") == "Product.TEntry"

        top = tk.Toplevel(root)
        install_window_logical_metrics(top, dpi=192)
        density_entry = ProductEntry(top)
        density_style = density_entry.cget("style")
        assert density_style == "Dpi2.Product.TEntry"
        assert density_style != default.cget("style")

        style = ttk.Style(root)
        # A fallback to the default Product style would omit the owned, 2x
        # field element. This makes that wrong-style regression observable.
        assert style.layout(density_style)[0][0] == "Dpi2.Product.field"
        assert style.layout(default.cget("style"))[0][0] == "Product.field"
        top.destroy()
    finally:
        root.destroy()


def test_native_product_button_uses_window_metrics_without_changing_siblings(
    monkeypatch, tmp_path
):
    from yt_downloader import ui_chrome
    from yt_downloader.ui_button_contract import ProductButton
    from yt_downloader.ui_theme import apply_theme_selection

    root = tk.Tk()
    original_theme = dict(THEME)
    from yt_downloader import ui_theme

    original_name = ui_theme._active_theme_name
    try:
        apply_product_styles(root)
        root.geometry("400x220+30+30")
        ordinary = ProductButton(root, text="Ordinary")
        ordinary.pack()
        popup = tk.Toplevel(root)
        install_window_logical_metrics(popup, dpi=192)
        calls = []
        button = ProductButton(
            popup, text="Scaled action", command=lambda: calls.append("once")
        )
        button.pack()
        pump(root)
        assert ordinary.winfo_height() == 44
        style = ttk.Style(root)
        assert button.winfo_height() == 88
        font_spec = style.lookup(button.cget("style"), "font")
        assert int(root.tk.splitlist(font_spec)[1]) == -30
        assert (
            int(root.tk.call("font", "measure", font_spec, "Scaled action"))
            < button.winfo_width()
        )
        button.invoke()
        assert calls == ["once"]
        button.state(["disabled"])
        button.invoke()
        assert calls == ["once"]
        button.state(["!disabled"])
        # Prior behavior: leaving the same opted-in button on the base style
        # creates the wrong native height, without changing its callback/model.
        with monkeypatch.context() as wrong:
            wrong.setattr(
                ui_chrome, "prototype_button_style", lambda widget, name: name
            )
            broken = ProductButton(popup, text="Wrong units")
        broken.pack()
        pump(root)
        assert broken.winfo_height() == 44 and broken.winfo_height() != 88
        broken.destroy()
        handles = set(root.tk.call("image", "names"))
        popup.destroy()
        second = tk.Toplevel(root)
        install_window_logical_metrics(second, dpi=192)
        retained = ProductButton(second, text="Retained owner")
        retained.pack()
        pump(root)
        assert retained.winfo_height() == 88
        assert set(root.tk.call("image", "names")) == handles
        from PIL import ImageChops

        from tests.test_matte_native import save_native_capture

        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        out.mkdir(parents=True, exist_ok=True)
        before = save_native_capture(
            retained, out / "button-before-native.png"
        ).convert("RGB")
        retained.state(["focus"])
        pump(root)
        focused = save_native_capture(
            retained, out / "button-focus-native.png"
        ).convert("RGB")
        assert ImageChops.difference(before, focused).getbbox() is not None
        retained.state(["!focus"])
        pump(root)
        # Exercise an effective palette change through the normal image owner.
        apply_theme_selection("Cobalt" if original_name != "Cobalt" else "Violet")
        apply_product_styles(root)
        pump(root)
        changed = save_native_capture(
            retained, out / "button-theme-native.png"
        ).convert("RGB")
        assert ImageChops.difference(before, changed).getbbox() is not None
        assert retained.winfo_height() == 88 and ordinary.winfo_height() == 44
        assert set(root.tk.call("image", "names")) == handles
        THEME.clear()
        THEME.update(original_theme)
        ui_theme._active_theme_name = original_name
        apply_product_styles(root)
        pump(root)
        restored = save_native_capture(
            retained, out / "button-restored-native.png"
        ).convert("RGB")
        assert ImageChops.difference(before, restored).getbbox() is None
        assert set(root.tk.call("image", "names")) == handles
        second.destroy()
    finally:
        THEME.clear()
        THEME.update(original_theme)
        ui_theme._active_theme_name = original_name
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_checkbox_geometry_label_glyph_and_input_share_window_units(dpi, tmp_path):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.ui_widgets import ModernCheckbox

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        root.geometry("700x240+40+40")
        value = tk.BooleanVar(root, False)
        calls = []
        control = ModernCheckbox(
            root,
            text="Keep metadata",
            variable=value,
            command=lambda: calls.append(value.get()),
        )
        control.pack(padx=20, pady=20)
        pump(root)
        scale = dpi // 96 if dpi else 1
        assert control._box.winfo_width() == 18 * scale
        assert control._box_surface.width() == 16 * scale
        text_font = control._label.cget("font")
        assert (
            int(root.tk.call("font", "metrics", text_font, "-linespace"))
            <= control.winfo_height()
        )
        box = control._box
        box.event_generate("<ButtonPress-1>", x=9 * scale, y=9 * scale)
        assert value.get() is False
        box.event_generate("<ButtonRelease-1>", x=9 * scale, y=9 * scale)
        pump(root)
        assert value.get() is True and calls == [True]
        assert control._check_image.width() == 12 * scale
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        out.mkdir(parents=True, exist_ok=True)
        save_native_capture(control, out / f"checkbox-{scale}x-native.png")
        control.state(["disabled"])
        box.event_generate("<ButtonPress-1>", x=9 * scale, y=9 * scale)
        box.event_generate("<ButtonRelease-1>", x=9 * scale, y=9 * scale)
        pump(root)
        assert value.get() is True and calls == [True]
    finally:
        root.destroy()


def test_segmented_labels_use_physical_font_and_padding_without_changing_selection(
    tmp_path,
):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.ui_widgets import SegmentedSelector

    root = tk.Tk()
    try:
        install_window_logical_metrics(root, dpi=192)
        root.geometry("720x220+40+40")
        selected = tk.StringVar(root, "MP4")
        changes = []
        selected.trace_add("write", lambda *_args: changes.append(selected.get()))
        selector = SegmentedSelector(
            root,
            variable=selected,
            values=("MP4", "MP3", "Original"),
            separated=True,
            background=THEME["bg"],
        )
        selector.pack(padx=20, pady=20)
        pump(root)
        target = selector._labels["Original"]
        font = target.cget("font")
        assert int(root.tk.splitlist(font)[1]) == -27  # canonical10pt at192DPI
        measured_width = int(root.tk.call("font", "measure", font, "Original"))
        measured_height = int(root.tk.call("font", "metrics", font, "-linespace"))
        assert target.winfo_width() == measured_width + 44  # 11px on each side, twice
        assert target.winfo_height() == measured_height + 24
        target.event_generate("<ButtonPress-1>", x=10, y=10)
        pump(root)
        assert selected.get() == "MP4" and not changes
        target.event_generate("<ButtonRelease-1>", x=10, y=10)
        pump(root)
        assert selected.get() == "Original" and changes == ["Original"]
        before = (target.winfo_width(), target.winfo_height())
        selector._set_hover("Original", True)
        pump(root)
        assert (target.winfo_width(), target.winfo_height()) == before
        assert changes == ["Original"]
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        out.mkdir(parents=True, exist_ok=True)
        save_native_capture(selector, out / "segments-2x-native.png")
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_tooltip_label_metrics_preserve_measured_anchor_and_owner_retirement(
    dpi, monkeypatch, tmp_path
):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.ui_widgets import ToolTip

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        root.geometry("700x240+40+40")
        anchor = tk.Label(root, text="Tooltip anchor")
        anchor.pack(padx=40, pady=40)
        pump(root)
        tooltip = ToolTip(
            anchor, "A longer explanation of the selected media option. " * 4
        )
        # Controlled pointer ownership admits only this fixture tooltip; no
        # physical pointer or platform activation claim follows from this test.
        monkeypatch.setattr(tooltip, "contains_pointer", lambda: True)
        controller = tooltip.controller
        controller.pending = tooltip
        controller._show_if_owned(tooltip)
        pump(root)
        tip = controller.tip
        assert tip is not None and tip.winfo_ismapped()
        label = tip.winfo_children()[0]
        scale = dpi // 96 if dpi else 1
        assert int(label.cget("wraplength")) == 320 * scale
        if dpi:
            assert int(root.tk.splitlist(label.cget("font"))[1]) == -27
        assert tip.winfo_y() == anchor.winfo_rooty() + anchor.winfo_height() + 8 * scale
        assert label.winfo_width() == label.winfo_reqwidth()
        assert label.winfo_height() == label.winfo_reqheight()
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        out.mkdir(parents=True, exist_ok=True)
        save_native_capture(tip, out / f"tooltip-{scale}x-native.png")
        root.withdraw()
        pump(root)
        assert controller.tip is None and controller.pointer_poll_after_id is None
        monkeypatch.setattr(tooltip, "contains_pointer", lambda: False)
        controller.pending = tooltip
        controller._show_if_owned(tooltip)
        assert controller.tip is None and controller.pending is None
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_facts_document_scales_canonical_spacing_and_preserves_content(dpi, tmp_path):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.detail_ui import FactsText

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        scale = dpi // 96 if dpi else 1
        root.geometry(f"{600 * scale}x{300 * scale}+40+40")
        doc = FactsText(root)
        doc.pack(fill="both", expand=True)
        source = "Codec: H.264\nAudio: AAC\nLong path: /example/" + "long folder/" * 12
        doc.request(source)
        pump(root)
        assert int(doc.cget("pady")) == 4 * scale
        assert int(doc.cget("spacing1")) == 2 * scale
        assert int(doc.tag_cget("block-label", "spacing1")) == 10 * scale
        if dpi:
            assert int(root.tk.splitlist(doc.cget("font"))[1]) == -27
        measure = lambda value: int(
            root.tk.call("font", "measure", doc.cget("font"), value)
        )
        expected_stop = max(
            measure(label) + 18 * scale for label in ("Codec", "Audio", "Long path")
        )
        assert int(root.tk.splitlist(doc.cget("tabs"))[0]) == expected_stop
        doc.tag_add("sel", "1.0", "1.5")
        selected = doc.get("sel.first", "sel.last")
        for width in (350 * scale, 600 * scale):
            root.geometry(f"{width}x{300 * scale}")
            pump(root)
            assert doc.raw_snapshot == source
            assert doc.get("sel.first", "sel.last") == selected
            for value in ("H.264", "AAC", "/example/" + "long folder/" * 12):
                assert value in doc.get("1.0", "end-1c")
        assert doc.request(source) is False
        assert str(doc.cget("state")) == "disabled"
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        out.mkdir(parents=True, exist_ok=True)
        save_native_capture(doc, out / f"facts-{scale}x-native.png")
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_log_document_metrics_preserve_tokens_and_embedded_label_density(dpi, tmp_path):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.activity_ui import ActivityLogText

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        scale = dpi // 96 if dpi else 1
        root.geometry(f"{600 * scale}x{220 * scale}+40+40")
        doc = ActivityLogText(root, wrap="word", bg=THEME["bg"], fg=THEME["text"])
        doc.pack(fill="both", expand=True)
        source = "[info] Ready\nWARNING: Keep the original warning\n[success] Finished"
        doc.request(source)
        pump(root)
        assert int(doc.cget("spacing1")) == 8 * scale
        assert doc._icon_size == (16 * scale, 16 * scale)
        assert doc._divider.width() == scale
        assert doc._divider.height() == 18 * scale
        for constrained in (True, False):
            doc.request_density(constrained=constrained)
            pump(root)
            assert int(doc.cget("pady")) == (0 if constrained else 4 * scale)
            if dpi:
                assert int(root.tk.splitlist(doc.cget("font"))[1]) == (
                    -24 if constrained else -29
                )
            labels = [c for c in doc.winfo_children() if isinstance(c, tk.Label)]
            assert labels and all(
                str(c.cget("font")) == str(doc.cget("font")) for c in labels
            )
            assert doc.get("1.0", "end-1c") == source
        doc.apply_theme()
        assert doc.get("1.0", "end-1c") == source
        assert doc.request(source) is False
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        out.mkdir(parents=True, exist_ok=True)
        save_native_capture(doc, out / f"log-{scale}x-native.png")
        doc.request("Replacement")
        assert not doc.winfo_children()
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
@pytest.mark.parametrize("orient", ["vertical", "horizontal"])
def test_scrollbar_canonical_chrome_preserves_fractional_drag(dpi, orient):
    from types import SimpleNamespace

    from yt_downloader.ui_widgets import SleekScrollbar

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        scale = dpi // 96 if dpi else 1
        root.geometry(f"{320 * scale}x{320 * scale}+40+40")
        calls = []
        bar = SleekScrollbar(
            root, orient=orient, command=lambda *args: calls.append(args)
        )
        bar.pack(fill="y" if orient == "vertical" else "x", expand=True)
        bar.set(0, 0.01)
        pump(root)
        cross = bar.winfo_width() if orient == "vertical" else bar.winfo_height()
        assert cross == 8 * scale
        start, end = bar._thumb_bounds()
        assert end - start == 28 * scale
        assert float(bar.itemcget(bar.find_all()[0], "width")) == 4 * scale
        length = bar.winfo_height() if orient == "vertical" else bar.winfo_width()
        bar._begin_drag(SimpleNamespace(x=7 * scale, y=7 * scale))
        bar._drag(
            SimpleNamespace(
                x=(length - 28 * scale) / 2 + 7 * scale,
                y=(length - 28 * scale) / 2 + 7 * scale,
            )
        )
        assert calls[-1][0] == "moveto"
        assert calls[-1][1] == pytest.approx(0.495)
        bar.set(0, 1)
        assert bar._drag_offset is None
        count = len(calls)
        bar._drag(SimpleNamespace(x=length, y=length))
        assert len(calls) == count
        assert not bar.find_all()
    finally:
        root.destroy()


@pytest.mark.parametrize("theme", ["Violet", "Cobalt", "Jade", "Ember", "Rose"])
def test_keyboard_tab_focus_material_preserves_selection_and_restores(
    theme, monkeypatch, tmp_path
):
    from PIL import ImageChops

    from tests.test_matte_native import save_native_capture
    from yt_downloader.ui_theme import THEME_PRESETS
    from yt_downloader.ui_widgets import SegmentedSelector

    for key, value in THEME_PRESETS[theme].items():
        monkeypatch.setitem(THEME, key, value)
    root = tk.Tk()
    try:
        root.geometry("640x300+40+40")
        root.configure(bg=THEME["bg"])
        apply_product_styles(root)
        first = ttk.Button(root, text="Library", style="FocusNav.TButton")
        selected = ttk.Button(root, text="Forge", style="FocusNavActive.TButton")
        field = ProductEntry(root)
        field.insert(0, "Destination")
        # Native Tab entry selects its text; start with the same selection so
        # restoration compares identical document state, not changed selection.
        field.selection_range(0, "end")
        variable = tk.StringVar(root, "MP4")
        segments = SegmentedSelector(
            root, variable=variable, values=("MP4", "MP3"), separated=True
        )
        for widget in (first, selected, field, segments):
            widget.pack(pady=10)
        pump(root)
        first.focus_force()
        pump(root)
        out = (
            Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path))) / theme
        )
        out.mkdir(parents=True, exist_ok=True)
        # Actual Tk Tab bindings, not direct calls to the material renderer.
        for name, widget in [
            ("selected-nav", selected),
            ("field", field),
            ("selected-segment", segments._labels["MP4"]),
        ]:
            before = save_native_capture(widget, out / f"{name}-before.png").convert(
                "RGB"
            )
            previous = root.focus_get()
            previous.event_generate("<Tab>")
            pump(root)
            assert root.focus_get() is widget
            if isinstance(widget, ttk.Widget):
                assert "focus" in widget.state()
            during = save_native_capture(widget, out / f"{name}-focused.png").convert(
                "RGB"
            )
            assert ImageChops.difference(before, during).getbbox()
            assert variable.get() == "MP4"
            assert field.get() == "Destination"
            widget.event_generate("<Shift-Tab>")
            pump(root)
            assert root.focus_get() is previous
            after = save_native_capture(widget, out / f"{name}-restored.png").convert(
                "RGB"
            )
            assert ImageChops.difference(before, after).getbbox() is None
            previous.event_generate("<Tab>")
            pump(root)
        assert variable.get() == "MP4"
    finally:
        root.destroy()


def test_inspector_notebook_uses_shared_selected_focus_material(tmp_path):
    from PIL import ImageChops

    from tests.test_matte_native import save_native_capture

    root = tk.Tk()
    try:
        root.geometry("520x220+40+40")
        apply_product_styles(root)
        notebook = ttk.Notebook(root, style="Archive.TNotebook", takefocus=True)
        notebook.pack(fill="both", expand=True, padx=20, pady=20)
        for title in ("Details", "Technical"):
            notebook.add(ttk.Frame(notebook), text=title)
        root.focus_force()
        pump(root)
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        out.mkdir(parents=True, exist_ok=True)
        before = save_native_capture(notebook, out / "notebook-selected.png").convert(
            "RGB"
        )
        selected = notebook.select()
        notebook.focus_force()
        pump(root)
        focused = save_native_capture(notebook, out / "notebook-focused.png").convert(
            "RGB"
        )
        assert notebook.select() == selected
        assert ImageChops.difference(before, focused).getbbox()
        assert "Notebook.focus" not in str(
            ttk.Style(root).layout("Archive.TNotebook.Tab")
        )
        notebook.event_generate("<Right>")
        pump(root)
        assert notebook.index(notebook.select()) == 1
        notebook.event_generate("<Left>")
        pump(root)
        assert notebook.select() == selected
        root.focus_force()
        pump(root)
        restored = save_native_capture(notebook, out / "notebook-restored.png").convert(
            "RGB"
        )
        assert ImageChops.difference(before, restored).getbbox() is None
    finally:
        root.destroy()


@pytest.mark.parametrize("kind", ["editor", "collection", "volume"])
def test_exception_controls_retire_perimeter_focus_without_losing_input(kind, tmp_path):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.library_collection_ui import LibraryCollectionDialog
    from yt_downloader.media_player_ui import PlayerVolumeControl
    from yt_downloader.ui_editable_text import EditableTextSection

    root = tk.Tk()
    try:
        root.geometry("650x450+40+40")
        apply_product_styles(root)
        saved = []
        if kind == "editor":
            owner = EditableTextSection(
                root,
                title="Notes",
                save=lambda *v: saved.append(v) or True,
                changed=lambda: None,
            )
            owner.pack(fill="both", expand=True)
            owner.present("fixture", "Original note", "")
            owner.begin()
            target, capture = owner.text, owner
        elif kind == "collection":
            owner = LibraryCollectionDialog(
                root,
                [("a", "First file"), ("b", "Second file")],
                lambda *v: saved.append(v),
                selected=("a",),
            )
            target, capture = owner.items, owner.popup
        else:
            variable = tk.IntVar(root, 40)
            owner = PlayerVolumeControl(
                root, variable=variable, command=lambda *v: saved.append(v)
            )
            owner.pack(pady=40)
            target = capture = owner
        pump(root)
        target.focus_force()
        pump(root)
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        out.mkdir(parents=True, exist_ok=True)
        save_native_capture(capture, out / f"{kind}-focused.png")
        assert int(target.cget("highlightthickness")) == 0
        if kind == "volume":
            assert not target.find_withtag("keyboard-focus")
            target.event_generate("<Right>")
            pump(root)
            assert variable.get() == 45
        elif kind == "editor":
            target.insert("end", " edited")
            owner.commit()
            assert saved == [("fixture", "Original note edited")]
        else:
            assert target.curselection() == (0,)
            target.event_generate("<Down>")
            pump(root)
            assert target.index("active") == 1
            assert saved == []
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
@pytest.mark.parametrize("placement", ["below", "above"])
def test_run_hover_units_preserve_rows_ellipsis_viewport_and_dispatch(
    dpi, placement, tmp_path
):
    import json

    from tests.test_matte_native import save_native_capture
    from yt_downloader.run_hover_menu import RunHoverMenu

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        root.geometry("1200x780+40+40")
        apply_product_styles(root)
        button = ttk.Button(root, text="All runs")
        button.place(
            x=1000, y=30 if placement == "below" else 650, width=180, height=70
        )
        records = [
            {"id": i, "title": f"Run {i} — WWW café 東京 " * 4, "status": "Completed"}
            for i in range(8)
        ]
        scale = 2 if dpi else 1
        probe_font = tkfont.Font(
            root=root, family=FONT_UI[0], size=-29 if dpi else FONT_UI[1]
        )
        available = 380 * scale
        # A complete label that fits must not lose characters just because
        # adding an unnecessary ellipsis would exceed the available width.
        title = max(
            (
                "W" * n
                for n in range(1, 56)
                if probe_font.measure("W" * n + " — Completed") <= available
            ),
            key=len,
        )
        assert probe_font.measure(title + " — Completed…") > available
        records[1]["title"] = title
        selected = []
        owner = RunHoverMenu(button, lambda: records, selected.append)
        pump(root)
        owner.show()
        pump(root)
        assert owner.popup is not None
        popup, menu = owner.popup, owner.menu
        row = 31 * scale
        text_items = [i for i in menu.find_all() if menu.type(i) == "text"]
        drawn = [menu.itemcget(i, "text") for i in text_items]
        font = menu.itemcget(text_items[0], "font")
        assert int(root.tk.call("font", "configure", font, "-size")) == (
            -29 if dpi else FONT_UI[1]
        )
        measure = lambda value: int(root.tk.call("font", "measure", font, value))
        labels = [str(r["title"])[:55] + " — " + r["status"] for r in records]
        available = menu.winfo_width() - 20 * scale
        expected = [
            label
            if measure(label) <= available
            else max(
                (
                    label[:n] + "…"
                    for n in range(len(label) + 1)
                    if measure(label[:n] + "…") <= available
                ),
                key=len,
            )
            for label in labels
        ]
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        name = f"run-hover-{dpi or 'default'}-{placement}"
        save_native_capture(popup, out / f"{name}.png")
        (out / f"{name}.json").write_text(
            json.dumps(
                {
                    "requested_canvas": [menu.winfo_reqwidth(), menu.winfo_reqheight()],
                    "font": font,
                    "drawn": drawn,
                    "expected": expected,
                    "scope": "Mac source native, injected units; no physical Windows or OS-key claim",
                },
                indent=2,
            )
        )
        assert menu.winfo_reqwidth() == 400 * scale
        assert menu.winfo_reqheight() == 5 * row
        assert drawn == expected
        for index, item in enumerate(text_items):
            assert menu.coords(item) == [10 * scale, index * row + row / 2]
            box = menu.bbox(item)
            assert box[1] >= index * row and box[3] <= (index + 1) * row
        assert root.winfo_rootx() <= popup.winfo_rootx()
        assert (
            popup.winfo_rootx() + popup.winfo_width()
            <= root.winfo_rootx() + root.winfo_width()
        )
        if placement == "below":
            assert popup.winfo_rooty() >= button.winfo_rooty() + button.winfo_height()
        else:
            assert popup.winfo_rooty() + popup.winfo_height() <= button.winfo_rooty()
        menu.yview_moveto(1)
        pump(root)
        y = round((len(records) - 0.5) * row - menu.canvasy(0))
        assert 0 <= y < menu.winfo_height()
        menu.event_generate("<Motion>", x=20 * scale, y=y)
        menu.event_generate("<Return>")
        pump(root)
        assert selected == [records[-1]]
        assert owner.popup is None and owner.pending is None
        assert owner._menu_surfaces.bytes == 0
        owner.show()
        pump(root)
        assert owner.popup is not None
        button.place_configure(x=1220)
        pump(root)
        assert owner.popup is None, "Menu survived its anchor leaving the viewport"
        assert selected == [records[-1]]
    finally:
        root.destroy()


def test_run_hover_selected_row_uses_shared_material_and_keeps_dispatch(tmp_path):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.run_hover_menu import RunHoverMenu

    root = tk.Tk()
    try:
        root.geometry("640x350+40+40")
        apply_product_styles(root)
        button = ttk.Button(root, text="All runs")
        button.pack(anchor="ne", padx=20, pady=20)
        records = [
            {"id": i, "title": f"Run {i}", "status": "Completed"} for i in range(3)
        ]
        selected = []
        owner = RunHoverMenu(button, lambda: records, selected.append)
        pump(root)
        owner.show()
        pump(root)
        assert owner.popup is not None
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        out.mkdir(parents=True, exist_ok=True)
        save_native_capture(owner.popup, out / "run-hover-selected.png")
        assert not any(
            owner.menu.type(item) == "rectangle" for item in owner.menu.find_all()
        )
        owner.menu.event_generate("<Return>")
        pump(root)
        assert selected == [records[0]]
        assert owner.popup is None
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_primary_button_hover_cannot_replace_keyboard_focus_material(dpi):
    from PIL import ImageColor

    from yt_downloader.platform_services import capture_own_widget
    from yt_downloader.ui_button_contract import ProductButton

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        apply_product_styles(root)
        button = ProductButton(root, text="Continue", style="Accent.TButton", width=24)
        button.pack(padx=30, pady=30)
        pump(root)
        button.focus_force()
        button.state(["!active"])
        pump(root)
        before = capture_own_widget(button).convert("RGB")
        button.state(["active"])
        pump(root)
        assert button.instate(["focus", "active"])
        image = capture_own_widget(button).convert("RGB")
        scale = dpi // 96 if dpi else 1
        point = (20 * scale, button.winfo_height() // 2)
        assert image.getpixel(point) == before.getpixel(point)
        assert (
            max(
                abs(a - b)
                for a, b in zip(
                    image.getpixel(point),
                    ImageColor.getrgb(THEME["focus_surface"]),
                    strict=True,
                )
            )
            <= 1
        )
        button.state(["disabled"])
        assert button.instate(["disabled"])
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
@pytest.mark.parametrize("width", [92, 160, 260])
def test_navigation_stretch_has_no_internal_seams_and_detects_prior_tiling(
    dpi, width, monkeypatch, tmp_path
):
    from tests.test_matte_native import save_native_capture
    from yt_downloader import ui_chrome
    from yt_downloader.ui_button_contract import ProductButton

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        scale = dpi // 96 if dpi else 1
        apply_product_styles(root)
        root.configure(bg=THEME["bg"])
        root.geometry(f"{(width + 40) * scale}x{100 * scale}+40+40")
        button = ProductButton(root, text="Library", style="FocusNav.TButton")
        button.place(x=20 * scale, y=20 * scale, width=width * scale, height=44 * scale)
        root.focus_force()
        pump(root)
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        out.mkdir(parents=True, exist_ok=True)
        name = f"nav-{scale}x-{width}"

        def capture(label):
            return save_native_capture(button, out / f"{name}-{label}.png").convert(
                "RGB"
            )

        def spread(bitmap):
            # Interior horizontal band above the label, beyond rounded corners.
            backing = bitmap.width / button.winfo_width()
            spreads = []
            for y in range(round(2 * scale * backing), round(12 * scale * backing)):
                band = bitmap.crop(
                    (
                        round(20 * scale * backing),
                        y,
                        bitmap.width - round(20 * scale * backing),
                        y + 1,
                    )
                )
                spreads.append(max(high - low for low, high in band.getextrema()))
            return max(spreads)

        idle = capture("resting")
        assert spread(idle) <= 1
        button.state(["active"])
        pump(root)
        hovered = capture("hover")
        assert spread(hovered) <= 1
        button.state(["!active"])
        pump(root)
        original = ui_chrome.ttk_surface_image

        def prior_unflattened(*args, **kwargs):
            kwargs["stretch"] = False
            return original(*args, **kwargs)

        with monkeypatch.context() as fault:
            fault.setattr(ui_chrome, "ttk_surface_image", prior_unflattened)
            root._product_chrome_owner._committed = None
            root._product_chrome_owner.request(ttk.Style(root))
            button.state(["active"])
            pump(root)
            button.state(["!active"])
            pump(root)
            broken = capture("prior-tiling-fault")
            assert spread(broken) > 3, (
                "The independent interior-band oracle missed prior tiling"
            )
        root._product_chrome_owner._committed = None
        root._product_chrome_owner.request(ttk.Style(root))
        button.state(["active"])
        pump(root)
        button.state(["!active"])
        pump(root)
        restored = capture("restored")
        assert restored.tobytes() == idle.tobytes()
        assert spread(restored) <= 1
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_collection_dialog_owns_list_units_and_retains_failed_save(
    dpi, monkeypatch, tmp_path
):
    from tests.test_matte_native import save_native_capture
    from yt_downloader import library_collection_ui as module
    from yt_downloader.ui_layout import bounded_window_size, window_logical_metrics

    root = tk.Tk()
    try:
        install_window_logical_metrics(root, dpi=192)
        apply_product_styles(root)
        root.geometry("1000x740+40+40")
        original = tk.Toplevel

        class AdmittedPopup(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if dpi:
                    install_window_logical_metrics(self, dpi=dpi)

        monkeypatch.setattr(module.tk, "Toplevel", AdmittedPopup)
        attempts, saved = [], []

        def save(name, owners):
            attempts.append((name, owners))
            if len(attempts) == 1:
                raise OSError(
                    "Fixture save failed. Your name and selected items must remain available."
                )
            saved.append((name, owners))

        items = [(f"owner-{i}", f"Saved item {i} — café 東京") for i in range(60)]
        dialog = module.LibraryCollectionDialog(
            root, items, save, selected=("owner-1",)
        )
        pump(root)
        popup = dialog.popup
        metrics = window_logical_metrics(popup)
        scale = 2 if dpi else 1
        assert metrics.scale == scale
        assert window_logical_metrics(root).scale == 2
        expected_font = metrics.font(FONT_UI)
        actual_lines = int(
            popup.tk.call("font", "metrics", dialog.items.cget("font"), "-linespace")
        )
        expected_lines = int(
            popup.tk.call("font", "metrics", expected_font, "-linespace")
        )
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(popup, out / f"collection-{dpi or 'default'}-initial.png")
        assert actual_lines == expected_lines
        row = dialog.items.bbox(1)
        assert expected_lines <= row[3] <= expected_lines + 4 * scale
        limit = bounded_window_size(
            popup.winfo_screenwidth(), popup.winfo_screenheight()
        )
        assert popup.winfo_width() == min(540 * scale, limit[0])
        assert popup.winfo_height() == min(480 * scale, limit[1])
        assert tuple(popup.minsize()) == (
            min(500 * scale, limit[0]),
            min(400 * scale, limit[1]),
        )
        assert (
            0 <= popup.winfo_rootx()
            and popup.winfo_rootx() + popup.winfo_width() <= popup.winfo_screenwidth()
        )
        assert (
            0 <= popup.winfo_rooty()
            and popup.winfo_rooty() + popup.winfo_height() <= popup.winfo_screenheight()
        )
        assert dialog.dialog_surface.action_is_visible(dialog.save_button)
        dialog.name.set("Dense collection")
        dialog.items.see(59)
        dialog.items.focus_force()
        pump(root)
        x, y, _width, height = dialog.items.bbox(59)
        dialog.items.event_generate("<ButtonPress-1>", x=x + 8, y=y + height // 2)
        dialog.items.event_generate("<ButtonRelease-1>", x=x + 8, y=y + height // 2)
        pump(root)
        assert dialog.items.curselection() == (1, 59)
        dialog.save_button.invoke()
        pump(root)
        assert dialog.error.get().startswith("Fixture save failed")
        assert popup.winfo_exists() and dialog.name.get() == "Dense collection"
        assert dialog.items.curselection() == (1, 59)
        assert saved == [] and len(attempts) == 1
        assert dialog.dialog_surface.action_is_visible(dialog.save_button)
        save_native_capture(
            popup, out / f"collection-{dpi or 'default'}-failed-save.png"
        )
        minimum_width, minimum_height = popup.minsize()
        popup.geometry(f"{minimum_width}x{minimum_height}")
        pump(root)
        error_label = next(
            widget
            for widget in dialog.dialog_surface.footer.winfo_children()
            if isinstance(widget, ttk.Label)
            and str(widget.cget("textvariable")) == str(dialog.error)
        )
        save_native_capture(popup, out / f"collection-{dpi or 'default'}-minimum.png")
        assert int(error_label.cget("wraplength")) <= error_label.winfo_width()
        assert dialog.dialog_surface.protected_content_is_visible(error_label)
        assert dialog.dialog_surface.action_is_visible(dialog.save_button)
        assert dialog.items.curselection() == (1, 59)
        dialog.save_button.invoke()
        pump(root)
        assert saved == [("Dense collection", ("owner-1", "owner-59"))]
        assert not popup.winfo_exists()
        assert window_logical_metrics(root).scale == 2
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_scene_rail_units_keep_measured_viewport_and_final_target(dpi, tmp_path):
    from types import SimpleNamespace

    from tests.test_matte_native import save_native_capture
    from yt_downloader.scene_rail import SceneRail
    from yt_downloader.ui_layout import window_logical_metrics

    root = tk.Tk()
    pending = None
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        root.geometry("1000x700+40+40")
        apply_product_styles(root)
        parent = tk.Canvas(root, highlightthickness=0, bg=THEME["bg"])
        parent.pack(fill="both", expand=True)
        metrics = window_logical_metrics(parent)
        scale = metrics.scale
        rows = [SimpleNamespace(key=f"item-{i}") for i in range(12)]
        width, height, stride = 760, 180 * scale, 200 * scale
        selected, used = [], []

        def changed():
            nonlocal pending
            if pending is None:
                pending = root.after_idle(present)

        rail = SceneRail(parent, changed=changed, used=lambda: used.append(True))

        def draw(item, left):
            bounds = (left, 0, left + stride - 14 * scale, 140 * scale)
            rail._depth.draw(bounds)
            rail.canvas.create_text(
                left + 12 * scale,
                14 * scale,
                text=item.key,
                anchor="nw",
                font=metrics.font(FONT_UI),
                fill=THEME["text"],
            )
            rail._targets.append((bounds, lambda key=item.key: selected.append(key)))

        def present():
            nonlocal pending
            pending = None
            if rail._closed:
                return
            parent.delete("all")
            rail.present(
                rows, y=30, width=width, height=height, stride=stride, draw=draw
            )

        pump(root)
        present()
        pump(root)
        present()
        pump(root)
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(rail, out / f"rail-{dpi or 'default'}-initial.png")
        assert rail.winfo_width() == width and rail.winfo_height() == height
        assert rail._stride == stride and rail.winfo_y() == 30
        assert rail._bar.winfo_height() == 8 * scale
        assert rail._bar.winfo_y() - rail.canvas.winfo_height() == 4 * scale
        assert rail.canvas.winfo_reqheight() == height - 12 * scale
        assert tuple(map(float, rail.canvas.cget("scrollregion").split())) == (
            0,
            0,
            len(rows) * stride - 14 * scale,
            height - 12 * scale,
        )
        rail.canvas.focus_force()
        rail.canvas.event_generate("<End>")
        pump(root)
        assert rail._focus_index == len(rows) - 1
        target = rail._focused()
        assert target is not None
        left = rail.canvas.canvasx(0)
        assert left <= target[0][0] and target[0][2] <= left + rail.canvas.winfo_width()
        assert abs(target[0][2] - left - rail.canvas.winfo_width()) <= 1
        rail.canvas.event_generate("<Return>")
        pump(root)
        assert selected == [rows[-1].key]
        width = 640  # Already-measured caller width must not be doubled.
        present()
        pump(root)
        rail.canvas.event_generate("<End>")
        pump(root)
        assert rail.winfo_width() == 640 and rail.canvas.winfo_width() == 640
        assert rail._focused()[0][2] <= rail.canvas.canvasx(0) + 640
        save_native_capture(rail, out / f"rail-{dpi or 'default'}-last.png")
        rail.destroy()
        pump(root)
        assert rail._closed and not rail._targets and rail._depth.bytes == 0
        assert used and selected == [rows[-1].key]
    finally:
        if pending is not None:
            root.after_cancel(pending)
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
@pytest.mark.parametrize("categories", [(), ("Research", "Saved research")])
def test_annotation_dialog_owns_text_units_and_preserves_retry(
    dpi, categories, monkeypatch, tmp_path
):
    from tests.test_matte_native import save_native_capture
    from yt_downloader import library_annotation_ui as module
    from yt_downloader.library_annotations import LibraryAnnotation
    from yt_downloader.ui_button_contract import ProductButton
    from yt_downloader.ui_layout import bounded_window_size, window_logical_metrics

    root = tk.Tk()
    try:
        install_window_logical_metrics(root, dpi=192)
        apply_product_styles(root)
        root.geometry("1000x740+40+40")
        original = tk.Toplevel

        class AdmittedPopup(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if dpi:
                    install_window_logical_metrics(self, dpi=dpi)

        monkeypatch.setattr(module.tk, "Toplevel", AdmittedPopup)
        attempts = []

        def save(value):
            attempts.append(value)
            return len(attempts) > 1

        dialog = module.LibraryAnnotationDialog(
            root,
            title="Saved media — café 東京",
            categories=categories,
            annotation=LibraryAnnotation(note="Original note", category="Research"),
            on_save=save,
        )
        dialog.show()
        pump(root)
        popup = dialog.popup
        metrics = window_logical_metrics(popup)
        scale = 2 if dpi else 1
        assert metrics.scale == scale
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(popup, out / f"annotation-{dpi or 'default'}-initial.png")
        actual = int(
            popup.tk.call("font", "metrics", dialog.note.cget("font"), "-linespace")
        )
        expected = int(
            popup.tk.call("font", "metrics", metrics.font(FONT_UI), "-linespace")
        )
        assert actual == expected
        assert int(dialog.note.cget("padx")) == 12 * scale
        limit = bounded_window_size(
            popup.winfo_screenwidth(), popup.winfo_screenheight()
        )
        assert (popup.winfo_width(), popup.winfo_height()) == (
            min(620 * scale, limit[0]),
            min(520 * scale, limit[1]),
        )
        assert tuple(popup.minsize()) == (
            min(520 * scale, limit[0]),
            min(500 * scale, limit[1]),
        )
        buttons = [
            w
            for w in dialog.dialog_surface.footer.winfo_children()
            if isinstance(w, ProductButton)
        ]
        save_button = next(w for w in buttons if w.cget("text") == "Save details")
        draft = "Changed note — café 東京\n" * 20
        dialog.note.delete("1.0", "end")
        dialog.note.insert("1.0", draft)
        dialog.tags_var.set("one,two")
        dialog.category_var.set("Saved research")
        save_button.invoke()
        pump(root)
        assert len(attempts) == 1 and popup.winfo_exists()
        assert dialog.note.get("1.0", "end-1c") == draft
        assert (
            dialog.tags_var.get() == "one,two"
            and dialog.category_var.get() == "Saved research"
        )
        w, h = popup.minsize()
        popup.geometry(f"{w}x{h}")
        pump(root)
        save_native_capture(popup, out / f"annotation-{dpi or 'default'}-minimum.png")
        for button in buttons:
            assert dialog.dialog_surface.action_is_visible(button)
        assert dialog.note.winfo_height() >= expected + 20 * scale
        viewport = dialog.dialog_surface.viewport
        assert (viewport is not None) == bool(dpi)
        dialog.note.focus_force()
        pump(root)
        visible_top = (
            viewport.winfo_rooty()
            if viewport
            else dialog.dialog_surface.body.winfo_rooty()
        )
        visible_bottom = (
            viewport.winfo_rooty() + viewport.winfo_height()
            if viewport
            else dialog.dialog_surface.footer.winfo_rooty()
        )
        assert dialog.note.winfo_rooty() >= visible_top
        assert dialog.note.winfo_rooty() + dialog.note.winfo_height() <= visible_bottom
        save_native_capture(
            popup, out / f"annotation-{dpi or 'default'}-note-revealed.png"
        )
        dialog.note.see("20.0")
        pump(root)
        assert dialog.note.dlineinfo("20.0") is not None
        category = next(
            w
            for w in dialog.dialog_surface.body.winfo_children()
            if isinstance(w, (ProductEntry, ChoiceDropdown))
            and str(w.cget("textvariable")) == str(dialog.category_var)
        )
        category.focus_force()
        pump(root)
        assert category.winfo_rooty() >= visible_top
        assert category.winfo_rooty() + category.winfo_height() <= visible_bottom
        assert dialog.note.get("1.0", "end-1c") == draft
        for label in dialog.dialog_surface.body.winfo_children():
            if isinstance(label, ttk.Label):
                assert (
                    label.winfo_rootx() + label.winfo_width()
                    <= popup.winfo_rootx() + popup.winfo_width()
                )
                if int(label.cget("wraplength") or 0):
                    assert int(label.cget("wraplength") or 0) <= label.winfo_width()
        assert (
            0 <= popup.winfo_rootx()
            and popup.winfo_rootx() + popup.winfo_width() <= popup.winfo_screenwidth()
        )
        assert (
            0 <= popup.winfo_rooty()
            and popup.winfo_rooty() + popup.winfo_height() <= popup.winfo_screenheight()
        )
        save_button.invoke()
        pump(root)
        assert len(attempts) == 2 and attempts[0] == attempts[1]
        assert attempts[-1].note == draft and attempts[-1].tags == ("one", "two")
        assert not popup.winfo_exists()
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
@pytest.mark.parametrize("kind", ["unavailable", "ambiguous", "legacy", "missing"])
def test_media_recovery_dialog_owns_units_and_keeps_exact_action(
    dpi, kind, monkeypatch, tmp_path
):
    from tests.test_library_media_recovery import _job
    from tests.test_matte_native import save_native_capture
    from yt_downloader import library_media_recovery_ui as module
    from yt_downloader.library_media_recovery import LibraryMediaRecoveryPlan
    from yt_downloader.ui_button_contract import ProductButton
    from yt_downloader.ui_layout import bounded_window_size, window_logical_metrics
    from yt_downloader.ui_theme import FONT_UI_SMALL

    root = tk.Tk()
    try:
        install_window_logical_metrics(root, dpi=192)
        apply_product_styles(root)
        root.geometry("1000x740+40+40")
        original = tk.Toplevel

        class AdmittedPopup(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if dpi:
                    install_window_logical_metrics(self, dpi=dpi)

        monkeypatch.setattr(module.tk, "Toplevel", AdmittedPopup)
        chosen = []
        plan = LibraryMediaRecoveryPlan(
            kind,
            tmp_path / "Saved media — café 東京",
            job=_job(tmp_path) if kind == "missing" else None,
            requires_destination_choice=kind != "unavailable",
            preset_migrated=kind == "legacy",
        )
        dialog = module.LibraryMediaRecoveryDialog(
            root, plan=plan, on_action=chosen.append
        )
        dialog.show()
        pump(root)
        popup = dialog.popup
        metrics = window_logical_metrics(popup)
        scale = 2 if dpi else 1
        assert metrics.scale == scale
        labels = [
            w
            for w in dialog.dialog_surface.body.winfo_children()
            if isinstance(w, ttk.Label)
        ]
        message = next(w for w in labels if w.cget("text") == dialog.prompt.message)
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(popup, out / f"recovery-{kind}-{dpi or 'default'}.png")
        actual = popup.tk.call(
            "font",
            "metrics",
            message.cget("font") or ttk.Style(root).lookup("Muted.TLabel", "font"),
            "-linespace",
        )
        expected = popup.tk.call(
            "font", "metrics", metrics.font(FONT_UI_SMALL), "-linespace"
        )
        assert int(actual) == int(expected)
        limit = bounded_window_size(
            popup.winfo_screenwidth(), popup.winfo_screenheight()
        )
        assert popup.winfo_width() == min(540 * scale, limit[0])
        assert popup.winfo_height() == min(popup.winfo_reqheight(), limit[1])
        assert (
            0 <= popup.winfo_rootx()
            and popup.winfo_rootx() + popup.winfo_width() <= popup.winfo_screenwidth()
        )
        assert (
            0 <= popup.winfo_rooty()
            and popup.winfo_rooty() + popup.winfo_height() <= popup.winfo_screenheight()
        )
        assert dialog.path_entry.get() == dialog.prompt.detail
        assert str(dialog.path_entry.cget("state")) == "readonly"
        for label in labels:
            assert label.winfo_reqwidth() <= label.winfo_width()
            assert (
                label.winfo_rooty() + label.winfo_height()
                <= dialog.dialog_surface.footer.winfo_rooty()
            )
        buttons = [
            w
            for w in dialog.dialog_surface.footer.winfo_children()
            if isinstance(w, ProductButton)
        ]
        for button in buttons:
            assert dialog.dialog_surface.action_is_visible(button)
        primary = next(
            w for w in buttons if w.cget("text") == dialog.prompt.primary_label
        )
        primary.invoke()
        pump(root)
        assert not popup.winfo_exists()
        assert chosen == (
            []
            if kind in {"unavailable", "ambiguous"}
            else [dialog.prompt.primary_action]
        )
        assert root.grab_current() is None
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_consent_panel_units_keep_choices_visible_and_dispatch_once(
    dpi, tmp_path, monkeypatch
):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.analytics_consent_ui import AnalyticsConsentPanel
    from yt_downloader.ui_layout import window_logical_metrics
    from yt_downloader.ui_theme import FONT_UI_SMALL

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        apply_product_styles(root)
        root.geometry("1100x740+40+40")
        pump(root)
        origin = tk.Entry(root)
        origin.pack()
        pump(root)
        origin.focus_force()
        pump(root)
        chosen, privacy = [], []
        panel = AnalyticsConsentPanel(root, chosen.append, lambda: privacy.append(True))
        pump(root)
        metrics = window_logical_metrics(panel.frame)
        scale = 2 if dpi else 1
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(
            panel.frame, out / f"consent-{dpi or 'default'}-initial.png"
        )
        label = panel.benefit_labels[0]
        font = label.cget("font") or ttk.Style(root).lookup("Muted.TLabel", "font")
        assert int(root.tk.call("font", "metrics", font, "-linespace")) == int(
            root.tk.call("font", "metrics", metrics.font(FONT_UI_SMALL), "-linespace")
        )
        assert panel.frame.winfo_width() == min(
            620 * scale, root.winfo_width() - 48 * scale
        )
        icons = [w for w in label.master.winfo_children() if isinstance(w, tk.Canvas)]
        assert len(icons) == 4
        for icon in icons:
            assert (icon.winfo_width(), icon.winfo_height()) == (36 * scale, 36 * scale)
            for item in icon.find_all():
                coords = icon.coords(item)
                assert min(coords) >= 0 and max(coords) <= 36 * scale
        for width, height in ((1100, 740), (860, 600)):
            root.geometry(f"{width}x{height}")
            pump(root)
            frame = panel.frame
            assert (
                0 <= frame.winfo_x()
                and frame.winfo_x() + frame.winfo_width() <= root.winfo_width()
            )
            assert (
                0 <= frame.winfo_y()
                and frame.winfo_y() + frame.winfo_height() <= root.winfo_height()
            )
            for control in panel.controls:
                assert panel.surface.protected_content_is_visible(control)
            for label in panel.benefit_labels:
                assert label.winfo_reqwidth() <= label.winfo_width()
            save_native_capture(frame, out / f"consent-{dpi or 'default'}-{width}.png")
        if panel.surface.viewport is not None:
            viewport = panel.surface.viewport
            assert panel._benefit_columns == 2
            from types import SimpleNamespace

            holder = panel.benefit_labels[0].master
            # Recreate the prior fixed-four-column layout without changing source.
            with monkeypatch.context() as prior:
                prior.setattr(panel, "_benefit_min_width", 0)
                panel._layout_benefits(
                    SimpleNamespace(widget=holder, width=holder.winfo_width())
                )
                pump(root)
                word = "information"
                label = panel.benefit_labels[0]
                assert int(
                    root.tk.call("font", "measure", label.cget("font"), word)
                ) > int(label.cget("wraplength"))
            panel._layout_benefits(
                SimpleNamespace(widget=holder, width=holder.winfo_width())
            )
            pump(root)
            assert panel._benefit_columns == 2
            for index, label in enumerate(panel.benefit_labels):
                top = label.winfo_rooty() - panel.surface.body.winfo_rooty()
                viewport.yview_moveto(top / max(1, panel.surface.body.winfo_height()))
                pump(root)
                assert label.winfo_rooty() >= viewport.winfo_rooty()
                assert (
                    label.winfo_rooty() + label.winfo_height()
                    <= viewport.winfo_rooty() + viewport.winfo_height()
                )
                for word in str(label.cget("text")).split():
                    measured = int(
                        root.tk.call("font", "measure", label.cget("font"), word)
                    )
                    assert measured <= int(label.cget("wraplength"))
                for control in panel.controls:
                    assert panel.surface.protected_content_is_visible(control)
                save_native_capture(
                    panel.frame, out / f"consent-192-benefit-{index}-revealed.png"
                )
        panel.privacy.focus_force()
        pump(root)
        panel.privacy.event_generate("<Return>")
        pump(root)
        assert privacy == [True] and chosen == []
        panel.deny.invoke()
        panel.finish(True)
        pump(root)
        assert chosen == [False]
        assert not panel.frame.winfo_exists() and root.grab_current() is None
        assert root.focus_get() is origin
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_activity_panel_units_couple_mode_hit_boundary_and_log_viewport(dpi, tmp_path):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.forge_activity_ui import ForgeActivityPanel

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        apply_product_styles(root)
        root.geometry("760x380+40+40")
        opened = []
        panel = ForgeActivityPanel(root, on_technical=lambda: opened.append(True))
        panel.pack(fill="both", expand=True)
        raw = "\n".join(f"Technical record {i} — café 東京" for i in range(40))
        panel.technical.request(raw)
        panel.show("one", raw)
        panel.observe("one", "Video 1 of 1 — downloading")
        pump(root)
        scale = 2 if dpi else 1
        toggle = panel.toggle
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(panel, out / f"activity-{dpi or 'default'}-friendly.png")
        assert (toggle.winfo_width(), toggle.winfo_height()) == (
            30 * scale,
            116 * scale,
        )
        assert (
            panel.friendly.winfo_rootx() - (toggle.winfo_rootx() + toggle.winfo_width())
            == 8 * scale
        )
        toggle.event_generate("<ButtonPress-1>", x=15 * scale, y=58 * scale - 1)
        pump(root)
        assert not panel.expanded and opened == []
        toggle.event_generate("<B1-Motion>", x=15 * scale, y=58 * scale)
        pump(root)
        assert panel.expanded and opened == [True]
        toggle.event_generate("<ButtonRelease-1>", x=15 * scale, y=58 * scale)
        toggle.event_generate("<B1-Motion>", x=15 * scale, y=0)
        pump(root)
        assert panel.expanded and opened == [True]
        root.geometry("440x280")
        pump(root)
        assert panel.technical.get("1.0", "end-1c") == raw
        assert panel.technical.winfo_width() == panel.winfo_width() - 38 * scale
        assert panel.technical.winfo_height() == panel.winfo_height()
        assert toggle.winfo_rooty() >= panel.winfo_rooty()
        assert (
            toggle.winfo_rooty() + toggle.winfo_height()
            <= panel.winfo_rooty() + panel.winfo_height()
        )
        before = [toggle.coords(item) for item in toggle.find_all()]
        toggle.apply_theme()
        pump(root)
        assert [toggle.coords(item) for item in toggle.find_all()] == before
        assert toggle.coords(toggle.find_all()[-1]) == [
            9 * scale,
            72 * scale,
            21 * scale,
            84 * scale,
        ]
        save_native_capture(panel, out / f"activity-{dpi or 'default'}-technical.png")
        toggle.event_generate("<Up>")
        pump(root)
        assert not panel.expanded and panel.friendly.winfo_ismapped()
        toggle.event_generate("<Down>")
        pump(root)
        assert panel.expanded and opened == [True, True]
        assert panel.technical.get("1.0", "end-1c") == raw
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_output_details_owns_font_units_and_preserves_scroll_footer(
    dpi, monkeypatch, tmp_path
):
    from tests.test_matte_native import save_native_capture
    from yt_downloader import detail_ui as module
    from yt_downloader.ui_layout import window_logical_metrics

    root = tk.Tk()
    try:
        install_window_logical_metrics(root, dpi=192)
        apply_product_styles(root)
        root.geometry("1000x740+40+40")
        original = tk.Toplevel

        class AdmittedPopup(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if dpi:
                    install_window_logical_metrics(self, dpi=dpi)

        monkeypatch.setattr(module.tk, "Toplevel", AdmittedPopup)
        content = "\n".join(
            f"Field {i}: café 東京 " + "long measured value " * 8 for i in range(60)
        )
        dialog = module.OutputDetailsDialog(
            root,
            title="Saved media — café 東京 " * 12,
            sections=(("Final output", content),),
        )
        popup, document = dialog.popup, dialog.documents[0]
        metrics = window_logical_metrics(popup)
        pump(root)
        expected_font = tkfont.Font(root=popup, font=metrics.font(FONT_UI))
        actual_font = tkfont.Font(root=popup, font=document.cget("font"))
        assert actual_font.metrics("linespace") == expected_font.metrics("linespace")
        assert document.raw_snapshot == "Final output\n" + content

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        done = next(
            w
            for w in descendants(popup)
            if isinstance(w, ttk.Button) and w.cget("text") == "Done"
        )
        title = next(
            w
            for w in descendants(popup)
            if isinstance(w, ttk.Label)
            and str(w.cget("text")).startswith("Saved media")
        )
        for width, height in (popup.minsize(), (1180, 900), popup.minsize()):
            popup.geometry(f"{width}x{height}")
            pump(root)
            assert title.winfo_height() >= title.winfo_reqheight()
            assert document.winfo_height() >= expected_font.metrics("linespace") * 2
            assert (
                done.winfo_rooty() + done.winfo_height()
                <= popup.winfo_rooty() + popup.winfo_height()
            )
            before = (done.winfo_rootx(), done.winfo_rooty())
            document.yview_moveto(1)
            pump(root)
            assert document.yview()[1] == 1.0
            assert before == (done.winfo_rootx(), done.winfo_rooty())
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(popup, out / f"output-details-{dpi or 'default'}.png")
        assert str(document.get("end-2l", "end")).strip()
        done.invoke()
        pump(root)
        assert not popup.winfo_exists()
    finally:
        root.destroy()


@pytest.mark.parametrize("dpi", [None, 192])
def test_pro_emblem_uses_window_units_and_native_backing(dpi, tmp_path):
    from tests.test_matte_native import save_native_capture
    from yt_downloader.platform_services import surface_backing_scale
    from yt_downloader.ui_chrome import pro_wordmark

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        root.geometry("640x180+40+40")
        emblem = pro_wordmark(root)
        label = ttk.Label(root, image=emblem)
        label.pack(padx=20, pady=20)
        pump(root)
        assert emblem.height() == (40 if dpi else 20)
        if surface_backing_scale(root) > 1:
            assert root.tk.call("image", "type", str(emblem)) == "nsimage"
        assert label.winfo_width() >= emblem.width()
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        save_native_capture(label, out / f"pro-emblem-{dpi or 'default'}.png")
    finally:
        root.destroy()
