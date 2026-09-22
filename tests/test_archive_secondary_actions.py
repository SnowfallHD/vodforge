"""Maintained regression from the independent controller probe: secondary pointer actions must not activate primary targets."""

from types import MethodType, SimpleNamespace

import pytest

from yt_downloader.archive_browser import ArchiveBrowserModel, ArchiveComponent
from yt_downloader.archive_browser_ui import ArchiveBrowser
from yt_downloader.archive_paths import ArchivePath


def browser(kind):
    model = ArchiveBrowserModel()
    records = [
        {
            "id": "one",
            "title": "One",
            "webpage_url": "https://www.youtube.com/watch?v=one",
            "vodforge_output_dir": "/synthetic/archive/one",
            "vodforge_output_type": "MP4",
        },
        {
            "id": "two",
            "title": "Two",
            "webpage_url": "https://www.youtube.com/watch?v=two",
            "vodforge_output_dir": "/synthetic/archive/two",
            "vodforge_output_type": "MP4",
        },
    ]
    model.replace(records, (0, 1))
    model.navigate(None, mode="all")
    model.select(1)
    component = ArchiveComponent(
        "target",
        kind,
        "Target",
        "",
        (0,),
        ArchivePath.parse("/synthetic/archive/one") if kind == "folder" else None,
    )
    outcomes = {"activated": [], "navigated": [], "menus": [], "selected": []}
    canvas = SimpleNamespace(
        canvasx=lambda x: x, canvasy=lambda y: y, focus_set=lambda: None
    )
    host = SimpleNamespace(
        canvas=canvas,
        model=model,
        _boxes=[((0, 0, 300, 180), component)],
        _open_boxes=[((10, 10, 100, 45), component)],
        _selected_folder=None,
        _refresh=lambda: None,
        _last_row="",
        _on_select=lambda: outcomes["selected"].append(model.selected_index()),
        _on_activate=outcomes["activated"].append,
        _on_folder=lambda path, indices: None,
        navigate=lambda path: outcomes["navigated"].append(str(path)),
        _on_menu=lambda event: (
            outcomes["menus"].append(model.selected_index()) or "break"
        ),
    )
    for name in ["_hit", "_click", "_open_component", "_menu"]:
        setattr(host, name, MethodType(getattr(ArchiveBrowser, name), host))
    return host, outcomes


@pytest.mark.parametrize("button", [2, 3])
@pytest.mark.parametrize("kind", ["media", "activity", "folder"])
def test_secondary_click_on_primary_affordance_does_not_activate(kind, button):
    host, outcomes = browser(kind)
    result = host._menu(SimpleNamespace(x=30, y=25, num=button))
    assert outcomes["activated"] == [] and outcomes["navigated"] == [], outcomes
    assert result == "break"
    if kind != "folder":
        assert outcomes["menus"] == [0]


def test_secondary_click_elsewhere_selects_current_card_without_activation():
    host, outcomes = browser("media")
    host._menu(SimpleNamespace(x=150, y=100, num=3))
    assert outcomes["activated"] == [] and outcomes["navigated"] == []
    assert outcomes["menus"] == [0]


@pytest.mark.parametrize("kind", ["media", "activity", "folder"])
def test_primary_click_keeps_primary_action(kind):
    host, outcomes = browser(kind)
    host._click(SimpleNamespace(x=30, y=25, num=1))
    assert outcomes["activated"] == ([0] if kind != "folder" else [])
    assert outcomes["navigated"] == (
        ["/synthetic/archive/one"] if kind == "folder" else []
    )
    assert outcomes["menus"] == []
