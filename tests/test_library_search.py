from __future__ import annotations

from yt_downloader.library_search import (
    LIBRARY_ALL_CATEGORIES,
    LIBRARY_ALL_MEDIA,
    library_categories,
    library_search_terms,
    library_visible_indices,
)


def test_search_matches_user_and_provider_metadata_across_all_media() -> None:
    items = [
        {
            "title": "Deep work mix",
            "uploader": "Studio",
            "tags": ["ambient"],
            "vodforge_user_tags": ("Focus",),
            "vodforge_user_note": "Use on writing days",
            "vodforge_user_category": "Work",
            "vodforge_output_type": "MP4",
        },
        {
            "title": "Interview",
            "uploader": "Channel",
            "vodforge_user_category": "Research",
            "vodforge_output_type": "MP3",
        },
    ]

    assert library_visible_indices(items, LIBRARY_ALL_MEDIA, "writing focus") == [0]
    assert library_visible_indices(items, LIBRARY_ALL_MEDIA, "research") == [1]
    assert library_visible_indices(items, "MP4", "studio") == [0]
    assert library_visible_indices(items, "MP3", "studio") == []


def test_search_supports_quoted_phrases_and_is_order_stable() -> None:
    items = [
        {"title": "Alpha deep work", "vodforge_output_type": "MP4"},
        {"title": "Deep alpha work", "vodforge_output_type": "MP4"},
    ]

    assert library_search_terms('alpha "deep work"') == ("alpha", "deep work")
    assert library_visible_indices(items, "MP4", 'alpha "deep work"') == [0]


def test_categories_are_user_created_filters_not_duplicate_authority() -> None:
    items = [
        {
            "title": "One",
            "vodforge_user_category": "Learning",
            "vodforge_output_type": "MP4",
        },
        {
            "title": "Two",
            "vodforge_user_category": "music",
            "vodforge_output_type": "MP3",
        },
        {
            "title": "Three",
            "vodforge_user_category": "Learning",
            "vodforge_output_type": "MP3",
        },
    ]

    assert library_categories(items) == ("Learning", "music")
    assert library_visible_indices(
        items,
        LIBRARY_ALL_MEDIA,
        category="learning",
    ) == [0, 2]
    assert library_visible_indices(
        items,
        "MP3",
        "two",
        category="music",
    ) == [1]
    assert library_visible_indices(
        items,
        LIBRARY_ALL_MEDIA,
        category=LIBRARY_ALL_CATEGORIES,
    ) == [0, 1, 2]
