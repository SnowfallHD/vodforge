"""Root menu-subject probe: late actions must retain the subject that opened the menu."""

from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

import yt_downloader.app as app_module
from yt_downloader.app import DownloaderApp


class MenuCapture:
    def __init__(self, *args, **kwargs):
        self.commands = {}
        self.host = args[0]

    def add_command(self, *, label, command, **kwargs):
        self.commands[label] = command

    def add_separator(self):
        pass

    def tk_popup(self, *args):
        pass

    def grab_release(self):
        pass


def opened_menu(monkeypatch):
    menus = []

    def create_menu(*args, **kwargs):
        result = MenuCapture(*args, **kwargs)
        menus.append(result)
        return result

    monkeypatch.setattr(app_module, "ContextMenu", create_menu)
    selected = ["0"]
    opened, confirmations, details = [], [], []
    records = [
        {
            "id": "original",
            "title": "Original selected item",
            "vodforge_output_dir": "/synthetic/original",
        },
        {
            "id": "later",
            "title": "Later selected item",
            "vodforge_output_dir": "/synthetic/later",
        },
    ]
    host = SimpleNamespace(
        video_tree=SimpleNamespace(selection=lambda: tuple(selected)),
        metadata_items=records,
        _terminal_job_for_metadata=lambda info: None,
        _play_selected_library_item=lambda *args: None,
        _show_library_output_details=lambda info: details.append(info["id"]),
        _show_library_annotation_editor=lambda *args: None,
        _open_existing_saved_folder=lambda path: opened.append(str(path)),
        focus_library_menu_button=SimpleNamespace(
            winfo_rootx=lambda: 0, winfo_rooty=lambda: 0, winfo_height=lambda: 1
        ),
    )
    for name in (
        "_show_library_actions_menu",
        "_selected_saved_folder",
        "_open_selected_saved_location",
        "_remove_selected_library_item",
    ):
        setattr(host, name, MethodType(getattr(DownloaderApp, name), host))

    def askyesno(title, text, **kwargs):
        confirmations.append(text)
        return False

    monkeypatch.setattr(app_module.messagebox, "askyesno", askyesno)
    host._show_library_actions_menu()
    return menus[0], selected, opened, confirmations, details


@pytest.mark.parametrize("changed", [False, True])
def test_open_location_retains_original_menu_subject(monkeypatch, changed):
    menu, selected, opened, _confirmations, _details = opened_menu(monkeypatch)
    if changed:
        selected[:] = ["1"]
    menu.commands["Open saved location"]()
    assert opened == [str(Path("/synthetic/original"))]


@pytest.mark.parametrize("changed", [False, True])
def test_remove_confirmation_retains_original_menu_subject(monkeypatch, changed):
    menu, selected, _opened, confirmations, _details = opened_menu(monkeypatch)
    if changed:
        selected[:] = ["1"]
    menu.commands["Remove from Library…"]()
    assert len(confirmations) == 1
    assert "Original selected item" in confirmations[0]
    assert "Later selected item" not in confirmations[0]


def test_output_details_already_retains_original_menu_subject(monkeypatch):
    menu, selected, _opened, _confirmations, details = opened_menu(monkeypatch)
    selected[:] = ["1"]
    menu.commands["Output details…"]()
    assert details == ["original"]


@pytest.mark.parametrize("action", ["Open saved location", "Remove from Library…"])
@pytest.mark.parametrize("change", ["reorder", "removed"])
def test_menu_subject_resolves_latest_owner_without_using_old_index(
    monkeypatch, action, change
):
    menu, _selected, opened, confirmations, _details = opened_menu(monkeypatch)
    host = menu.host
    host.metadata_items = (
        list(reversed(host.metadata_items))
        if change == "reorder"
        else host.metadata_items[1:]
    )
    menu.commands[action]()
    if change == "removed":
        assert opened == [] and confirmations == []
    elif action == "Open saved location":
        assert opened == [str(Path("/synthetic/original"))]
    else:
        assert len(confirmations) == 1 and "Original selected item" in confirmations[0]


@pytest.mark.parametrize("change", ["reorder", "removed"])
def test_removal_rechecks_original_owner_after_nested_confirmation(monkeypatch, change):
    menu, _selected, _opened, _confirmations, _details = opened_menu(monkeypatch)
    host = menu.host
    applied = []
    host._apply_library_removal_plan = lambda info, index, plan: (
        applied.append((info["id"], index)) or set()
    )
    host._reconcile_focus_after_library_removal = lambda _ids: None
    host.status_var = SimpleNamespace(set=lambda _text: None)

    def confirm(*_args, **_kwargs):
        host.metadata_items = (
            list(reversed(host.metadata_items))
            if change == "reorder"
            else host.metadata_items[1:]
        )
        return True

    monkeypatch.setattr(app_module.messagebox, "askyesno", confirm)
    menu.commands["Remove from Library…"]()
    assert applied == ([("original", 1)] if change == "reorder" else [])
