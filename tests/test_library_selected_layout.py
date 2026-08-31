from __future__ import annotations

import inspect

import yt_downloader.app as app_module
from yt_downloader.app import DownloaderApp
from yt_downloader.ui_layout import (
    FOCUS_LIBRARY_SELECTED_DESCRIPTION_VISIBLE_LINES,
    FOCUS_LIBRARY_SELECTED_DETAILS_HEIGHT,
    FOCUS_LIBRARY_SELECTED_OVERVIEW_HEIGHT,
    FOCUS_LIBRARY_SELECTED_TAGS_MAX_HEIGHT,
    FOCUS_LIBRARY_SELECTED_TAGS_MAX_VISIBLE_LINES,
    FOCUS_LIBRARY_SELECTED_TITLE_EXTRA_LINES,
    selected_description_max_height,
    selected_overview_height,
)


def test_selected_overview_adds_one_measured_title_line() -> None:
    assert FOCUS_LIBRARY_SELECTED_OVERVIEW_HEIGHT == 81
    assert FOCUS_LIBRARY_SELECTED_TITLE_EXTRA_LINES == 1
    assert selected_overview_height(title_line_height=20) == 101
    assert selected_overview_height(title_line_height=27) == 108


def test_selected_tags_cap_leaves_description_as_the_larger_region() -> None:
    assert FOCUS_LIBRARY_SELECTED_TAGS_MAX_HEIGHT == 84
    assert FOCUS_LIBRARY_SELECTED_TAGS_MAX_VISIBLE_LINES == 2
    assert (
        FOCUS_LIBRARY_SELECTED_DESCRIPTION_VISIBLE_LINES
        > FOCUS_LIBRARY_SELECTED_TAGS_MAX_VISIBLE_LINES
    )

    description_top = 486
    library_table_bottom = 590
    description_height = selected_description_max_height(
        description_top=description_top,
        library_table_bottom=library_table_bottom,
    )

    assert description_height == 104
    assert description_height > FOCUS_LIBRARY_SELECTED_TAGS_MAX_HEIGHT


def test_selected_item_height_remains_fixed_while_tags_are_capped() -> None:
    library_source = inspect.getsource(DownloaderApp._build_focus_library_view)

    assert FOCUS_LIBRARY_SELECTED_DETAILS_HEIGHT == 360
    assert (
        "details.configure(width=410, height=FOCUS_LIBRARY_SELECTED_DETAILS_HEIGHT)"
        in library_source
    )
    assert "tags_line.configure(height=FOCUS_LIBRARY_SELECTED_TAGS_MAX_HEIGHT)" in (
        library_source
    )
    assert "tags_line.grid_propagate(False)" in library_source
    assert "height=FOCUS_LIBRARY_SELECTED_TAGS_MAX_VISIBLE_LINES" in library_source
    assert "height=FOCUS_LIBRARY_SELECTED_DESCRIPTION_VISIBLE_LINES" in library_source
    assert "details.rowconfigure(3, weight=0)" in library_source
    assert "details.rowconfigure(4, weight=1, minsize=120)" in library_source


def test_selected_overview_uses_the_active_title_font_measurement() -> None:
    layout_source = inspect.getsource(DownloaderApp._fit_focus_selected_overview_text)

    assert "selected_overview_height(" in layout_source
    assert 'title_font.metrics("linespace")' in layout_source
    assert "focus_selected_overview.configure(height=" in layout_source
    assert (
        app_module.FOCUS_LIBRARY_SELECTED_TAGS_MAX_HEIGHT
        == FOCUS_LIBRARY_SELECTED_TAGS_MAX_HEIGHT
    )
