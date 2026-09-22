"""Maintained composed Library journey. Native Tk, synthetic saved files; no physical input or codec claim."""

import os

import pytest

from tests.test_archive_models import saved
from tests.test_archive_native import application as _application
from tests.test_archive_native import pump
from yt_downloader.archive_browser import archive_row_owner
from yt_downloader.history import history_annotation_owner, save_history
from yt_downloader.library_annotations import LibraryAnnotation

application = _application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="native GUI lease required",
)


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
def test_filters_grouped_versions_details_and_back_preserve_browsing_context(
    application, tmp_path, monkeypatch, size
):
    app = application
    monkeypatch.setattr(app, "_load_thumbnail_preview", lambda *a, **k: None)
    rows = []
    for video, kind, category in [
        ("shared-alpha", "MP4", "Travel"),
        ("shared-alpha", "MP3", "Travel"),
        ("other-beta", "MP4", "Work"),
    ]:
        path = tmp_path / video / (kind + " review variant") / ("media." + kind.lower())
        path.parent.mkdir(parents=True)
        path.write_bytes(b"synthetic file; no playback requested")
        row = saved(path, video=video, kind=kind, playlist="Series")
        row.update(
            title=f"{video} {kind}",
            description=f"Original source description for {video} {kind}",
            tags=["source", kind],
            vodforge_output_profile=f"{kind} saved version",
            vodforge_output_variant=f"{kind} review variant",
            vodforge_encoding_summary={
                "source": {"Source format selector used": "original source retained"},
                "output": {"Output container": kind, "Output file path": str(path)},
            },
        )
        rows.append(row)
        app.library_annotations.replace(
            history_annotation_owner(row),
            LibraryAnnotation(
                note=f"Personal note {video} {kind}",
                tags=("personal", kind),
                category=category,
            ),
        )
    app.download_history = rows
    save_history(app.history_path, rows)
    history_before = app.history_path.read_bytes()
    app._reconcile_library_projection()
    app.geometry(size)
    app._select_focus_view("library")
    app.video_tree.navigate(None, mode="all")
    app.library_output_type_var.set("All")
    pump(app, 0.2)
    assert len(app.video_tree.model.visible) == 3

    app.library_output_type_var.set("MP3")
    pump(app)
    assert [
        app.metadata_items[i]["vodforge_output_type"]
        for i in app.video_tree.model.visible
    ] == ["MP3"]
    app.library_output_type_var.set("All")
    app.library_category_var.set("Travel")
    app.library_search_var.set("shared-alpha")
    pump(app)
    assert len(app.video_tree.model.visible) == 2
    assert len(app.video_tree.model.page_components) == 1
    assert len(app.video_tree.model.page_components[0].indices) == 2

    bounds, _component = next(
        (bounds, c) for bounds, c in app.video_tree._boxes if c.kind == "media"
    )
    left, _top, right, bottom = bounds
    app.video_tree.canvas.event_generate(
        "<Button-1>", x=int((left + right) / 2), y=int(bottom - 18)
    )
    pump(app)
    assert app.video_tree.selection()
    app.focus_library_details_button.invoke()
    pump(app)
    assert app.library_scene.winfo_ismapped() and app.library_scene._route == "detail"
    mode_before, path_before, page_before = (
        app.video_tree.model.mode,
        app.video_tree.model.path,
        app.video_tree.model.page,
    )

    scene = app.library_scene
    choice = scene._version_choice
    window = next(
        item
        for item in scene.canvas.find_all()
        if scene.canvas.type(item) == "window"
        and scene.canvas.itemcget(item, "window") == str(choice)
    )
    region = tuple(float(v) for v in scene.canvas.cget("scrollregion").split())
    scene.canvas.yview_moveto(max(0, scene.canvas.bbox(window)[1] - 20) / region[3])
    pump(app)
    assert choice.winfo_ismapped()
    target = next(
        i
        for i in app._archive_variant_indices
        if app.metadata_items[i]["vodforge_output_type"] == "MP3"
    )
    option = tuple(choice.cget("values"))[app._archive_variant_indices.index(target)]
    choice.set(option)
    choice.event_generate("<<ComboboxSelected>>", when="tail")
    pump(app)
    selected = app.metadata_items[int(app.video_tree.selection()[0])]
    assert (
        selected["id"] == "shared-alpha" and selected["vodforge_output_type"] == "MP3"
    )
    assert scene._detail_owner == archive_row_owner(selected)
    assert (
        "Original source description for shared-alpha MP3"
        in scene._description_section.text.get("1.0", "end")
    )
    texts = [
        scene.canvas.itemcget(item, "text")
        for item in scene.canvas.find_all()
        if scene.canvas.type(item) == "text"
    ]
    assert "original source retained" in texts and "MP3" in texts
    # The current version's note remains available through the real note editor.
    from yt_downloader import app as app_module

    dialogs = []
    original_dialog = app_module.LibraryAnnotationDialog

    def capture_dialog(*args, **kwargs):
        dialog = original_dialog(*args, **kwargs)
        dialogs.append(dialog)
        return dialog

    monkeypatch.setattr(app_module, "LibraryAnnotationDialog", capture_dialog)
    scene._action("notes", target)
    pump(app)
    assert dialogs[-1].popup.winfo_ismapped()
    assert "Personal note shared-alpha MP3" in dialogs[-1].note.get("1.0", "end")
    dialogs[-1].popup.destroy()
    scene.return_from_detail()
    pump(app)
    assert app.video_tree.winfo_ismapped()
    assert (
        app.video_tree.model.mode,
        app.video_tree.model.path,
        app.video_tree.model.page,
    ) == (mode_before, path_before, page_before)
    assert app.library_category_var.get() == "Travel"
    assert app.library_search_var.get() == "shared-alpha"
    assert app.library_output_type_var.get() == "All"
    assert app.history_path.read_bytes() == history_before


def test_version_selector_stays_with_current_library_card(application, tmp_path):
    from yt_downloader.archive_paths import ArchivePath

    app = application
    rows = []
    for folder, kind in [
        ("first-copy", "MP4"),
        ("first-copy", "MP3"),
        ("other-copy", "M4A"),
    ]:
        path = tmp_path / folder / kind / ("clip." + kind.lower())
        row = saved(path, video="same-video", kind=kind)
        row["vodforge_output_variant"] = kind
        rows.append(row)
    app.download_history = rows
    app._reconcile_library_projection()
    app.geometry("1100x600")
    app.library_output_type_var.set("All")
    app._select_focus_view("library")
    browser = app.video_tree
    browser.navigate(ArchivePath.parse(str(tmp_path / "first-copy")), mode="folders")
    selected = next(
        i
        for i, row in enumerate(app.metadata_items)
        if row["vodforge_output_type"] == "MP4"
    )
    outside = next(
        i
        for i, row in enumerate(app.metadata_items)
        if row["vodforge_output_type"] == "M4A"
    )
    browser.selection_set(str(selected))
    app._display_selected_metadata(selected)
    pump(app)
    assert {
        app.metadata_items[i]["vodforge_output_type"]
        for i in app._archive_variant_indices
    } == {"MP4", "MP3"}
    before = (
        browser.model.mode,
        browser.model.path,
        browser.model.page,
        browser.canvas.yview(),
    )
    # A stale callback for a no-longer-represented card cannot navigate or select it.
    app._archive_variant_indices = (outside,)
    app._archive_variant_choice.configure(values=("Stale saved version",))
    app._archive_variant_choice.set("Stale saved version")
    app._archive_choose_version()
    pump(app)
    assert browser.selection() == (str(selected),)
    assert (
        browser.model.mode,
        browser.model.path,
        browser.model.page,
        browser.canvas.yview(),
    ) == before
    assert outside not in app._archive_variant_indices


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
def test_preview_menu_admission_and_rejected_removal_preserve_real_library_state(
    application, tmp_path, monkeypatch, size
):
    import tkinter as tk

    from tests.test_state_authority import LiveWorker, make_job
    from yt_downloader import app as app_module
    from yt_downloader.library_state import PROJECTION_OWNER_KEY

    app = application
    app.geometry(size)
    monkeypatch.setattr(app, "_load_thumbnail_preview", lambda *_a, **_k: None)
    app.download_history = []
    app.active_job = make_job(tmp_path, video_id="active-other")
    app.worker = LiveWorker()
    app.pending_jobs = []
    app._terminal_jobs = []
    app._library_projection_owner().record_preview(
        "native-preview",
        [
            {
                "id": f"native-{i}",
                "title": f"Preview story {i}",
                "webpage_url": f"https://www.youtube.com/watch?v=native-{i}",
                "vodforge_output_type": "MP4",
            }
            for i in range(2)
        ],
    )
    for i in range(2):
        app.library_annotations.replace(
            f"preview:native-preview:{i}",
            LibraryAnnotation(note=f"Personal preview note {i}"),
        )
    app._reconcile_library_projection()
    app.video_tree.navigate(None, mode="activity")
    app.library_output_type_var.set("All")
    app._select_focus_view("library")
    pump(app, 0.2)
    first = next(
        index
        for index, row in enumerate(app.metadata_items)
        if row.get("id") == "native-0"
    )
    bounds, _component = next(
        (bounds, component)
        for bounds, component in app.video_tree._boxes
        if first in component.indices
    )
    app.video_tree.canvas.event_generate(
        "<Button-1>", x=int((bounds[0] + bounds[2]) / 2), y=int(bounds[3] - 18)
    )
    pump(app)
    assert app.metadata_items[int(app.video_tree.selection()[0])]["id"] == "native-0"
    assert app.focus_library_menu_button.winfo_ismapped()

    built = make_job(tmp_path, video_id="native-0")
    monkeypatch.setattr(
        app, "_build_download_job_from_current_settings", lambda *_a, **_k: built
    )
    monkeypatch.setattr(
        app, "_enqueue_queue_preview", lambda *_a: app._reconcile_library_projection()
    )
    menus = []
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda menu, *_a: menus.append(menu))
    errors = []
    monkeypatch.setattr(
        app_module.messagebox, "showerror", lambda *_a: errors.append(_a)
    )
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *_a: True)
    queue_changed = app.run_recovery.queue_changed

    def denied(*_a, **_k):
        raise app_module.RunStateError("controlled queue write rejection")

    try:
        before = app.library_projection.snapshot
        annotations_before = app.library_annotations.path.read_bytes()
        monkeypatch.setattr(app.run_recovery, "queue_changed", denied)
        app.focus_library_menu_button.invoke()
        menus.pop().invoke("Start download in Forge")
        pump(app)
        assert app.library_projection.snapshot == before
        assert app.library_annotations.path.read_bytes() == annotations_before
        assert app._focus_selected_view == "library"
        assert not app.pending_jobs
        assert errors

        monkeypatch.setattr(app.run_recovery, "queue_changed", queue_changed)
        app.focus_library_menu_button.invoke()
        menus.pop().invoke("Start download in Forge")
        pump(app, 0.25)
        assert app.pending_jobs == [built]
        assert app._focus_selected_view == "forge"
        assert app._focus_selected_run_id == built.run_id
        by_owner = {row[PROJECTION_OWNER_KEY]: row for row in app.metadata_items}
        assert (
            by_owner[f"run:{built.run_id}"]["vodforge_user_note"]
            == "Personal preview note 0"
        )
        assert (
            by_owner["preview:native-preview:1"]["vodforge_user_note"]
            == "Personal preview note 1"
        )
        assert "preview:native-preview:0" not in by_owner

        app._select_focus_view("library")
        app.video_tree.navigate(None, mode="activity")
        selected = next(
            index
            for index, row in enumerate(app.metadata_items)
            if row[PROJECTION_OWNER_KEY] == f"run:{built.run_id}"
        )
        app.video_tree.selection_set(str(selected))
        app._display_selected_metadata(selected)
        pump(app)
        before_remove = app.library_projection.snapshot
        monkeypatch.setattr(app.run_recovery, "queue_changed", denied)
        app.focus_library_menu_button.invoke()
        menus.pop().invoke("Remove from Library…")
        pump(app)
        assert app.pending_jobs == [built]
        assert app.library_projection.snapshot == before_remove
        assert built.run_id not in app.__dict__.get(
            "_library_suppressed_run_ids", set()
        )
        assert len(errors) == 2
    finally:
        app.active_job = None
        app.worker = None
        app.pending_jobs = []


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
@pytest.mark.parametrize("status", ["Stopped", "Failed"])
@pytest.mark.parametrize("fault", ["none", "annotation", "queue"])
def test_retry_menu_retains_annotations_through_reload_and_editor(
    application, tmp_path, monkeypatch, size, status, fault
):
    import tkinter as tk
    from dataclasses import replace
    from tkinter import ttk

    from tests.test_archive_native import native_descendants
    from tests.test_retry_annotation_lineage import EDITED, ORIGINAL, writer_fault
    from tests.test_state_authority import LiveWorker, make_job
    from yt_downloader import app as app_module
    from yt_downloader import library_annotations, run_state
    from yt_downloader.library_annotation_ui import LibraryAnnotationDialog
    from yt_downloader.library_annotations import LibraryAnnotationsOwner
    from yt_downloader.library_state import PROJECTION_OWNER_KEY

    app = application
    app.geometry(size)
    monkeypatch.setattr(app, "_load_thumbnail_preview", lambda *_a, **_k: None)
    monkeypatch.setattr(
        app, "_enqueue_queue_preview", lambda *_a: app._reconcile_library_projection()
    )
    app.download_history = []
    previous = make_job(tmp_path, video_id="native-retry")
    previous.terminal_status = status
    previous.preview_info = {
        "id": "native-retry",
        "title": "Story with saved notes",
        "webpage_url": previous.url,
        "vodforge_output_type": "MP4",
    }
    sibling = make_job(tmp_path, video_id="native-sibling")
    sibling.terminal_status = "Stopped"
    sibling.preview_info = {
        "id": "native-sibling",
        "title": "Another story",
        "vodforge_output_type": "MP4",
    }
    app._terminal_jobs = [previous, sibling]
    app.active_job = make_job(tmp_path, video_id="native-active")
    app.worker = LiveWorker()
    app.pending_jobs = []
    for job in app._terminal_jobs:
        app.run_recovery.terminal_attempt(job, job.terminal_status, "Stopped")
    app.library_annotations.replace("run:" + previous.run_id, ORIGINAL)
    untouched = LibraryAnnotation("Untouched sibling", ("sibling",), "Other")
    app.library_annotations.replace("run:" + sibling.run_id, untouched)
    monkeypatch.setattr(
        app,
        "_build_download_job_from_current_settings",
        lambda *_a, **_k: replace(previous),
    )
    menus, editors, errors = [], [], []
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda menu, *_a: menus.append(menu))
    monkeypatch.setattr(
        app_module.messagebox, "showerror", lambda *_a: errors.append(_a)
    )
    original_show = LibraryAnnotationDialog.show

    def show(editor):
        editors.append(editor)
        original_show(editor)

    monkeypatch.setattr(LibraryAnnotationDialog, "show", show)

    def select(run_id):
        index = next(
            i
            for i, row in enumerate(app.metadata_items)
            if row.get(PROJECTION_OWNER_KEY) == "run:" + run_id
        )
        app.video_tree.selection_set(str(index))
        app._display_selected_metadata(index)
        pump(app)
        return app.metadata_items[index]

    def reload_library():
        app.pending_jobs = app.run_recovery.store.load_queued_jobs()
        app._terminal_jobs = app.run_recovery.store.load_terminal_jobs()
        app.library_annotations = LibraryAnnotationsOwner(app.library_annotations.path)
        app.library_annotations.load()
        app._reconcile_library_projection()
        app._select_focus_view("library")
        app.video_tree.navigate(None, mode="activity")
        pump(app)

    try:
        reload_library()
        app.library_output_type_var.set("All")
        select(previous.run_id)
        app.focus_library_menu_button.invoke()
        menu = menus.pop()
        select(sibling.run_id)  # A posted menu keeps its original subject.
        with monkeypatch.context() as failures:
            if fault != "none":
                failures.setattr(
                    library_annotations if fault == "annotation" else run_state,
                    "write_private_bytes",
                    writer_fault(13),
                )
            menu.invoke("↻ Retry in Forge")
        menu.destroy()
        reload_library()
        assert len(app.pending_jobs) == (0 if fault == "queue" else 1)
        target_id = previous.run_id if fault == "queue" else app.pending_jobs[0].run_id
        row = select(target_id)
        assert row["id"] == "native-retry"
        assert row["vodforge_user_note"] == ORIGINAL.note
        assert tuple(row["vodforge_user_tags"]) == ORIGINAL.tags
        assert row["vodforge_user_category"] == ORIGINAL.category
        app.focus_library_menu_button.invoke()
        menu = menus.pop()
        menu.invoke("Edit notes, tags & category…")
        pump(app)
        editor = editors.pop()
        assert editor.note.get("1.0", "end-1c") == ORIGINAL.note
        editor.note.delete("1.0", "end")
        editor.note.insert("1.0", EDITED.note)
        editor.tags_var.set(", ".join(EDITED.tags))
        editor.category_var.set(EDITED.category)
        save = next(
            w
            for w in native_descendants(editor.popup)
            if isinstance(w, ttk.Button) and str(w.cget("text")) == "Save details"
        )
        save.invoke()
        pump(app)
        assert not editor.popup.winfo_exists()
        menu.destroy()
        reload_library()
        row = select(target_id)
        assert row["vodforge_user_note"] == EDITED.note
        assert tuple(row["vodforge_user_tags"]) == EDITED.tags
        assert row["vodforge_user_category"] == EDITED.category
        assert (
            app.library_annotations.annotation_for("run:" + sibling.run_id) == untouched
        )
        assert len(errors) == (1 if fault == "queue" else 0)
    finally:
        app.active_job = None
        app.worker = None
        app.pending_jobs = []


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
@pytest.mark.parametrize(
    "boundary", ["dependency", "initialization", "readiness", "load"]
)
def test_opening_failures_replace_loading_and_keep_captured_recovery_subject(
    application, tmp_path, monkeypatch, size, boundary
):
    import tkinter as tk
    from tkinter import ttk
    from types import SimpleNamespace

    from tests.test_archive_native import native_descendants, wait_for
    from yt_downloader import app as app_module
    from yt_downloader import platform_services

    app = application
    app.geometry(size)
    rows = []
    for identity in ("original", "different"):
        path = tmp_path / identity / (identity + ".mp4")
        path.parent.mkdir()
        path.write_bytes(b"controlled saved file; provider load is rejected")
        rows.append(saved(path, video=identity, kind="MP4"))
    app.download_history = rows
    monkeypatch.setattr(app, "_library_thumbnail_path", lambda *_a: None)
    monkeypatch.setattr(app, "_load_thumbnail_preview", lambda *_a, **_k: None)
    app._reconcile_library_projection()
    app._select_focus_view("library")
    app.video_tree.navigate(None, mode="all")
    index = next(
        i for i, row in enumerate(app.metadata_items) if row["id"] == "original"
    )
    app.video_tree.selection_set(str(index))
    app._display_selected_metadata(index)
    pump(app)
    released = []

    class Backend:
        def load(self, *_a, **_k):
            raise PermissionError(13, "controlled provider file failure")

        def shutdown(self):
            released.append(True)

    engine = SimpleNamespace(
        failed=boundary == "initialization",
        ready=boundary == "load",
        start=lambda: None,
        create_backend=lambda: Backend(),
        shutdown=lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        app, "playback_engine", None if boundary == "dependency" else engine
    )
    monkeypatch.setattr(
        platform_services, "find_runtime_executable", lambda _name: "controlled-ffmpeg"
    )
    monkeypatch.setattr(
        app_module.messagebox,
        "showerror",
        lambda *_a, **_k: pytest.fail("opening failure used a modal dialog"),
    )
    opened = []
    monkeypatch.setattr(app, "_open_existing_saved_folder", opened.append)

    app.focus_library_play_button.invoke()
    other = next(
        i for i, row in enumerate(app.metadata_items) if row["id"] == "different"
    )
    app.video_tree.selection_set(str(other))

    def labels():
        return [
            str(w.cget("text"))
            for w in native_descendants(app)
            if isinstance(w, (tk.Label, ttk.Label))
        ]

    wait_for(app, lambda: "Media needs attention" in labels(), timeout=12)
    assert "Opening saved media…" not in labels()
    assert app._archive_overlay.winfo_ismapped()
    assert app._archive_opening_operation is None
    assert app._archive_playback_origins == {}
    open_location = next(
        w
        for w in native_descendants(app._archive_overlay)
        if isinstance(w, ttk.Button) and w.cget("text") == "Open saved location"
    )
    open_location.invoke()
    assert opened == [tmp_path / "original"]
    assert released == ([True] if boundary == "load" else [])
    back = next(
        w
        for w in native_descendants(app._archive_overlay)
        if isinstance(w, ttk.Button) and w.cget("text") == "Back to browse"
    )
    back.invoke()
    pump(app)
    assert app._archive_overlay is None
    assert app._archive_playback_host is None
    assert app.video_tree.winfo_ismapped()
    assert app.download_history == rows


@pytest.fixture(autouse=True)
def legacy_folder_workspace_for_existing_contracts(application):
    """These contracts target the retained folder workspace, not the default scenes."""
    application._library_scene_action("folders", None)
    application.update()
