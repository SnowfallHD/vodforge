"""Opt-in real Tcl/Tk checks; run with VODFORGE_NATIVE_UI_TESTS=1."""

import os
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest

from yt_downloader.activity_ui import (
    ActivityLogText,
    ActivitySummary,
    terminal_activity_line,
)
from yt_downloader.detail_ui import FactsText, OutputDetailsDialog
from yt_downloader.ui_styles import apply_product_styles
from yt_downloader.ui_theme import THEME
from yt_downloader.ui_widgets import (
    ChoiceDropdown,
    ChoiceMenu,
    ProductEntry,
    SegmentedSelector,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="requires native Tcl/Tk"
)


def settle_native(window):
    """Process native map/configure events, not only Tk idle layout callbacks."""
    deadline = time.monotonic() + 0.2
    while time.monotonic() < deadline:
        window.update()
        time.sleep(0.01)


def test_settings_helper_wrap_uses_allocated_width_without_shrinking(root):
    from yt_downloader.focus_settings import FocusSettingsDialog
    from yt_downloader.youtube_access import ACCESS_DESCRIPTION

    root.geometry("440x300")
    frame = ttk.Frame(root)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(0, weight=1)
    label = ttk.Label(frame, text=ACCESS_DESCRIPTION, wraplength=300, justify="left")
    label.grid(row=0, column=0, sticky="w")
    FocusSettingsDialog._bind_responsive_copy(frame)
    root.deiconify()
    for width in (440, 260, 440):
        root.geometry(f"{width}x300")
        settle_native(root)
        assert int(label.cget("wraplength")) == min(300, frame.winfo_width() - 2)
        assert label.winfo_width() == frame.winfo_width()


@pytest.fixture
def root():
    window = tk.Tk()
    window.withdraw()
    apply_product_styles(window)
    yield window
    window.destroy()


def test_forge_url_list_shortcut_uses_existing_action(monkeypatch):
    from scripts.focus_ui_preview import isolated_preview_services
    from yt_downloader.app import DownloaderApp

    calls = []
    monkeypatch.setattr(
        DownloaderApp, "_load_url_list_file", lambda self: calls.append(True)
    )
    with isolated_preview_services():
        application = DownloaderApp()
        try:
            for size in ("1180x780", "820x560"):
                application.geometry(size)
                settle_native(application)
                button = application.load_url_list_button
                audio = application.local_audio_video_button
                assert button.winfo_ismapped()
                assert (
                    button.winfo_rootx() + button.winfo_width() <= audio.winfo_rootx()
                )
                assert abs(button.winfo_rooty() - audio.winfo_rooty()) <= 2
                button.invoke()
            assert calls == [True, True]
        finally:
            application.destroy()


@pytest.mark.parametrize("size", ["1180x780", "820x560"])
def test_forge_error_guidance_wraps_beside_retry(size):
    from scripts.focus_ui_preview import isolated_preview_services
    from yt_downloader.app import DownloaderApp, format_ytdlp_user_error

    with isolated_preview_services():
        application = DownloaderApp()
        try:
            application.geometry(size)
            settle_native(application)
            message = format_ytdlp_user_error("No usable video source was found")
            application.focus_active_detail_var.set(message)
            application.focus_preview_start_button.configure(text="Retry Download")
            application.focus_percent_label.grid_remove()
            application.focus_preview_start_button.grid()
            settle_native(application)
            label = application.focus_active_detail_label
            assert label.cget("text") == message
            assert float(label.cget("wraplength")) <= label.master.winfo_width()
            assert label.winfo_height() >= label.winfo_reqheight()
            assert label.winfo_height() > 30
            assert (
                label.winfo_rootx() + label.winfo_width()
                <= application.focus_preview_start_button.winfo_rootx()
            )
        finally:
            application.destroy()


def test_all_runs_hover_and_click_remain_independent(monkeypatch):
    from scripts.focus_ui_preview import isolated_preview_services
    from yt_downloader.app import DownloaderApp

    with isolated_preview_services():
        application = DownloaderApp()
        try:
            # This is a returning-user Run Deck interaction. A fresh profile's
            # delayed Welcome tour otherwise correctly takes focus on Windows.
            application.engagement.state.presented_welcome()
            application.geometry("1180x780")
            settle_native(application)
            owner = application.focus_run_hover_menu
            record = {"title": "Wide title 漢字 " * 20, "status": "Completed"}
            records = [dict(record, id=i) for i in range(47)]
            owner.records = lambda: records
            application._focus_run_records = owner.records
            selected = []
            owner.select = selected.append
            button = application.focus_run_overflow_button
            application._select_focus_view("forge")
            button.grid()
            application.focus_deck_header.grid()
            application.focus_force()
            application.update()
            assert button.winfo_ismapped()
            monkeypatch.setattr(button, "winfo_containing", lambda *_: button)
            button.event_generate("<Enter>")
            settle_native(application)
            assert owner.popup is not None
            menu = owner.menu
            popup = owner.popup
            assert (
                popup.winfo_rootx() + popup.winfo_width()
                <= application.winfo_rootx() + application.winfo_width()
            )
            assert (
                popup.winfo_rootx() + popup.winfo_width()
                == button.winfo_rootx() + button.winfo_width()
            )
            assert popup.winfo_rooty() + popup.winfo_height() == button.winfo_rooty()
            for item in menu.find_all():
                if menu.type(item) == "text":
                    assert menu.bbox(item)[2] <= menu.winfo_width()
            assert int(menu.cget("scrollregion").split()[-1]) == 47 * 31
            assert menu.bind("<MouseWheel>")
            if menu.tk.call("info", "commands", "tk::PreciseScrollDeltas"):
                assert menu.bind("<TouchpadScroll>")
            for _ in range(60):
                menu.event_generate("<MouseWheel>", delta=-120)
            assert menu.yview()[1] == 1.0
            menu.event_generate("<Motion>", x=20, y=menu.winfo_height() - 5)
            menu.event_generate("<Return>")
            application.update()
            assert selected == [records[-1]]
            assert owner.popup is None
            owner.show()
            application.update()
            assert owner.popup is not None
            views = []
            original = application._select_focus_view
            application._select_focus_view = lambda name: (
                views.append(name),
                original(name),
            )
            button.invoke()
            application.update()
            assert views == ["library"]
            assert owner.popup is None
        finally:
            application.destroy()


def test_settings_selects_every_quality_tier_in_real_dropdown():
    from scripts.focus_ui_preview import isolated_preview_services
    from yt_downloader.app import DownloaderApp, _quality_max_height
    from yt_downloader.export_planning import QUALITY_OPTIONS, choose_best_video_format

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    with isolated_preview_services():
        application = DownloaderApp()
        try:
            application._show_focus_settings()
            application.update()
            dropdown = next(
                widget
                for widget in descendants(application)
                if isinstance(widget, ChoiceDropdown)
                and tuple(widget.cget("values")) == tuple(QUALITY_OPTIONS)
            )
            for index, label in enumerate(QUALITY_OPTIONS):
                dropdown.open_popover()
                settle_native(application)
                listbox = dropdown._popover.winfo_children()[0]
                listbox.see(index)
                click_y = 6 + (index - listbox.top) * listbox.row_height + 17
                listbox.event_generate("<ButtonPress-1>", x=24, y=click_y)
                listbox.event_generate("<ButtonRelease-1>", x=24, y=click_y)
                application.update()
                assert dropdown.get() == label
                ceiling = _quality_max_height(dropdown.get())
                selected = choose_best_video_format(
                    [
                        {
                            "format_id": str(tier),
                            "format_note": f"{tier}p",
                            "height": tier,
                            "vcodec": "avc1",
                            "acodec": "none",
                            "tbr": 5000,
                        }
                        for tier in (360, 480, 720, 1080, 1440, 2160)
                    ],
                    max_height=ceiling,
                )
                assert selected["format_id"] == str(ceiling)
        finally:
            application.destroy()


def test_shared_choice_menu_navigation_hover_and_identical_render(root):
    root.geometry("600x400")
    root.deiconify()
    value = tk.StringVar(root, value="Choice 0")
    dropdown = ChoiceDropdown(
        root, textvariable=value, values=[f"Choice {i}" for i in range(12)]
    )
    dropdown.pack()
    root.update()
    dropdown.open_popover()
    root.update()
    menu = dropdown._popover.winfo_children()[0]
    assert isinstance(menu, ChoiceMenu)
    items = menu.find_all()
    menu.selection_set(0)
    assert menu.find_all() == items
    menu._move(11)
    assert menu.selected == 11 and menu.top == 4
    menu.event_generate("<Motion>", x=24, y=7)
    assert menu.selected == 4
    dropdown._commit_listbox(menu)
    assert value.get() == "Choice 4"
    assert dropdown._popover is None
    dropdown.configure(state="disabled")
    dropdown.open_popover()
    assert dropdown._popover is None


def assert_field_contour_focus(idle, active, restored):
    """Focus darkens the rounded face and rim, then restores exact idle pixels."""
    from PIL import ImageChops

    from yt_downloader.ui_theme import THEME

    width, height = idle.size
    assert active.size == restored.size == idle.size
    center = (width // 2, height // 2)
    for image, role in ((idle, "surface"), (active, "focus_surface")):
        expected = tuple(
            int(THEME[role][offset : offset + 2], 16) for offset in (1, 3, 5)
        )
        for x in range(center[0] - 2, center[0] + 3):
            for y in range(center[1] - 2, center[1] + 3):
                assert image.getpixel((x, y))[:3] == expected
    assert active.getpixel((1, center[1]))[:3] != active.getpixel(center)[:3]
    assert (
        ImageChops.difference(idle.convert("RGB"), restored.convert("RGB")).getbbox()
        is None
    )
    assert (
        ImageChops.difference(idle.getchannel("A"), restored.getchannel("A")).getbbox()
        is None
    )
    assert (
        ImageChops.difference(idle.getchannel("A"), active.getchannel("A")).getbbox()
        is None
    )


def test_shared_fields_show_contour_focus_and_restore_idle(root, monkeypatch):
    """1x fallback focus contour; faults cannot hide behind equal alpha."""
    monkeypatch.setattr("yt_downloader.ui_chrome.surface_backing_scale", lambda _: 1)
    from PIL import ImageDraw, ImageTk

    from yt_downloader.ui_chrome import RoundedFieldBorder

    root.deiconify()
    field = tk.Frame(root, width=220, height=40)
    field.pack()
    root.update()
    chrome = RoundedFieldBorder(field)
    chrome.request(False)
    size = (field.winfo_width(), field.winfo_height())
    idle = ImageTk.getimage(chrome._image).convert("RGBA")
    chrome.request(True)
    focused = ImageTk.getimage(chrome._image).convert("RGBA")
    assert (field.winfo_width(), field.winfo_height()) == size
    chrome.request(False)
    restored = ImageTk.getimage(chrome._image).convert("RGBA")

    def verify(active, after):
        assert_field_contour_focus(idle, active, after)

    verify(focused, restored)  # Actual antialiased native-image positive.
    faults = {"missing": (idle, restored), "stale": (focused, focused)}
    rectangle = focused.copy()
    ImageDraw.Draw(rectangle).rectangle((0, 0, 219, 39), outline="#ffffff", width=1)
    faults["rectangular"] = (rectangle, restored)
    face = focused.copy()
    # Preserve alpha exactly: RGBA.getbbox(alpha_only=True) would miss this.
    face.putpixel((110, 20), (255, 0, 0, face.getpixel((110, 20))[3]))
    faults["face-color"] = (face, restored)
    stale_color = restored.copy()
    stale_color.putpixel((110, 20), (255, 0, 0, stale_color.getpixel((110, 20))[3]))
    faults["restored-color"] = (focused, stale_color)
    for active, after in faults.values():
        with pytest.raises(AssertionError):
            verify(active, after)


@pytest.mark.parametrize("geometry", ["700x540", "820x720"])
def test_settings_pro_is_compact_visible_and_seen_only_when_shown(root, geometry):
    from yt_downloader.focus_settings import FocusSettingsDialog
    from yt_downloader.ui_widgets import ActionDialogSurface

    seen, clicked = [], []
    popup = tk.Toplevel(root)
    popup.withdraw()
    popup.geometry(geometry)
    dialog = FocusSettingsDialog.__new__(FocusSettingsDialog)
    dialog._closed = False
    dialog.actions = SimpleNamespace(
        record_cloud_cta_seen=lambda: seen.append(True),
        open_cloud_early_access=lambda: clicked.append(True),
    )
    dialog.dialog_surface = ActionDialogSurface(popup, allow_body_scroll=True)
    dialog._build_heading(dialog.dialog_surface.body)
    dialog._record_visible_pro()
    assert not seen
    popup.deiconify()
    root.update()
    dialog._record_visible_pro()
    assert seen == [True]
    button = dialog.pro_button
    assert button.cget("text") == "VODForge PRO"
    assert button.cget("image")
    assert dialog._pro_wordmark.width() > 80
    assert button.winfo_width() < 220
    button.invoke()
    assert clicked == [True]
    dialog._record_visible_pro()
    assert seen == [True]
    popup.destroy()


def test_activity_missing_icons_preserves_visible_tokens(root, monkeypatch):
    from yt_downloader import activity_ui

    monkeypatch.setattr(activity_ui, "_tinted_ui_icon", lambda *_args, **_kwargs: None)
    text = ActivityLogText(root)
    text.request("[success] Done\n[info] Ready")
    text.apply_theme()
    assert text.get("1.0", "end-1c") == "[success] Done\n[info] Ready"
    assert not text.tag_ranges("log-hidden")


def test_real_facts_keep_all_values_and_noop(root):
    text = FactsText(root)
    source = "\n".join(f"Fact {n}: exact value {n}" for n in range(80))
    assert text.request(source)
    assert text.raw_snapshot == source
    rendered = text.get("1.0", "end-1c")
    for n in range(80):
        assert f"Fact {n}\texact value {n}" in rendered
    before = text.get("1.0", "end")
    assert text.request(source) is False
    assert text.get("1.0", "end") == before
    assert str(text.cget("state")) == "disabled"


def test_facts_reflow_paths_and_long_labels_without_losing_copy_or_selection(root):
    root.deiconify()
    text = FactsText(root)
    text.pack(fill="both", expand=True)
    value = "/Users/example/Downloads/" + "a long folder name/" * 15
    raw = (
        "Output video codec: H.264\n"
        "Target audio bitrate: 192 kbps\n"
        "Output file path: " + value + "\n"
        "HDR/SDR or pixel format reported by this provider: SDR\n"
        "Unknown provider fact: Keep this exact value"
    )
    text.request(raw)
    for width in (650, 300, 650):
        root.geometry(f"{width}x400")
        settle_native(root)
        value_start = text.search(value[:30], "1.0", exact=True)
        text.see(value_start)
        settle_native(root)
        first = text.bbox(value_start)
        continuation = text.dlineinfo(f"{value_start} + 1 display lines")
        assert first is not None and continuation is not None
        assert first[0] > 10 and abs(first[0] - continuation[0]) <= 1
        assert text.raw_snapshot == raw
        rendered = text.get("1.0", "end-1c")
        assert value in rendered
        assert "Unknown provider fact" in rendered
        text.tag_add("sel", value_start, f"{value_start} + {len(value)} chars")
    root.geometry("300x400")
    settle_native(root)
    assert text.get("sel.first", "sel.last") == value
    text.yview_moveto(0)
    settle_native(root)
    for label, fact in (
        ("Output video codec", "H.264"),
        ("Target audio bitrate", "192 kbps"),
    ):
        label_box = text.bbox(text.search(label, "1.0", exact=True))
        value_box = text.bbox(text.search(fact, "1.0", exact=True))
        assert label_box and value_box and label_box[1] == value_box[1]
    label = text.search("HDR/SDR or pixel format", "1.0", exact=True)
    val = text.search("SDR", f"{label} lineend", exact=True)
    text.see(val)
    settle_native(root)
    label_box, val_box = text.bbox(label), text.bbox(val)
    assert label_box and val_box
    assert val_box[0] > label_box[0] + 20 and val_box[1] >= label_box[1]


def test_log_decoration_is_character_exact_and_clear_invalidates(root):
    text = ActivityLogText(root)
    source = "09:12:30  [info] unicode →\n09:12:31 [warning] C:\\a path\\b\n"
    text.request(source)
    assert text.get("1.0", "end-1c") == source
    text.configure(state="normal")
    text.delete("1.0", "end")
    assert text.request(source)
    assert text.get("1.0", "end-1c") == source
    text.configure(state="normal")
    text.insert("end", "09:12:32 [error] appended")
    assert text.get("1.0", "end-1c") == source + "09:12:32 [error] appended"


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize(
    "severity,color", [("warning", "warning"), ("error", "danger")]
)
def test_severity_spellings_share_visible_layout_and_lossless_source(
    root, compact, severity, color
):
    root.deiconify()
    text = ActivityLogText(root, compact=compact)
    text.pack()
    text.configure(width=36)
    body = (
        "A long diagnostic message with enough words to wrap onto another display line."
    )
    source = f"[{severity}] {body}\n{severity.upper()}: {body}\n"
    text.insert("end", source)
    settle_native(root)
    assert text.get("1.0", "end-1c") == source
    assert len(text.image_names()) == 4
    labels = [child for child in text.winfo_children() if isinstance(child, tk.Label)]
    assert [label.cget("text") for label in labels] == [severity.upper() + ": "] * 2
    assert all(label.cget("fg") == THEME[color] for label in labels)
    assert labels[0].winfo_x() == labels[1].winfo_x()
    indents = [
        {tag for tag in text.tag_names(f"{line}.0") if tag.startswith("log-indent-")}
        for line in (1, 2)
    ]
    assert indents[0] and indents[0] == indents[1]
    text.apply_theme()
    assert all(label.cget("fg") == THEME[color] for label in labels)
    text.delete("1.0", "end")
    assert not text.winfo_children()


@pytest.mark.parametrize("compact", [False, True])
def test_real_pipeline_activity_is_decorated_losslessly(root, compact):
    text = ActivityLogText(root, compact=compact)
    lines = [
        "Video 1 of 1: downloading\n",
        "WARNING: Target bitrate is close to the selected source.\n",
        "Video 1 of 1: FFmpeg command started (1/1) using CPU libx264\n",
        "ERROR: Encoder failed\n",
        "[success] MP4 download complete\n",
    ]
    for line in lines:
        text.insert("end", line)
    source = "".join(lines)
    assert text.get("1.0", "end-1c") == source
    assert len(text.image_names()) == 10  # Every marker uses the same gutter.
    assert text.tag_ranges("log-warning")
    assert text.tag_ranges("log-error")
    text.request(source)
    images = text.image_names()
    assert not text.request(source)
    text.apply_theme()
    assert text.image_names() == images
    assert text.get("1.0", "end-1c") == source


def test_log_fragment_does_not_create_an_extra_event(root):
    text = ActivityLogText(root)
    text.insert("end", "Video 1:")
    images = text.image_names()
    text.insert("end", " downloading")
    assert text.image_names() == images
    assert text.get("1.0", "end-1c") == "Video 1: downloading"


@pytest.mark.parametrize("compact", [False, True])
def test_activity_wrapping_and_success_share_message_column(root, compact):
    root.deiconify()
    root.geometry("420x420")
    text = ActivityLogText(root, compact=compact, wrap="word")
    text.pack(fill="both", expand=True)
    source = "Video saved " + "long path segment " * 8 + "\n[success] Completed\n"
    text.request(source)
    root.update()
    start = text.search("Video", "1.0")
    # display linestart must be requested explicitly, not logical linestart.
    continuation = text.index(f"{start} +1 display lines display linestart")
    done = text.search("Completed", "1.0")
    assert text.bbox(start)[0] == text.bbox(continuation)[0] == text.bbox(done)[0]
    icons = [
        name
        for name in text.image_names()
        if text.image_cget(name, "image") != str(text._divider)
    ]
    assert len(icons) == 2
    assert text.bbox(icons[0])[0] == text.bbox(icons[1])[0]
    assert text.get("1.0", "end-1c") == source


@pytest.mark.parametrize("compact", [False, True])
def test_warning_error_dividers_icons_and_wrapped_lines_align_with_normal_events(
    root, compact
):
    root.deiconify()
    root.geometry("460x620")
    text = ActivityLogText(root, compact=compact, wrap="word")
    text.pack(fill="both", expand=True)
    body = "A diagnostic message " * 6
    source = f"Ordinary event\n[warning] {body}\nERROR: {body}\n"
    text.insert("end", source)
    settle_native(root)
    message_x = text.bbox(text.search("Ordinary", "1.0"))[0]
    labels = [child for child in text.winfo_children() if isinstance(child, tk.Label)]
    for label in labels:
        assert text.bbox(str(label))[0] == message_x
        continuation = text.index(f"{label!s} +1 display lines display linestart")
        assert text.bbox(continuation)[0] == message_x
    for divider in (True, False):
        names = [
            name
            for name in text.image_names()
            if (text.image_cget(name, "image") == str(text._divider)) == divider
        ]
        assert len(names) == 3
        assert len({text.bbox(name)[0] for name in names}) == 1


def test_appended_event_after_snapshot_starts_a_new_line(root):
    from yt_downloader.app import DownloaderApp

    text = ActivityLogText(root)
    text.request("Video 1: downloading")
    DownloaderApp._append_log_widget(text, "Video 1: transcoding")
    DownloaderApp._append_log_widget(text, "Video 1: validating")
    assert text.get("1.0", "end-1c") == (
        "Video 1: downloading\nVideo 1: transcoding\nVideo 1: validating\n"
    )
    assert len(text.image_names()) == 6


@pytest.mark.parametrize("compact", [False, True])
def test_activity_theme_refresh_retains_document_and_noop(root, compact):
    from yt_downloader.ui_theme import THEME

    text = ActivityLogText(root, compact=compact)
    source = (
        "09:12:30 [info] Started\n09:12:31 [warning] Warning\n09:12:32 [error] Error"
    )
    text.request(source)
    original = THEME["accent"]
    try:
        THEME["accent"] = "#35aabb"
        text.apply_theme()
        assert text.tag_cget("log-level", "foreground") == "#35aabb"
        assert text.tag_cget("log-warning", "foreground") == THEME["warning"]
        assert text.tag_cget("log-error", "foreground") == THEME["danger"]
        assert text.get("1.0", "end-1c") == source
        assert text.request(source) is False
    finally:
        THEME["accent"] = original


def test_explicit_terminal_activity_and_summary(root):
    assert (
        terminal_activity_line("Failed", "Saved something earlier")
        == "[error] Saved something earlier"
    )
    assert terminal_activity_line("Completed", "Finished") == "[success] Finished"
    text = ActivityLogText(root)
    source = "14:30:08 [success] Finished\n14:30:09 [error] Failed"
    text.request(source)
    text.apply_theme()
    assert text.get("1.0", "end-1c") == source
    assert any(
        text.image_cget(name, "image") == str(text._success_icon)
        for name in text.image_names()
    )
    summary = ActivitySummary(root)
    assert summary.request(title="Run A", status="Completed", detail="Finished")
    assert not summary.request(title="Run A", status="Completed", detail="Finished")
    assert summary._status.get() == "Completed"
    assert summary.request(title="Run B", status="Failed", detail="Failure")
    assert summary._title.get() == "Run B"


def test_input_semantics_and_one_interpreter_chrome_cache(root):
    value = tk.StringVar(root, "initial")
    entry = ProductEntry(root, textvariable=value)
    entry.delete(0, "end")
    entry.insert(0, "edited")
    assert value.get() == "edited"
    entry.configure(state="readonly")
    entry.insert(0, "ignored")
    assert value.get() == "edited"
    style = ttk.Style(root)
    owner = root._product_chrome_owner
    images = tuple(str(image) for image in owner.images.values())
    owner.request(style)
    assert tuple(str(image) for image in owner.images.values()) == images
    dropdown = ChoiceDropdown(root, textvariable=value, values=("edited", "second"))
    value.set("second")
    assert dropdown.get() == "second"


def test_segmented_control_retains_bindings_and_noops(root):
    value = tk.StringVar(root, "MP4")
    selector = SegmentedSelector(root, variable=value)
    images = dict(selector._segment_images)
    selector._sync()
    assert selector._segment_images == images
    selector._select_from_event("MP3", None)
    assert value.get() == "MP3"
    assert selector._segment_images != images
    selected_images = dict(selector._segment_images)
    selector._sync()
    assert selector._segment_images == selected_images
    assert all(label.cget("takefocus") for label in selector.tooltip_targets())


def test_output_document_scrolls_without_moving_done(root):
    root.deiconify()
    settle_native(root)
    dialog = OutputDetailsDialog(
        root,
        sections=(
            (
                "Final output",
                "\n".join(f"Field {n}: " + "long value " * 12 for n in range(60)),
            ),
        ),
    )
    dialog.popup.geometry("460x320")
    settle_native(dialog.popup)
    document = dialog.documents[0]
    assert "Field 59" in document.raw_snapshot
    document.yview_moveto(1.0)
    assert document.yview()[1] == 1.0

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    done = next(
        w
        for w in descendants(dialog.popup)
        if isinstance(w, ttk.Button) and w.cget("text") == "Done"
    )
    assert done.winfo_rooty() >= dialog.popup.winfo_rooty()
    assert (
        done.winfo_rooty() + done.winfo_height()
        <= dialog.popup.winfo_rooty() + dialog.popup.winfo_height()
    )
    dialog.popup.destroy()


@pytest.mark.parametrize("content", ["Codec: H.264", "Codec: H.264\n"])
def test_details_section_tags_do_not_drift_into_facts(root, content):
    dialog = OutputDetailsDialog(
        root, sections=(("Requested output", content), ("Final output", "Codec: AAC"))
    )
    document = dialog.documents[0]
    ranges = document.tag_ranges("section")
    assert [document.get(ranges[n], ranges[n + 1]) for n in (0, 2)] == [
        "Requested output",
        "Final output",
    ]
    dialog.popup.destroy()


@pytest.mark.parametrize("size", ["1100x786", "980x690"])
def test_player_content_cannot_starve_stage_or_clip_previews(root, size):
    from PIL import Image, ImageTk

    from scripts.focus_ui_preview import PreviewMediaOwner, PreviewPlaybackBackend
    from yt_downloader.media_player_ui import MediaPlayerWindow, apply_preview_image

    player = MediaPlayerWindow(
        root,
        playback=PreviewPlaybackBackend(audio_only=False),
        previews=PreviewMediaOwner(),
        info={
            "title": "A saved film",
            "vodforge_user_note": "A note " * 300,
            "chapters": [
                {
                    "start_time": n * 10,
                    "end_time": (n + 1) * 10,
                    "title": f"Chapter {n}",
                }
                for n in range(10)
            ],
        },
    )
    player.popup.geometry(size)
    player.popup.deiconify()
    image = ImageTk.PhotoImage(Image.new("RGB", (132, 74), "#121419"), master=root)
    for label in player.preview_labels:
        apply_preview_image(label, image)
    settle_native(player.popup)
    assert player.stage.winfo_width() >= player.popup.winfo_width() * 0.60
    bottom = player.popup.winfo_rooty() + player.popup.winfo_height()
    for label in player.preview_labels:
        assert label.winfo_height() >= 74
        assert label.winfo_rooty() + label.winfo_height() + 18 <= bottom
    player.close()


def test_dropdown_keeps_arrow_under_width_pressure(root):
    root.geometry("180x90")
    root.deiconify()
    value = tk.StringVar(root, "A very long selected option")
    dropdown = ChoiceDropdown(root, textvariable=value, values=(value.get(),), width=40)
    dropdown.pack(fill="x")
    settle_native(root)
    assert dropdown._chevron.winfo_ismapped()
    assert (
        dropdown._chevron.winfo_x() + dropdown._chevron.winfo_width()
        <= dropdown.winfo_width()
    )


def test_analytics_prompt_actions_fit_without_scroll(root, tmp_path):
    from yt_downloader.analytics_consent import AnalyticsConsentOwner
    from yt_downloader.analytics_startup import AnalyticsStartup

    startup = AnalyticsStartup(
        root, AnalyticsConsentOwner(tmp_path), tk.BooleanVar(root), lambda _: None
    )
    root.geometry("1180x780")
    root.deiconify()
    root.update()
    startup._prompt()
    popup = startup.permission_panel.frame
    root.update()
    buttons = startup.permission_panel.controls
    assert {str(w.cget("text")) for w in buttons} == {
        "Not now",
        "Share analytics",
        "Privacy details",
    }
    for button in buttons:
        assert button.winfo_ismapped()
        assert button.winfo_rooty() >= popup.winfo_rooty()
        assert (
            button.winfo_rooty() + button.winfo_height()
            <= popup.winfo_rooty() + popup.winfo_height()
        )
    startup.close()
    startup.permission_panel.finish(False)


def test_task_presets_use_real_dropdown_and_custom_quality_controls():
    from scripts.focus_ui_preview import isolated_preview_services
    from yt_downloader.app import DownloaderApp
    from yt_downloader.export_planning import (
        EXPORT_MODES,
        export_mode_from_display_name,
    )

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    with isolated_preview_services():
        application = DownloaderApp()
        try:
            assert application.export_mode_choice_var.get() == "Everyday"
            application._show_focus_settings()
            settle_native(application)
            dialog = application._focus_settings_dialog
            dropdown = next(
                w
                for w in descendants(application)
                if isinstance(w, ChoiceDropdown)
                and tuple(w.cget("values")) == tuple(EXPORT_MODES)
            )
            # Return from Custom too: its expanded fields must not push the
            # preset anchor outside the scrolling Settings viewport.
            for label in (*EXPORT_MODES, EXPORT_MODES[0]):
                index = EXPORT_MODES.index(label)
                dropdown.open_popover()
                settle_native(application)
                assert dropdown._popover is not None, label
                choices = dropdown._popover.winfo_children()[0]
                choices.see(index)
                y = 6 + (index - choices.top) * choices.row_height + 17
                choices.event_generate("<ButtonPress-1>", x=24, y=y)
                choices.event_generate("<ButtonRelease-1>", x=24, y=y)
                settle_native(application)
                assert (
                    application.export_mode_var.get()
                    == export_mode_from_display_name(label).value
                )
                assert application.export_mode_description_var.get()
                assert bool(dialog.manual_frame.winfo_ismapped()) == (label == "Custom")
            application.export_mode_choice_var.set("Custom")
            settle_native(application)
            application.manual_rate_control_var.set("Quality")
            application.manual_crf_var.set("19")
            application.manual_video_bitrate_var.set("unused value")
            settle_native(application)
            assert str(dialog._custom_rate_widgets["CBR"].cget("state")) == "disabled"
            assert application._manual_export_settings().video_crf == 19
            application.manual_video_bitrate_var.set("7000")
            application.manual_rate_control_var.set("CBR")
            assert application._manual_export_settings().video_bitrate_kbps == 7000
            assert application._manual_export_settings().video_crf is None
            dialog.close()
            # Closing removes the dialog-owned trace; preference remains usable.
            application.manual_rate_control_var.set("Quality")
            application._show_focus_settings()
            settle_native(application)
            assert application.manual_crf_var.get() == "19"
            dialog = application._focus_settings_dialog
            dialog.popup.geometry("820x720")
            settle_native(application)
            dropdown = next(
                w
                for w in descendants(dialog.popup)
                if isinstance(w, ChoiceDropdown)
                and tuple(w.cget("values")) == tuple(EXPORT_MODES)
            )
            dropdown.open_popover()
            settle_native(application)
            assert dropdown._popover is not None, "Reopened Custom preset menu"
            choices = dropdown._popover.winfo_children()[0]
            choices.see(0)
            choices.event_generate("<ButtonPress-1>", x=24, y=23)
            choices.event_generate("<ButtonRelease-1>", x=24, y=23)
            settle_native(application)
            assert application.export_mode_choice_var.get() == EXPORT_MODES[0]
            assert not dialog.manual_frame.winfo_ismapped()
        finally:
            application.destroy()


@pytest.mark.parametrize("size", ["1180x780", "820x560"])
def test_composer_format_menu_opens_and_selects_every_format(size, monkeypatch):
    from scripts.focus_ui_preview import isolated_preview_services
    from yt_downloader.analytics_startup import AnalyticsStartup
    from yt_downloader.app import DownloaderApp
    from yt_downloader.engagement_ui import EngagementUI
    from yt_downloader.models import OutputType

    # This is an existing-user composer journey, without first-launch modals.
    monkeypatch.setattr(AnalyticsStartup, "start", lambda self: None)
    monkeypatch.setattr(EngagementUI, "start", lambda self: None)
    with isolated_preview_services():
        application = DownloaderApp()
        try:
            application.geometry(size)
            settle_native(application)
            dropdown = application.focus_output_type_selector
            for kind in OutputType:
                application.focus_url_entry.focus_force()
                settle_native(application)
                dropdown._field.event_generate("<ButtonPress-1>", x=4, y=4)
                dropdown._field.event_generate("<ButtonRelease-1>", x=4, y=4)
                settle_native(application)
                assert dropdown._popover is not None, kind
                assert dropdown._popover.winfo_ismapped()
                menu = dropdown._popover.winfo_children()[0]
                menu.selection_set(dropdown._values.index(kind.value))
                menu.event_generate("<Return>")
                settle_native(application)
                assert application.output_type_var.get() == kind.value
                assert dropdown._popover is None
        finally:
            application.destroy()


def test_update_recovery_exposes_cause_and_keeps_repair_visible(root):
    from yt_downloader.update_recovery import show_update_recovery

    checks = []
    root.geometry("1000x720")
    root.deiconify()
    root.update()

    def inspect():
        popup = root.nametowidget(".update_recovery")

        def walk(widget):
            return [widget] + [
                item for child in widget.winfo_children() for item in walk(child)
            ]

        widgets = walk(popup)
        buttons = {
            str(w.cget("text")): w for w in widgets if w.winfo_class() == "TButton"
        }
        detail = next(w for w in widgets if isinstance(w, tk.Text))
        checks.append(not bool(detail.winfo_manager()))
        buttons["Technical details"].invoke()
        popup.update_idletasks()
        checks.append(bool(detail.winfo_manager()))
        checks.append(
            abs(popup.winfo_x() + popup.winfo_width() / 2 - root.winfo_width() / 2) <= 1
        )
        checks.append(
            abs(popup.winfo_y() + popup.winfo_height() / 2 - root.winfo_height() / 2)
            <= 1
        )
        checks.append("precise failure cause" in detail.get("1.0", "end"))
        checks.append(
            all(
                w.winfo_rooty() + w.winfo_height()
                <= popup.winfo_rooty() + popup.winfo_height()
                for w in buttons.values()
            )
        )
        buttons["Repair VODForge"].invoke()

    root.after(150, inspect)
    show_update_recovery(root, "precise failure cause", lambda: checks.append(True))
    assert checks == [True] * 7


def test_player_overlay_corners_match_poster_and_native_input(root):
    from PIL import Image, ImageTk

    from yt_downloader.media_player_ui import MediaPlayerWindow

    player = object.__new__(MediaPlayerWindow)
    player.popup = root
    player.embedded = False
    player.thumbnail_path = None
    player._poster_image = None
    player._audio_only = False
    player._closed = False
    player._source_image = None
    player._stage_render_after_id = None
    player._stage_render_signature = None
    calls = []
    player._toggle = lambda: calls.append(True)
    frame = ttk.Frame(root)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(1, weight=1)
    player._build_stage(frame)
    root.deiconify()
    for size in ("700x440", "950x600", "700x440"):
        root.geometry(size)
        settle_native(root)
        player._source_image = Image.new("RGB", (1000, 700), "#d03a98")
        player._stage_render_signature = None
        player._commit_stage_render()
        settle_native(root)
        button = player.play_overlay
        # The complete ttk element must own the corners, not transparent image
        # pixels exposing the stage shell's solid backing.
        images = getattr(button, "_backgrounds", [])
        assert len(images) == 2, "Overlay still uses transparent generic button chrome"
        for photo in images:
            pixels = ImageTk.getimage(photo)
            assert pixels.getpixel((0, 0))[:3] == (208, 58, 152)
            assert (button.winfo_width(), button.winfo_height()) == pixels.size
        button.invoke()
        button.focus_force()
        settle_native(root)
        button.event_generate("<KeyPress-space>")
        button.event_generate("<KeyRelease-space>")
        settle_native(root)
    assert len(calls) == 6


def test_library_description_stays_inside_inspector_after_resize(tmp_path):
    from scripts.focus_ui_preview import isolated_preview_services
    from tests.test_archive_models import saved
    from yt_downloader.app import DownloaderApp

    with isolated_preview_services():
        app = DownloaderApp()
        try:
            description = (
                "Description sentinel first\n"
                + "Middle description line\n" * 100
                + "Description sentinel last"
            )
            app.download_history = [
                {
                    **saved(tmp_path / "layout.mp4", video="layout"),
                    "title": "A long selected title " * 8,
                    "description": description,
                    "tags": ["tag"] * 20,
                }
            ]
            app._reconcile_library_projection()
            app._select_focus_view("library")
            scene = app.library_scene
            scene.show_details(0)
            for size in ("1320x820", "1100x600", "1440x900"):
                app.geometry(size)
                settle_native(app)
                details = scene._description_section
                body = details.text
                window = next(
                    item
                    for item in scene.canvas.find_all()
                    if scene.canvas.type(item) == "window"
                    and scene.canvas.itemcget(item, "window") == str(details)
                )
                region = tuple(
                    float(v) for v in scene.canvas.cget("scrollregion").split()
                )
                scene.canvas.yview_moveto(
                    max(0, scene.canvas.bbox(window)[1] - 20) / region[3]
                )
                settle_native(app)
                assert body.winfo_ismapped()
                assert body.winfo_height() > 100
                assert body.winfo_rooty() >= details.winfo_rooty()
                assert body.winfo_rooty() + body.winfo_height() <= (
                    details.winfo_rooty() + details.winfo_height()
                )
                assert body.winfo_rootx() + body.winfo_width() <= (
                    details.winfo_rootx() + details.winfo_width()
                )
                assert body.get("1.0", "end").strip() == description
                body.see("end")
                settle_native(app)
                assert body.yview()[1] == 1.0
                last_line = body.dlineinfo("end-1c linestart")
                assert last_line is not None
                assert 0 <= last_line[1]
                assert last_line[1] + last_line[3] <= body.winfo_height()
        finally:
            app.destroy()


def test_feature_callbacks_report_actions_without_widget_contents(monkeypatch):
    from scripts.focus_ui_preview import isolated_preview_services
    from yt_downloader.app import DownloaderApp

    calls = []
    with isolated_preview_services():
        application = DownloaderApp()
        try:
            application.product_telemetry = SimpleNamespace(
                record_feature=lambda feature, action, **fields: calls.append(
                    (feature, action, fields)
                ),
                shutdown=lambda *_args: True,
                set_enabled=lambda *_args: None,
                record_app_opened=lambda: None,
            )
            application._select_focus_view("library")
            application.library_search_var.set("PRIVATE SEARCH MUST NOT LEAVE")
            application.library_category_var.set("PRIVATE CATEGORY")
            application.forge_activity.set_technical(True)
            application.forge_activity.set_technical(False)
            application.forge_activity.set_technical(True)
            settle_native(application)
            observed = {(feature, action) for feature, action, _ in calls}
            assert {
                ("library", "opened"),
                ("library", "searched"),
                ("library", "filtered"),
                ("guidance", "technical_opened"),
            } <= observed
            assert "PRIVATE" not in repr(calls)
        finally:
            application.destroy()


def test_primary_views_allocate_only_current_surface_and_restore_latest_layout(
    monkeypatch,
):
    from scripts.focus_ui_preview import approved_metadata, isolated_preview_services
    from yt_downloader.app import DownloaderApp

    with isolated_preview_services():
        application = DownloaderApp()
        try:
            application.metadata_items = approved_metadata()
            application._render_metadata_tree(selected_index=0)
            for name, size in [
                ("library", "1180x780"),
                ("activity", "820x560"),
                ("forge", "1180x780"),
                ("library", "820x560"),
                ("forge", "820x560"),
                ("library", "1180x780"),
            ]:
                application._select_focus_view(name)
                application.geometry(size)
                settle_native(application)
                assert [
                    key
                    for key, frame in application._focus_views.items()
                    if frame.winfo_ismapped()
                ] == [name]
                active = application._focus_views[name]
                assert active.winfo_width() > 700
                assert active.winfo_height() > 400
                assert application.winfo_width() == int(size.split("x")[0])
            calls = []
            monkeypatch.setattr(
                application, "_focus_run_records", lambda: calls.append(True) or []
            )
            application._refresh_focus_run_deck()
            assert calls == []
            application._select_focus_view("forge")
            settle_native(application)
            assert calls
            assert application.focus_run_deck.winfo_ismapped()
            hidden_library_layouts = []
            original_layout = application._apply_archive_layout

            def count_library_layout(*args):
                hidden_library_layouts.append(args)
                return original_layout(*args)

            monkeypatch.setattr(
                application, "_apply_archive_layout", count_library_layout
            )
            application.geometry("1180x780")
            settle_native(application)
            application.geometry("1100x740")
            settle_native(application)
            assert hidden_library_layouts == []
            application._select_focus_view("library")
            settle_native(application)
            assert hidden_library_layouts
        finally:
            application.destroy()


@pytest.mark.parametrize("row_count", [0, 25, 5000])
def test_forge_geometry_reuses_projection_and_reentry_observes_history_changes(
    monkeypatch, row_count
):
    from scripts.focus_ui_preview import approved_metadata, isolated_preview_services
    from yt_downloader.app import DownloaderApp
    from yt_downloader.ui_layout import focus_run_deck_capacity

    with isolated_preview_services():
        application = DownloaderApp()
        try:
            base = approved_metadata()
            application.metadata_items = [
                {
                    **base[i % len(base)],
                    "id": f"geometry-{i}",
                    "title": f"Geometry record {i}",
                    "vodforge_projection_owner": f"preview:geometry:{i}",
                    "vodforge_annotation_owner": f"preview:geometry:{i}",
                }
                for i in range(row_count)
            ]
            application._render_metadata_tree(selected_index=0 if row_count else None)
            application._select_focus_view("forge")
            settle_native(application)
            original_projection = application._focus_run_records
            projections = []

            def project():
                projections.append(True)
                return original_projection()

            monkeypatch.setattr(application, "_focus_run_records", project)
            for size in ("820x560", "1180x780", "1440x900", "820x560"):
                application.geometry(size)
                settle_native(application)
                deck = application.focus_run_deck
                assert deck.winfo_ismapped()
                assert (
                    application._focus_run_deck_rendered_capacity
                    == focus_run_deck_capacity(deck.winfo_width())
                )
                assert deck.winfo_rootx() + deck.winfo_width() <= (
                    application.winfo_rootx() + application.winfo_width()
                )
            assert projections == []

            # Mutate the same history list while Forge is hidden. Forced entry
            # must reacquire data, including removal-to-empty and replacement.
            application._select_focus_view("library")
            changed = {**base[0], "title": "Changed while hidden"}
            application.metadata_items[:] = [changed]
            application._refresh_focus_run_deck()
            assert projections == []
            application._select_focus_view("forge")
            settle_native(application)
            assert projections
            snapshot = application._focus_run_deck_signature
            assert any(
                tile.structure[3] == "Changed while hidden" for tile in snapshot.tiles
            )

            def visible_text(widget):
                texts = []
                try:
                    texts.append(str(widget.cget("text")))
                except tk.TclError:
                    pass
                for child in widget.winfo_children():
                    texts.extend(visible_text(child))
                return texts

            assert "Changed while hidden" in visible_text(application.focus_run_deck)
            application.metadata_items.clear()
            application._refresh_focus_run_deck()
            settle_native(application)
            assert "Your runs will collect here" in visible_text(
                application.focus_run_deck
            )
        finally:
            application.destroy()


def test_thumbnail_configure_after_sibling_removal_and_native_close():
    from scripts.focus_ui_preview import isolated_preview_services
    from yt_downloader.app import DownloaderApp

    errors = []
    with isolated_preview_services():
        application = DownloaderApp()
        application.report_callback_exception = lambda *items: errors.append(items)
        try:
            application.geometry("1180x780")
            settle_native(application)
            # Reproduce the actual destroyed sibling condition seen during
            # recursive Tk shutdown, while its Configure-bound peer is alive.
            application.focus_active_thumbnail_label.destroy()
            application.focus_thumbnail_wrap.event_generate(
                "<Configure>", width=210, height=118
            )
            application._request_application_close()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    if not application.winfo_exists():
                        break
                    application.update()
                except tk.TclError:
                    break
                time.sleep(0.01)
            else:
                pytest.fail("native close did not finish")
            assert errors == []
        finally:
            try:
                if application.winfo_exists():
                    application.destroy()
            except tk.TclError:
                pass


@pytest.mark.parametrize("output_type", ["MP4", "MP3", "Original audio"])
def test_forge_destination_stays_single_across_resizes_and_path_changes(output_type):
    from scripts.focus_ui_preview import isolated_preview_services
    from yt_downloader.app import DownloaderApp
    from yt_downloader.detail_ui import detail_lines

    paths = (
        "/Volumes/An external archive/Projects/Finished films",
        r"C:\\Media archive\\Projects\\A new destination",
        "/Volumes/旅行記/完成した動画",
    )
    with isolated_preview_services():
        application = DownloaderApp()
        try:
            application.output_type_var.set(output_type)
            application._select_focus_view("forge")
            application.deiconify()
            document = application.focus_summary_text
            for path in paths:
                application.output_var.set(path)
                for size in ("1100x600", "1440x900", "1180x700", "1280x780") * 2:
                    application.geometry(size)
                    settle_native(application)
                    application._sync_focus_destination()
                    application.update_idletasks()
                    raw = document.raw_snapshot
                    rendered = document.get("1.0", "end-1c")
                    facts = detail_lines(raw)
                    destinations = [line for line in facts if line.label == "Save to"]
                    assert len(destinations) == 1
                    assert destinations[0].value == path
                    assert raw.count(path) == rendered.count(path) == 1
                    assert all(
                        old not in raw and old not in rendered
                        for old in paths
                        if old != path
                    )
                    assert all(line.label for line in facts)
                    mode = next(line for line in facts if line.label == "Output mode")
                    assert path not in mode.value
                    if document.winfo_ismapped():
                        assert document.dlineinfo("1.0") is not None
                    else:
                        assert application.focus_details_button.winfo_ismapped()
        finally:
            application.destroy()


@pytest.mark.parametrize(
    "label,width,variant,icon",
    [
        ("Update location", 174, "inline", "folder"),
        ("Update location", 148, "default", "folder"),
        ("Back to suggestions", 180, "default", "back"),
        ("View in Library", 181, "default", "folder"),
        ("Show in Folder", 184, "default", "folder"),
        ("Go to Forge", 217, "default", "download"),
        ("Sort: Recently Added", 205, "compact", "sort"),
    ],
)
def test_fixed_scene_action_labels_fit_without_user_content_ellipsis(
    root, label, width, variant, icon
):
    from tkinter import font as tkfont

    from yt_downloader.scene_components import ScenePainter
    from yt_downloader.ui_button_contract import button_metrics
    from yt_downloader.ui_layout import ellipsize_wrapped_text

    height = button_metrics(variant).height
    canvas = tk.Canvas(root, width=width + 40, height=height + 40)
    canvas.pack()
    fonts = {}

    def fit(value, maximum_width, maximum_lines, font):
        key = tuple(font)
        if key not in fonts:
            fonts[key] = tkfont.Font(root=root, font=font)
        return ellipsize_wrapped_text(
            str(value)[:2000],
            maximum_width=max(1, maximum_width),
            maximum_lines=maximum_lines,
            measure_width=fonts[key].measure,
        )

    # Preserve the real user-content fitting contract so the same fixture
    # demonstrates label truncation on the previous ScenePainter.
    view = SimpleNamespace(
        canvas=canvas, _button_images=[], _button_labels=[], _targets=[], _fit=fit
    )
    ScenePainter(view).button(
        20, 20, width, label, lambda: None, icon=icon, variant=variant
    )
    settle_native(root)
    bounds, item, _color, _active = view._button_labels[0]
    assert canvas.itemcget(item, "text") == label
    text_bounds = canvas.bbox(item)
    assert text_bounds is not None
    assert bounds[0] + 38 <= text_bounds[0] < text_bounds[2] <= bounds[2] - 8
    assert bounds[1] <= text_bounds[1] < text_bounds[3] <= bounds[3]


def test_shared_header_initial_map_and_responsive_controls():
    from unittest.mock import patch

    from scripts.focus_ui_preview import isolated_preview_services
    from yt_downloader.analytics_startup import AnalyticsStartup
    from yt_downloader.app import DownloaderApp
    from yt_downloader.engagement_ui import EngagementUI

    with (
        isolated_preview_services(),
        patch.object(AnalyticsStartup, "start", lambda _: None),
        patch.object(EngagementUI, "start", lambda _: None),
    ):
        application = DownloaderApp()
        try:
            # Set geometry before the first map: Aqua previously delivered a
            # stale1x1 Configure after this actual1414px window was visible.
            application.geometry("1414x800+40+40")
            application._select_focus_view("watch")
            application.deiconify()
            settle_native(application)
            assert application.winfo_width() == 1414
            assert not application._focus_header_compact
            for width in (1414, 980, 820, 1414):
                application.geometry(f"{width}x800+40+40")
                settle_native(application)
                widgets = [
                    *application._focus_nav_buttons.values(),
                    application._global_search_field,
                    application.focus_settings_button,
                ]
                right = application.winfo_rootx() + application.winfo_width()
                previous = application.winfo_rootx()
                for widget in widgets:
                    assert widget.winfo_ismapped()
                    assert widget.winfo_rootx() >= previous
                    previous = widget.winfo_rootx() + widget.winfo_width()
                    assert previous <= right
                expected = width < (1100 if application._integrated_header else 1000)
                assert application._focus_header_compact == expected
                assert all(
                    bool(label.winfo_ismapped()) != expected
                    for label in application._focus_brand_labels
                )
        finally:
            application.destroy()


@pytest.mark.parametrize("theme", ["Jade", "Ember"])
@pytest.mark.parametrize("role", ["selection", "progress", "action-icon"])
def test_shared_foreground_roles_are_independent_of_material_hue(root, theme, role):
    from yt_downloader.ui_theme import apply_theme_selection

    previous = dict(THEME)
    try:
        apply_theme_selection(theme)
        apply_product_styles(root)
        style = ttk.Style(root)
        if role == "selection":
            assert (
                style.lookup("Archive.TNotebook.Tab", "foreground", ("selected",))
                == THEME["selection"]
            )
        elif role == "progress":
            for name in (
                "TProgressbar",
                "FocusProgress.Horizontal.TProgressbar",
                "FocusDeck.Horizontal.TProgressbar",
            ):
                assert style.lookup(name, "background") == THEME["progress"]
        else:
            assert style.lookup("TCombobox", "arrowcolor") == THEME["icon"]
    finally:
        THEME.clear()
        THEME.update(previous)


@pytest.mark.parametrize(
    "sequence, supported",
    [("<MouseWheel>", True), ("<VODForgeUnsupportedEvent>", False)],
)
def test_optional_event_probe_parses_without_registering_callback_or_input(
    root, sequence, supported
):
    from yt_downloader.platform_services import supports_tk_event

    commands = tuple(root._tclCommands)
    tags = root.bindtags()
    assert supports_tk_event(root, sequence) is supported
    assert tuple(root._tclCommands) == commands
    assert root.bindtags() == tags


def test_optional_event_probe_preserves_preexisting_tag(root, monkeypatch):
    import uuid

    from yt_downloader.platform_services import supports_tk_event

    tag = "VODForgeEventProbe-reserved-by-another-owner"
    monkeypatch.setattr(
        uuid, "uuid4", lambda: SimpleNamespace(hex="reserved-by-another-owner")
    )
    root.tk.call("bind", tag, "<MouseWheel>", "break")
    before = root.tk.call("bind", tag, "<MouseWheel>")
    commands = tuple(root._tclCommands)
    try:
        assert supports_tk_event(root, "<MouseWheel>") is False
        assert root.tk.call("bind", tag, "<MouseWheel>") == before
        assert tuple(root._tclCommands) == commands
        assert tag not in root.bindtags()
    finally:
        root.tk.call("bind", tag, "<MouseWheel>", "")
