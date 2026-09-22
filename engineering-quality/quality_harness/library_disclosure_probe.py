"""Real Library disclosure producers with a synthetic menu surface."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from yt_downloader import app as app_module
from yt_downloader.app import DownloaderApp
from yt_downloader.archive_observations import usage
from yt_downloader.library_scene_ui import LibraryScene

DISCLOSURE_CASES = ("library_disclosure", "player_description")


def disclosure_case(directory, telemetry, case):
    emit = lambda feature, action: usage(telemetry, feature, action)
    if case == "player_description":
        from yt_downloader.player_scene_ui import PlayerSceneMixin

        view = SimpleNamespace(
            _closed=False,
            info={"description": "PRIVATE description"},
            _description_expanded=False,
            _description_excerpt=Mock(),
            _description_more=Mock(),
            _description_panel=Mock(),
            _description_body=Mock(),
            _on_feature=lambda action: emit("player", action),
        )
        PlayerSceneMixin._read_description(view)
        PlayerSceneMixin._read_description(view)
        assert not view._description_expanded
        return {"case": case, "synthetic_detail_surface": True}
    scene = SimpleNamespace(
        _selection_mode=False,
        _selected=set(),
        _on_usage=emit,
        _queue_render=lambda: None,
    )
    LibraryScene._start_selection(scene)
    LibraryScene._clear_selection(scene)
    host = SimpleNamespace(
        metadata_items=[{"id": "PRIVATE id", "title": "PRIVATE title"}],
        _archive_usage=emit,
        _library_scene_owner_action=lambda *_a: None,
        _run_library_copy_action=lambda *_a: None,
        winfo_pointerx=lambda: 0,
        winfo_pointery=lambda: 0,
    )
    for method in (
        "_copy_tags",
        "_copy_description",
        "_copy_personal_tags",
        "_copy_personal_note",
        "_copy_thumbnail_url",
        "_copy_youtube_url",
    ):
        setattr(host, method, lambda *_a: None)
    with patch.object(app_module.tk, "Menu", lambda *_a, **_k: Mock()):
        DownloaderApp._show_library_scene_menu(host, 0)
    assert not scene._selection_mode and not scene._selected
    return {"case": case, "synthetic_menu_surface": True}
