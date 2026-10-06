"""Section switching and bulk dispatch cannot retain hidden Library targets."""

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QUrl
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import qt_app, saved, visual_item
from yt_downloader.qt_quick import main as qt_main


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [
        saved(tmp_path, "Clip", "MP4", category="Clips"),
        saved(tmp_path, "Nature", "MP4", category="Nature"),
        saved(tmp_path, "Sound", "MP3", category="Nature"),
    ]
    candidates = bridge.collectionCandidates
    assert bridge.createCollection("clips", [candidates[0]["owner"]])
    assert bridge.createCollection("nature", [row["owner"] for row in candidates[1:]])
    # Personal collections only, matching the reported Library arrangement.
    for row in bridge._runtime.history:
        row.pop("playlist_id", None)
        row.pop("playlist_title", None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    window.resize(1100, 900)
    bridge.select("Library")
    app.processEvents()
    QTest.qWait(30)
    scene = window.findChild(QObject, "libraryBrowseScene")
    yield app, bridge, window, scene
    bridge.close()
    window.close()
    engine.deleteLater()
    app.processEvents()


def click(window, name, app):
    item = visual_item(window.contentItem(), name)
    assert item is not None and item.isVisible(), name
    item.activated.emit()
    app.processEvents()
    QTest.qWait(20)


def values(scene, name):
    return scene.property(name).toVariant()


@pytest.mark.parametrize("width", [760, 1100, 2400])
def test_home_sections_have_separate_controls_and_switch_clears(library, width):
    app, bridge, window, scene = library
    window.resize(width, 900)
    app.processEvents()
    click(window, "libraryCollectionsSelectButton", app)
    click(window, "libraryGroupSelectionCheckbox", app)
    assert scene.property("selectedEntityCount") == 1
    assert values(scene, "selectedOwners") == []
    assert visual_item(
        window.contentItem(), "libraryCollectionsSelectionActionsButton"
    ).isVisible()
    assert not visual_item(
        window.contentItem(), "librarySelectionActionsButton"
    ).isVisible()
    click(window, "librarySelectButton", app)
    assert scene.property("mediaSelectionMode")
    assert not visual_item(
        window.contentItem(), "libraryGroupSelectionCheckbox"
    ).isVisible()
    assert values(scene, "selectedGroups") == []
    assert scene.property("selectedEntityCount") == 0
    click(window, "librarySelectionBarSelectAll", app)
    assert set(values(scene, "selectedOwners")) == {
        row["owner"] for row in bridge.libraryScene["media"]
    }
    assert scene.property("selectedEntityCount") == 3
    click(window, "librarySelectionBarClear", app)
    assert scene.property("selectedEntityCount") == 0
    assert scene.property("selectionMode")
    click(window, "libraryCollectionsSelectButton", app)
    click(window, "libraryCollectionsSelectionBarSelectAll", app)
    assert scene.property("selectedEntityCount") == 2
    assert values(scene, "selectedOwners") == []
    root = Path(__file__).resolve().parents[2] / "renders"
    root.mkdir(exist_ok=True)
    assert window.grabWindow().save(str(root / f"collections-{width}.png"))
    click(window, "libraryCollectionsSelectButton", app)
    assert not scene.property("selectionMode")


@pytest.mark.parametrize(
    "route,section",
    [
        ("channels", "groups"),
        ("playlists", "groups"),
        ("collections", "groups"),
        ("all", "media"),
        ("videos", "media"),
        ("audio", "media"),
    ],
)
def test_category_select_all_and_navigation_clear(library, route, section):
    app, bridge, window, scene = library
    bridge.navigateLibrary(route)
    app.processEvents()
    click(window, "librarySelectButton", app)
    assert scene.property("selectionSection") == section
    click(window, "librarySelectionBarSelectAll", app)
    key = "selectedGroups" if section == "groups" else "selectedOwners"
    assert scene.property("selectedEntityCount") == len(values(scene, key))
    assert (
        values(scene, "selectedOwners" if section == "groups" else "selectedGroups")
        == []
    )
    click(window, "librarySelectionBarClear", app)
    assert scene.property("selectedEntityCount") == 0
    bridge.navigateLibrary("home")
    app.processEvents()
    assert not scene.property("selectionMode")
    assert values(scene, "selectedOwners") == values(scene, "selectedGroups") == []


def test_search_and_history_changes_prune_media_selection(library):
    app, bridge, window, scene = library
    bridge.navigateLibrary("all")
    app.processEvents()
    click(window, "librarySelectButton", app)
    click(window, "librarySelectionBarSelectAll", app)
    bridge.setLibrarySearch("Nature")
    app.processEvents()
    QTest.qWait(30)
    assert scene.property("selectedEntityCount") == 2
    assert values(scene, "selectedOwners") == [
        row["owner"] for row in bridge.libraryScene["media"]
    ]
    bridge._runtime.history = []
    bridge.historyChanged.emit()
    app.processEvents()
    assert scene.property("selectedEntityCount") == 0


def test_group_delete_dispatch_contains_only_selected_members(library, monkeypatch):
    app, bridge, window, scene = library
    requested = []
    monkeypatch.setattr(
        bridge._files,
        "begin",
        lambda action, owners, *args, **kwargs: (
            requested.append((action, list(owners))) or False
        ),
    )
    click(window, "libraryCollectionsSelectButton", app)
    click(window, "libraryGroupSelectionCheckbox", app)
    expected = bridge.resolveScopedLibrarySelection(
        "groups", values(scene, "selectedGroups")
    )
    assert expected and len(expected) < len(bridge.libraryScene["media"])
    click(window, "libraryCollectionsSelectionActionsButton", app)
    click(window, "librarySelectionAction_delete", app)
    assert requested == [("delete", expected)]
    click(window, "librarySelectButton", app)
    assert values(scene, "selectedGroups") == []


def test_backend_rejects_mixed_malformed_duplicate_and_stale_targets(library):
    _app, bridge, _window, _scene = library
    group = bridge.libraryScene["groups"][0]
    target = {"kind": group["kind"], "key": group["key"]}
    owner = bridge.libraryScene["media"][0]["owner"]
    media = {"kind": "media", "owner": owner}
    assert bridge.resolveScopedLibrarySelection("groups", [target]) == group["owners"]
    assert bridge.resolveScopedLibrarySelection("media", [media]) == [owner]
    for section in ("groups", "media", "other"):
        assert bridge.resolveScopedLibrarySelection(section, [target, media]) == []
    for invalid in (
        [target, media],
        [media, media],
        [{"kind": []}],
        [{"kind": "media", "owner": "stale"}],
    ):
        assert bridge.resolveLibrarySelection(invalid) == []
    assert bridge.resolveScopedLibrarySelection("groups", [media]) == []
    assert bridge.resolveScopedLibrarySelection("media", [target]) == []
    bridge.navigateLibrary("videos")
    assert bridge.resolveScopedLibrarySelection("groups", [target]) == []
    bridge.navigateLibrary("collections")
    assert bridge.resolveScopedLibrarySelection("media", [media]) == []
    bridge._runtime.history = []
    bridge.historyChanged.emit()
    assert bridge.resolveScopedLibrarySelection("groups", [target]) == []
    assert not bridge.startFileActions("delete", [owner], QUrl())


def test_group_detail_owns_member_selection_and_stale_collection_prunes(library):
    app, bridge, window, scene = library
    group = bridge.libraryScene["groups"][0]
    bridge.navigateLibraryGroup(group["kind"], group["key"])
    app.processEvents()
    click(window, "librarySelectButton", app)
    click(window, "librarySelectionBarSelectAll", app)
    assert set(values(scene, "selectedOwners")) == set(group["owners"])
    assert values(scene, "selectedGroups") == []
    bridge.navigateLibrary("collections")
    app.processEvents()
    assert not scene.property("selectionMode")
    click(window, "librarySelectButton", app)
    click(window, "librarySelectionBarSelectAll", app)
    bridge._runtime.history = []
    bridge.historyChanged.emit()
    app.processEvents()
    QTest.qWait(20)
    assert values(scene, "selectedGroups") == []
    assert scene.property("selectedEntityCount") == 0
