"""Selection observations follow an actual selected media subject."""

from types import SimpleNamespace

import pytest

from yt_downloader.app import DownloaderApp


@pytest.mark.parametrize("selection", [(), ("0",), ("17",)])
def test_library_selection_observation_requires_media_subject(selection):
    observed, displayed, cleared = [], [], []
    owner = SimpleNamespace(
        video_tree=SimpleNamespace(selection=lambda: selection),
        _record_feature=lambda *args: observed.append(args),
        _display_selected_metadata=displayed.append,
        _clear_library_selection=lambda: cleared.append(True),
    )
    DownloaderApp._on_video_selected(owner)
    assert observed == ([("library", "selected")] if selection else [])
    assert displayed == ([int(selection[0])] if selection else [])
    assert cleared == ([] if selection else [True])
