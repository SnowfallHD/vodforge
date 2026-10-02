"""Closed language choices for optional provider subtitle acquisition."""

from itertools import product

from yt_dlp.utils import ISO639Utils

# Use the already required extractor's ISO table, not a translation service.
PROVIDER_SUBTITLE_LANGUAGES = tuple(
    code
    for first, second in product("abcdefghijklmnopqrstuvwxyz", repeat=2)
    if (code := first + second)
    and (long_code := ISO639Utils.short2long(code))
    and ISO639Utils.long2short(long_code) == code
)


def translated_subtitle_language(value: object) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str) and value in PROVIDER_SUBTITLE_LANGUAGES:
        return value
    raise ValueError("Choose Off or a supported subtitle language.")
