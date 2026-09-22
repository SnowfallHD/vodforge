"""Library annotations and selections retain canonical ownership through edits."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader import app as app_module
from yt_downloader import library_annotations, library_collection_ui
from yt_downloader.archive_browser import archive_row_owner
from yt_downloader.library_annotations import (
    LibraryAnnotation,
    LibraryAnnotationsError,
    LibraryAnnotationsOwner,
)
from yt_downloader.library_scene_ui import LibraryScene
from yt_downloader.library_state import ANNOTATION_OWNER_KEY, PROJECTION_OWNER_KEY


def rows():
    return [
        {
            "id": str(i),
            "title": f"Source title {i}",
            "description": "Provider description",
            "vodforge_output_dir": f"/saved/{i}",
            ANNOTATION_OWNER_KEY: f"annotation:{i}",
            PROJECTION_OWNER_KEY: f"history:{i}",
        }
        for i in range(3)
    ]


def state(tmp_path):
    owner = LibraryAnnotationsOwner(tmp_path / "annotations.json")
    owner.replace(
        "annotation:0", LibraryAnnotation("Keep note", ("Keep tag",), "Old category")
    )
    return SimpleNamespace(
        metadata_items=rows(),
        library_annotations=owner,
        library_scene=SimpleNamespace(selected_indices=(0, 2), navigate=Mock()),
        _reconcile_library_projection=Mock(),
        _record_feature=Mock(),
    )


def test_collection_commit_is_atomic_and_preserves_notes_and_tags(tmp_path):
    owner = LibraryAnnotationsOwner(tmp_path / "annotations.json")
    values = {
        f"owner:{i}": LibraryAnnotation(f"Note {i}", (f"Tag {i}",), "Collection")
        for i in range(4)
    }
    owner.replace_many(values)
    assert owner.snapshot == values
    reloaded = LibraryAnnotationsOwner(owner.path)
    assert reloaded.load() == values


def test_collection_persistence_failure_leaves_previous_memory_and_disk(
    tmp_path, monkeypatch
):
    owner = LibraryAnnotationsOwner(tmp_path / "annotations.json")
    owner.replace("one", LibraryAnnotation("Original"))
    before = owner.path.read_bytes()
    snapshot = dict(owner.snapshot)
    monkeypatch.setattr(
        library_annotations,
        "write_private_bytes",
        Mock(side_effect=OSError("Read only")),
    )
    with pytest.raises(LibraryAnnotationsError):
        owner.replace_many(
            {
                "one": LibraryAnnotation(category="Changed"),
                "two": LibraryAnnotation(category="Changed"),
            }
        )
    assert dict(owner.snapshot) == snapshot and owner.path.read_bytes() == before


def test_collection_dialog_save_resolves_only_current_captured_owners(
    tmp_path, monkeypatch
):
    view = state(tmp_path)
    captured = {}

    def dialog(_master, items, save, **options):
        captured.update(items=items, save=save, options=options)

    monkeypatch.setattr(library_collection_ui, "LibraryCollectionDialog", dialog)
    app_module.DownloaderApp._show_library_collection_editor(view)
    assert captured["options"]["selected"] == ("annotation:0", "annotation:2")
    before = deepcopy(view.metadata_items)
    captured["save"]("Trips", ("annotation:0", "annotation:2"))
    assert view.library_annotations.annotation_for("annotation:0") == LibraryAnnotation(
        "Keep note", ("Keep tag",), "Trips"
    )
    assert view.metadata_items == before
    view.metadata_items = view.metadata_items[1:]
    with pytest.raises(ValueError, match="changed"):
        captured["save"]("Another", ("annotation:0",))
    assert view.library_annotations.annotation_for("annotation:0").category == "Trips"


def test_inline_add_remove_tags_preserves_source_facts_and_personal_note(tmp_path):
    view = state(tmp_path)
    before = deepcopy(view.metadata_items)
    owner = archive_row_owner(view.metadata_items[0])
    assert app_module.DownloaderApp._library_scene_add_tag(view, owner, "Travel")
    assert view.library_annotations.annotation_for("annotation:0").tags == (
        "Keep tag",
        "Travel",
    )
    assert app_module.DownloaderApp._library_scene_add_tag(view, owner, "Travel", True)
    assert view.library_annotations.annotation_for("annotation:0") == LibraryAnnotation(
        "Keep note", ("Keep tag",), "Old category"
    )
    assert view.metadata_items == before


def test_inline_tag_owner_cannot_follow_reordered_or_removed_row(tmp_path):
    view = state(tmp_path)
    owner = archive_row_owner(view.metadata_items[0])
    view.metadata_items.reverse()
    assert app_module.DownloaderApp._library_scene_add_tag(view, owner, "Travel")
    assert view.library_annotations.annotation_for("annotation:0").tags[-1] == "Travel"
    view.metadata_items = view.metadata_items[:-1]
    assert not app_module.DownloaderApp._library_scene_add_tag(
        view, owner, "Wrong owner"
    )
    assert not view.library_annotations.annotation_for("annotation:2").tags


def test_selection_survives_reorder_and_retires_removed_owners():
    original = rows()
    selected = {archive_row_owner(original[0]), archive_row_owner(original[2])}
    view = SimpleNamespace(
        _selected=selected,
        _targets=[("old", "stale callback")],
        _records=tuple(original),
        _presentation_change=Mock(),
        _queue_render=Mock(),
        _draw_sidebar=Mock(),
    )
    LibraryScene.set_records(view, list(reversed(original)))
    assert LibraryScene.selected_indices.fget(view) == (0, 2)
    assert view._targets == []
    LibraryScene.set_records(view, [original[1], original[2]])
    assert LibraryScene.selected_indices.fget(view) == (1,)
    assert selected == {archive_row_owner(original[2])}


def navigation_state():
    value = SimpleNamespace(
        _records=rows(),
        _route="all",
        _page=3,
        _query="Source",
        _sort="title",
        _filter="Trips",
        _category="A playlist",
        _group_key="playlist:abc",
        _group_kind="playlists",
        _targets=[("old", Mock())],
        _detail_owner="",
        _detail_origin=None,
        _pending_scroll=None,
        _tag_var=Mock(),
        _on_usage=Mock(),
        _presentation_change=Mock(),
        _queue_render=Mock(),
        _draw_sidebar=Mock(),
        _clear_selection=Mock(),
        canvas=Mock(yview=Mock(return_value=(0.42, 0.8))),
        navigate=Mock(),
    )
    value._reset_catalog_viewport = lambda: LibraryScene._reset_catalog_viewport(value)
    return value


def test_library_escape_restores_origin_filters_group_page_and_scroll():
    view = navigation_state()
    origin = {
        name: getattr(view, name)
        for name in (
            "_route",
            "_page",
            "_query",
            "_sort",
            "_filter",
            "_category",
            "_group_key",
            "_group_kind",
        )
    }
    LibraryScene.show_details(view, 1)
    assert view._targets == []
    view._presentation_change.assert_called_once_with("navigation")
    LibraryScene.show_details(view, 2)
    LibraryScene.return_from_detail(view)
    assert {name: getattr(view, name) for name in origin} == origin
    assert view._pending_scroll == 0.42
    view.navigate.assert_not_called()
    view._queue_render.reset_mock()
    LibraryScene.return_from_detail(view)
    view._queue_render.assert_not_called()


@pytest.mark.parametrize(
    "method,args",
    [
        ("navigate", ("channels",)),
        ("_group_open", ("playlists", "new", "New")),
        ("_change_page", (1,)),
        ("_set_filter", ("New",)),
        ("_set_sort", ("recent",)),
    ],
)
def test_navigation_retires_old_hit_targets_before_deferred_repaint(method, args):
    view = navigation_state()
    getattr(LibraryScene, method)(view, *args)
    assert view._targets == []


def test_tag_removal_retains_captured_owner_across_navigation_and_deletion():
    view = navigation_state()
    owner = archive_row_owner(view._records[0])
    view._detail_owner = owner
    view._add_tag = Mock()
    LibraryScene._remove_tag(view, owner, "Travel")
    view._add_tag.assert_called_once_with(owner, "Travel", True)
    view._add_tag.reset_mock()
    view._detail_owner = archive_row_owner(view._records[1])
    LibraryScene._remove_tag(view, owner, "Travel")
    view._add_tag.assert_not_called()
    view._detail_owner = owner
    view._records.pop(0)
    LibraryScene._remove_tag(view, owner, "Travel")
    view._add_tag.assert_not_called()


def test_description_override_roundtrips_without_changing_provider_or_notes(tmp_path):
    view = state(tmp_path)
    before = deepcopy(view.metadata_items)
    owner = archive_row_owner(view.metadata_items[0])
    assert app_module.DownloaderApp._library_scene_save_description(
        view, owner, "My description"
    )
    saved = view.library_annotations.annotation_for("annotation:0")
    assert saved.description == "My description" and saved.note == "Keep note"
    assert saved.tags == ("Keep tag",) and saved.category == "Old category"
    assert view.metadata_items == before
    reloaded = LibraryAnnotationsOwner(view.library_annotations.path)
    assert reloaded.load()["annotation:0"] == saved
    assert app_module.DownloaderApp._library_scene_save_description(view, owner, "")
    assert view.library_annotations.annotation_for("annotation:0").description == ""
    view.metadata_items.pop(0)
    assert not app_module.DownloaderApp._library_scene_save_description(
        view, owner, "Wrong video"
    )


def test_empty_description_is_an_intentional_override_and_legacy_is_not(tmp_path):
    owner = LibraryAnnotationsOwner(tmp_path / "annotations.json")
    owner.replace("blank", LibraryAnnotation(description=""))
    assert not owner.annotation_for("blank").empty
    assert LibraryAnnotation().description is None
    assert LibraryAnnotationsOwner(owner.path).load()["blank"].description == ""


def test_detail_version_choice_resolves_current_owner_and_retains_origin():
    data = rows()
    first, second = (archive_row_owner(row) for row in data[:2])
    origin = {"_route": "videos", "scroll": 0.4}
    view = SimpleNamespace(
        _route="detail",
        _records=tuple(reversed(data)),
        _detail_owner=first,
        _detail_versions=((first, "1. MP4"), (second, "2. MP3")),
        _version_var=SimpleNamespace(get=lambda: "2. MP3"),
        _detail_origin=origin,
        _targets=[object()],
        _context_targets=[object()],
        _action=Mock(),
        _presentation_change=Mock(),
        _queue_render=Mock(),
    )
    LibraryScene._choose_detail_version(view)
    assert view._detail_owner == second
    view._action.assert_called_once_with("select_version", 1)
    assert (
        view._detail_origin is origin
        and not view._targets
        and not view._context_targets
    )
    view._action.reset_mock()
    view._records = tuple(
        row for row in view._records if archive_row_owner(row) != second
    )
    LibraryScene._choose_detail_version(view)
    view._action.assert_not_called()
    view._route = "home"
    view._records = tuple(data)
    LibraryScene._choose_detail_version(view)
    view._action.assert_not_called()
