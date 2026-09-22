"""Source-native controls with real isolated file work, never user media."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump
from yt_downloader.history import (
    history_archive_owner,
    sanitize_history_record,
    save_history,
)

application = _application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native display required"
)


def wait(app, predicate, seconds=8):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        pump(app, 0.025)
    assert predicate()


def files(app, tmp_path, *, missing=False):
    app.history_path = app.history_path.resolve()
    records = []
    for index in range(2):
        folder = (tmp_path / f"item-{index}").resolve()
        folder.mkdir()
        path = folder / f"clip-{index}.mp4"
        if not missing or index == 0:
            path.write_bytes(f"isolated fixture {index}".encode())
        records.append(
            sanitize_history_record(
                {
                    "id": str(index),
                    "title": f"Fixture {index}",
                    "vodforge_output_path": str(path),
                },
                folder,
                recorded_at="2026-09-17T00:00:00+00:00",
            )
        )
    save_history(app.history_path, records)
    app.download_history = records
    app._reconcile_library_projection()
    app.library_scene.navigate("all")
    app._select_focus_view("library")
    wait(app, lambda: not app._archive_worker.busy)
    return records


def capture(widget, name):
    folder = os.environ.get("VODFORGE_FILE_ACTION_CAPTURE_DIR")
    if folder:
        from yt_downloader.platform_services import capture_own_widget

        output = Path(folder)
        output.mkdir(parents=True, exist_ok=True)
        capture_own_widget(widget).save(output / name)


def test_contextual_bulk_actions_move_exact_selected_files(
    application, tmp_path, monkeypatch
):
    app = application
    rows = files(app, tmp_path)
    destination = (tmp_path / "destination").resolve()
    destination.mkdir()
    from yt_downloader import library_file_actions_ui as ui

    monkeypatch.setattr(ui.filedialog, "askdirectory", lambda **_: str(destination))
    scene = app.library_scene
    scene._toggle_selection(tuple(history_archive_owner(row) for row in rows))
    pump(app)
    texts = [
        scene.canvas.itemcget(i, "text")
        for i in scene.canvas.find_all()
        if scene.canvas.type(i) == "text"
    ]
    assert "Actions…" in texts and "Done" in texts
    assert "Move to…" not in texts and "Delete…" not in texts
    owners = scene.selected_owners
    app._begin_library_file_action("move", owners)
    dialog = app._library_file_dialog
    wait(app, lambda: str(dialog.primary["state"]) == "normal")
    assert dialog.primary["text"] == "Move"
    assert str(destination) in dialog.message.get()
    assert all(Path(row["vodforge_output_path"]).exists() for row in rows)
    pump(app, 0.2)
    assert dialog.heading.winfo_rooty() >= dialog.popup.winfo_rooty()
    assert (
        dialog.description.winfo_rooty() + dialog.description.winfo_height()
        < dialog.primary.winfo_rooty()
    )
    capture(dialog.popup, "move-confirmation.png")
    dialog.primary.invoke()
    wait(app, lambda: dialog.finished)
    assert not app._archive_commit_active
    assert not app._archive_file_recovery_blocked
    assert all(not Path(row["vodforge_output_path"]).exists() for row in rows)
    assert all(
        Path(row["vodforge_output_path"]).exists() for row in app.download_history
    )
    assert all(
        str(destination) in row["vodforge_output_path"] for row in app.download_history
    )
    assert scene.selected_owners == ()
    dialog.secondary.invoke()


def test_delete_confirmation_separates_existing_files_and_missing_entries(
    application, tmp_path, monkeypatch
):
    app = application
    rows = files(app, tmp_path, missing=True)
    trash = (tmp_path / "fixture-trash").resolve()
    trash.mkdir()
    from yt_downloader import platform_services

    calls = []

    def recycle(path):
        calls.append(path)
        target = trash / path.name
        path.rename(target)
        return str(target)

    monkeypatch.setattr(platform_services, "trash_file", recycle)
    import tkinter as tk

    def invoke_delete(menu, *_args):
        index = next(
            i
            for i in range(menu.index("end") + 1)
            if menu.type(i) != "separator" and menu.entrycget(i, "label") == "Delete…"
        )
        menu.invoke(index)

    monkeypatch.setattr(tk.Menu, "tk_popup", invoke_delete)
    app.library_scene._toggle_selection(
        tuple(history_archive_owner(row) for row in rows)
    )
    app._show_library_selection_actions()
    dialog = app._library_file_dialog
    wait(app, lambda: str(dialog.primary["state"]) == "normal")
    assert dialog.primary["text"] == "Move to Trash"
    assert "1 file will be moved to Trash" in dialog.message.get()
    assert "1 file is already missing" in dialog.message.get()
    pump(app, 0.2)
    assert (
        dialog.description.winfo_rooty() + dialog.description.winfo_height()
        < dialog.primary.winfo_rooty()
    )
    capture(dialog.popup, "delete-confirmation.png")
    dialog.primary.invoke()
    wait(app, lambda: dialog.finished)
    assert app.download_history == []
    assert len(calls) == 1
    assert (trash / "clip-0.mp4").read_bytes() == b"isolated fixture 0"
    dialog.secondary.invoke()


def test_permanent_delete_requires_distinct_confirmation_and_no_is_safe(
    application, tmp_path, monkeypatch
):
    app = application
    rows = files(app, tmp_path)
    from yt_downloader import library_file_actions_ui as ui

    monkeypatch.setattr(ui, "system_trash_available", lambda: False)
    prompts = []
    monkeypatch.setattr(
        ui.messagebox,
        "askyesno",
        lambda title, text, **kwargs: prompts.append((title, text, kwargs)) or False,
    )
    app._begin_library_file_action(
        "delete", tuple(history_archive_owner(row) for row in rows)
    )
    dialog = app._library_file_dialog
    wait(app, lambda: str(dialog.primary["state"]) == "normal")
    dialog.primary.invoke()
    assert len(prompts) == 1 and "cannot be undone" in prompts[0][1]
    assert prompts[0][2]["default"] == "no"
    assert all(Path(row["vodforge_output_path"]).exists() for row in rows)
    assert app.download_history == rows and not app._archive_commit_active
    dialog.secondary.invoke()


def test_ready_file_dialog_escape_cancels_without_file_changes(application, tmp_path):
    app = application
    rows = files(app, tmp_path)
    app._begin_library_file_action(
        "delete", tuple(history_archive_owner(row) for row in rows)
    )
    dialog = app._library_file_dialog
    wait(app, lambda: str(dialog.primary["state"]) == "normal")
    dialog.popup.focus_force()
    pump(app)
    dialog.popup.event_generate("<Escape>")
    pump(app)
    assert not dialog.exists()
    assert all(Path(row["vodforge_output_path"]).exists() for row in rows)
    assert app.download_history == rows


@pytest.mark.parametrize("missing", [False, True])
def test_item_delete_menu_keeps_captured_owner_after_projection_reorder(
    application, tmp_path, monkeypatch, missing
):
    import tkinter as tk

    from yt_downloader import platform_services

    app = application
    rows = files(app, tmp_path, missing=missing)
    trash = (tmp_path / "fixture-trash").resolve()
    trash.mkdir()
    calls = []

    def recycle(path):
        calls.append(path)
        target = trash / path.name
        path.rename(target)
        return str(target)

    monkeypatch.setattr(platform_services, "trash_file", recycle)

    def invoke_delete(menu, *_args):
        app.metadata_items = tuple(reversed(app.metadata_items))
        index = next(
            i
            for i in range(menu.index("end") + 1)
            if menu.type(i) != "separator" and menu.entrycget(i, "label") == "Delete…"
        )
        menu.invoke(index)

    monkeypatch.setattr(tk.Menu, "tk_popup", invoke_delete)
    target_index = next(
        i for i, row in enumerate(app.metadata_items) if row["id"] == rows[1]["id"]
    )
    app._show_library_scene_menu(target_index)
    dialog = app._library_file_dialog
    wait(app, lambda: str(dialog.primary["state"]) == "normal")
    assert dialog.primary["text"] == ("Remove entries" if missing else "Move to Trash")
    dialog.primary.invoke()
    wait(app, lambda: dialog.finished)
    assert [row["id"] for row in app.download_history] == [rows[0]["id"]]
    assert Path(rows[0]["vodforge_output_path"]).exists()
    assert calls == ([] if missing else [Path(rows[1]["vodforge_output_path"])])
    dialog.secondary.invoke()


def test_watch_search_origin_and_shared_field_follow_native_navigation(
    application, tmp_path
):
    from yt_downloader.watch_library import watch_rails

    app = application
    files(app, tmp_path)
    app._select_focus_view("watch")
    watch = app.focus_watch
    watch.show_home()
    app._global_search_var.set("Fixture")
    pump(app, 0.2)
    assert watch.search.get() == "Fixture"
    rail = watch_rails(watch._records)[0]
    watch._scene_open("playlist", playlist=rail.key)
    pump(app, 0.2)
    assert watch._scene_route == "playlist" and watch.search.get() == ""
    assert app._global_search_var.get() == ""
    watch._scene_back()
    pump(app, 0.2)
    assert watch.search.get() == "Fixture" and app._global_search_var.get() == "Fixture"
    app.library_search_var.set("separate Library query")
    assert app._global_search_var.get() == "Fixture"
    app._select_focus_view("library")
    assert app._global_search_var.get() == "separate Library query"
