from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from .library_state import library_status_or_location, metadata_output_type
from .models import OutputType
from .run_identity import metadata_output_profile

LIBRARY_ALL_MEDIA = "All"
LIBRARY_ALL_CATEGORIES = "All categories"


def library_categories(items: Sequence[dict[str, Any]]) -> tuple[str, ...]:
    """Return the user-created category vocabulary for one Library snapshot."""

    values = {
        str(item.get("vodforge_user_category") or "").strip()
        for item in items
        if str(item.get("vodforge_user_category") or "").strip()
    }
    return tuple(sorted(values, key=str.casefold))


def _searchable_text(info: dict[str, Any]) -> str:
    lists = (
        info.get("tags"),
        info.get("extra_tags"),
        info.get("categories"),
        info.get("vodforge_user_tags"),
    )
    values = [
        info.get("title"),
        info.get("uploader"),
        info.get("channel"),
        info.get("playlist_title"),
        info.get("vodforge_user_note"),
        info.get("vodforge_user_category"),
        library_status_or_location(info),
        metadata_output_profile(info),
    ]
    for items in lists:
        if isinstance(items, (list, tuple)):
            values.extend(items)
    return "\n".join(str(value or "") for value in values).casefold()


def library_search_terms(query: str) -> tuple[str, ...]:
    """Normalize a plain search query into stable case-insensitive terms."""

    terms: list[str] = []
    for phrase, word in re.findall(r'"([^"]+)"|(\S+)', str(query or "")):
        term = (phrase or word).strip()
        if term:
            terms.append(term.casefold())
    return tuple(terms)


def library_visible_indices(
    items: Sequence[dict[str, Any]],
    output_type: OutputType | str,
    query: str = "",
    category: str = LIBRARY_ALL_CATEGORIES,
) -> list[int]:
    """Return stable projection indices matching type, category, and search terms."""

    selected = str(
        output_type.value if isinstance(output_type, OutputType) else output_type
    )
    selected_category = str(category or LIBRARY_ALL_CATEGORIES).strip()
    terms = library_search_terms(query)
    result: list[int] = []
    for index, item in enumerate(items):
        if (
            selected != LIBRARY_ALL_MEDIA
            and metadata_output_type(item).value != selected
        ):
            continue
        item_category = str(item.get("vodforge_user_category") or "").strip()
        if (
            selected_category != LIBRARY_ALL_CATEGORIES
            and item_category.casefold() != selected_category.casefold()
        ):
            continue
        haystack = _searchable_text(item)
        if all(term in haystack for term in terms):
            result.append(index)
    return result
