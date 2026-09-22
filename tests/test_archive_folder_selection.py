"""Independent folder/media selection integration probes using production model and controller."""

from types import MethodType, SimpleNamespace

import pytest

from yt_downloader.archive_browser import ArchiveBrowserModel
from yt_downloader.archive_browser_ui import ArchiveBrowser
from yt_downloader.archive_paths import ArchivePath


def folder_browser(previous):
    model = ArchiveBrowserModel()
    records = [
        {
            "id": str(i),
            "title": f"Media {i}",
            "webpage_url": f"https://www.youtube.com/watch?v=media{i}",
            "vodforge_output_dir": f"/synthetic/archive/folder{i}/export",
            "vodforge_output_type": "MP4",
        }
        for i in range(3)
    ]
    model.replace(records, (0, 1, 2))
    model.navigate(ArchivePath.parse("/synthetic/archive"), mode="folders")
    if previous is not None:
        model.select(previous)
    outcomes = {"folders": [], "selected": []}
    canvas = SimpleNamespace(
        canvasx=lambda x: x, canvasy=lambda y: y, focus_set=lambda: None
    )
    host = SimpleNamespace(
        canvas=canvas,
        model=model,
        _selected_folder=None,
        _last_row="",
        _boxes=[
            ((0, i * 100, 300, i * 100 + 90), c)
            for i, c in enumerate(model.page_components)
        ],
        _open_boxes=[],
        _refresh=lambda: None,
        _on_folder=lambda path, indices: outcomes["folders"].append(str(path)),
        _on_select=lambda: outcomes["selected"].append(model.selected_index()),
    )
    for name in ("_hit", "_click", "_step", "selection"):
        setattr(host, name, MethodType(getattr(ArchiveBrowser, name), host))
    return host, outcomes


@pytest.mark.parametrize(
    "previous,direction,expected",
    [(0, 1, "folder2"), (2, -1, "folder0"), (None, 1, "folder2")],
)
def test_keyboard_movement_starts_at_visibly_selected_folder(
    previous, direction, expected
):
    host, outcomes = folder_browser(previous)
    host._click(SimpleNamespace(x=150, y=140, num=1))
    assert host._selected_folder.title == "folder1"
    host._step(direction)
    assert host._selected_folder.title == expected, {
        "folder": host._selected_folder.title,
        "media_selection": host.selection(),
        "callbacks": outcomes,
    }


def test_selecting_folder_does_not_expose_previous_media_as_active_selection():
    host, outcomes = folder_browser(0)
    host._click(SimpleNamespace(x=150, y=140, num=1))
    assert host._selected_folder.title == "folder1"
    assert host.selection() == (), {
        "folder": host._selected_folder.title,
        "media_selection": host.selection(),
        "callbacks": outcomes,
    }
