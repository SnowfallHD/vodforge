"""Contextual controls preserve discoverability, owner identity and consent."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_presentation_diagnostics import real_owner
from tests.test_scene_navigation import Painter, library_view, records
from yt_downloader import app as app_module
from yt_downloader.app import DownloaderApp
from yt_downloader.archive_browser import archive_row_owner
from yt_downloader.archive_library_ui import ArchiveLibraryMixin
from yt_downloader.archive_observations import usage
from yt_downloader.library_scene_ui import LibraryScene
from yt_downloader.product_telemetry import _load_outbox

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


def bind_selection(view):
    for name in (
        "_start_selection",
        "_toggle_selection",
        "_clear_selection",
        "set_records",
    ):
        setattr(view, name, getattr(LibraryScene, name).__get__(view))
    view._draw_sidebar = Mock()
    return view


@pytest.mark.parametrize(
    "route", ["home", "all", "channels", "playlists", "collections"]
)
def test_browsing_does_not_offer_selection_boxes_until_select(route):
    view = bind_selection(library_view(route))
    view.render()
    assert not any(
        getattr(callback, "func", None) == view._toggle_selection
        for _box, callback in view._targets
    )
    assert "Select" in view.buttons
    view.buttons["Select"]()
    view.buttons = {}
    view.render()
    assert any(
        getattr(callback, "func", None) == view._toggle_selection
        for _box, callback in view._targets
    )
    assert "Done" in view.buttons and "Select" not in view.buttons


def test_selection_is_explicit_retires_stale_owners_and_done_restores_browsing():
    view = bind_selection(library_view("all"))
    original = archive_row_owner(view._records[0])
    view._start_selection()
    view._start_selection()
    view._toggle_selection((original,))
    assert view._selected == {original}
    view.set_records(view._records[1:])
    assert not view._selected
    view._toggle_selection((original,))  # stale card cannot re-add removed media
    assert not view._selected
    view._clear_selection()
    view._clear_selection()
    assert not view._selection_mode
    calls = [call.args for call in view._on_usage.call_args_list]
    assert calls.count(("library", "selection_started")) == 1
    assert calls.count(("library", "selection_finished")) == 1


def test_selecting_card_body_toggles_exact_item_instead_of_opening_details():
    view = bind_selection(library_view("all"))
    view._start_selection()
    view.render()
    _box, callback = next(
        (b, c)
        for b, c in view._targets
        if getattr(c, "func", None) == view._toggle_selection and b[2] - b[0] > 30
    )
    callback()
    assert view._selected == {archive_row_owner(view._records[0])}
    view.show_details.assert_not_called()
    callback()
    assert not view._selected


def test_media_card_has_play_and_one_owner_bound_overflow():
    view = library_view("all")
    view.render()
    assert "Play" in view.buttons and "" in view.buttons
    assert "More" not in view.buttons
    callback = view.buttons[""]
    assert callback.func is view._open_item_menu
    assert callback.args[0] in {archive_row_owner(row) for row in view._records}


@pytest.mark.parametrize("width", [340, 520, 720, 1116])
@pytest.mark.parametrize("selection", [False, True])
def test_responsive_toolbar_controls_never_overlap_or_escape(width, selection):
    view = library_view("all")
    view._selection_mode = selection
    if selection:
        view._selected = {archive_row_owner(view._records[0])}
    boxes = []
    painter = Painter(view)
    painter.button = lambda x, y, w, label, callback, **kw: boxes.append(
        (x, y, x + w, y + kw.get("height", 40), label)
    )
    view._toolbar(painter, width, 80, "All media")
    for x, y, right, bottom, label in boxes:
        assert x >= 0 and right <= width, (width, label)
        for other in boxes:
            if other[-1] == label:
                continue
            assert (
                right <= other[0]
                or other[2] <= x
                or bottom <= other[1]
                or other[3] <= y
            )


class Menu:
    def __init__(self, *args, **kwargs):
        self.commands = {}
        self.children = {}

    def add_command(self, label, command, **kwargs):
        self.commands[label] = command

    def add_cascade(self, label, menu):
        self.children[label] = menu

    def add_separator(self):
        pass

    def tk_popup(self, *args):
        pass

    def grab_release(self):
        pass


def scene_menu(monkeypatch, usage_callback=None):
    menus = []

    def create(*a, **k):
        value = Menu(*a, **k)
        menus.append(value)
        return value

    monkeypatch.setattr(app_module, "ContextMenu", create)
    host = SimpleNamespace(
        metadata_items=list(records(2)),
        _archive_usage=usage_callback or Mock(),
        _library_scene_action=Mock(),
        winfo_pointerx=lambda: 0,
        winfo_pointery=lambda: 0,
        _run_library_copy_action=lambda fn: fn(),
    )
    for name in (
        "_copy_tags",
        "_copy_description",
        "_copy_personal_tags",
        "_copy_personal_note",
        "_copy_thumbnail_url",
        "_copy_youtube_url",
    ):
        setattr(host, name, Mock())
    host._library_scene_owner_action = (
        DownloaderApp._library_scene_owner_action.__get__(host)
    )
    DownloaderApp._show_library_scene_menu(host, 0)
    return host, menus[0]


@pytest.mark.parametrize("changed", ["reorder", "removed"])
@pytest.mark.parametrize(
    "action",
    ["collection", "location", "open_file", "copy_path", "remove", "move", "delete"],
)
def test_disclosed_file_actions_resolve_original_owner_after_refresh(
    monkeypatch, changed, action
):
    host, menu = scene_menu(monkeypatch)
    all_callbacks = [
        *menu.commands.values(),
        *menu.children["File options"].commands.values(),
    ]
    callback = next(c for c in all_callbacks if c.args[0] == action)
    host.metadata_items = (
        host.metadata_items[::-1] if changed == "reorder" else host.metadata_items[1:]
    )
    callback()
    if changed == "reorder":
        host._library_scene_action.assert_called_once_with(action, 1)
    else:
        host._library_scene_action.assert_not_called()


def test_more_menu_retains_every_moved_action_without_copy_command_wall(monkeypatch):
    host, menu = scene_menu(monkeypatch)
    assert len(menu.commands) == 5
    assert set(menu.children) == {"File options", "Copy"}
    assert set(menu.children["File options"].commands) == {
        "Open in default app",
        "Update file location\u2026",
        "Copy file path",
        "Source details\u2026",
        "Output details\u2026",
        "Move to…",
        "Remove Library entry only…",
    }
    assert len(menu.children["Copy"].commands) == 6
    captured = host.metadata_items[0]
    host.metadata_items.reverse()
    menu.children["Copy"].commands["Source description"]()
    host._copy_description.assert_called_once_with(captured)


@pytest.mark.parametrize("changed", ["reorder", "removed"])
def test_file_picker_cannot_relink_different_item_during_nested_refresh(
    monkeypatch, changed
):
    from yt_downloader import archive_library_ui

    host = SimpleNamespace(
        metadata_items=list(records(2)),
        video_tree=SimpleNamespace(selection=lambda: ("0",)),
        _archive_begin_relink=Mock(),
    )

    def pick(**kwargs):
        host.metadata_items = (
            host.metadata_items[::-1]
            if changed == "reorder"
            else host.metadata_items[1:]
        )
        return "/PRIVATE/new.mp4"

    monkeypatch.setattr(archive_library_ui.filedialog, "askopenfilename", pick)
    ArchiveLibraryMixin._archive_relink_selected(host)
    if changed == "reorder":
        host._archive_begin_relink.assert_called_once_with(
            None, (1,), exact="/PRIVATE/new.mp4"
        )
    else:
        host._archive_begin_relink.assert_not_called()


@pytest.mark.parametrize("permission", ["allowed", "denied", "withdrawn"])
def test_actual_disclosure_producers_obey_consent_and_never_send_media_content(
    tmp_path, monkeypatch, permission
):
    owner = real_owner(tmp_path, permitted=permission != "denied")
    if permission == "withdrawn":
        owner.set_enabled(False)
    emit = lambda feature, action: usage(owner, feature, action)
    view = bind_selection(library_view("all"))
    view._on_usage = emit
    view._start_selection()
    view._toggle_selection((archive_row_owner(view._records[0]),))
    view._clear_selection()
    scene_menu(monkeypatch, emit)
    assert owner.shutdown(2)
    events = _load_outbox(tmp_path / "events.json")
    actions = {e.action for e in events if e.feature == "library"}
    assert actions == (
        {"selection_started", "selected", "selection_finished", "menu_opened"}
        if permission == "allowed"
        else set()
    )
    payload = json.dumps([e.public_payload() for e in events])
    assert "Video 000" not in payload and "/saved/" not in payload


def test_empty_library_has_one_working_pair_of_starting_actions():
    view = library_view("home")
    view._records = []
    labels = []

    class Capture(Painter):
        def button(self, *args, **kwargs):
            labels.append(args[3])
            super().button(*args, **kwargs)

    view._browse(Capture(view), 1116)
    assert labels.count("Go to Forge") == 1 and labels.count("Import Media") == 1
    assert not {"Newest first", "Filter", "Select", "See All"} & view.buttons.keys()
    view.canvas.create_window.assert_not_called()
    view.buttons["Go to Forge"]()
    view.buttons["Import Media"]()
    assert [c.args for c in view._action.call_args_list] == [
        ("forge", None),
        ("import", None),
    ]


def test_populating_empty_library_restores_relevant_browse_controls():
    view = library_view("home")
    view._records = []
    view.render()
    assert "Select" not in view.buttons
    view._records = records(4)
    view.buttons = {}
    view.render()
    assert {"Select", "Newest first", "Filter"} <= view.buttons.keys()
    view.canvas.create_window.assert_called()


def test_empty_search_keeps_filter_recovery_available():
    view = library_view("all")
    view._query = "no-matching-fixture-value"
    view.render()
    assert "Clear filters" in view.buttons
    view.buttons["Clear filters"]()
    view._clear_filters.assert_called_once()
