"""Shared, session-only YouTube access selection for Tk and Qt."""

from __future__ import annotations

from pathlib import Path

from .models import CookieSource
from .platform_services import is_windows
from .youtube_access import (
    COOKIE_BROWSER_OPTIONS,
    COOKIE_BROWSER_PLACEHOLDER,
    COOKIE_BROWSER_VALUES,
)

WINDOWS_CHROMIUM_COOKIE_BROWSERS = {
    "brave",
    "chrome",
    "chromium",
    "edge",
    "opera",
    "vivaldi",
}
# On Windows these browsers keep their sign-in store locked while they run and
# encrypt it so that only the browser itself can read it (app-bound
# encryption). VODForge does not try to get around either, so it cannot use
# them at all there; it says so instead of letting the run fail.
WINDOWS_CHROMIUM_COOKIE_MESSAGE = (
    "On Windows, Edge, Chrome, Brave, Opera and Vivaldi lock their sign-in so other "
    "apps can't use it. In Settings → YouTube access, choose Browser → Firefox, or "
    "choose cookies.txt with a file exported from your browser."
)


def available_cookie_browsers(platform: str | None = None) -> list[str]:
    """Browser names VODForge can actually read on this platform."""
    return [
        name
        for name in COOKIE_BROWSER_OPTIONS[1:]
        if not (
            is_windows(platform)
            and COOKIE_BROWSER_VALUES[name] in WINDOWS_CHROMIUM_COOKIE_BROWSERS
        )
    ]


def browser_cookie_value(label_or_value: str | None) -> str | None:
    text = str(label_or_value or "").strip()
    if not text or text.lower() in {"none", COOKIE_BROWSER_PLACEHOLDER.lower()}:
        return None
    return COOKIE_BROWSER_VALUES.get(text, text.lower())


def cookie_inputs_for_source(
    source: CookieSource | str,
    cookie_file: Path | None,
    cookie_browser: str | None,
) -> tuple[bool, Path | None, str | None]:
    """Resolve one explicit source without carrying an inactive account choice."""
    try:
        selected = (
            source if isinstance(source, CookieSource) else CookieSource(str(source))
        )
    except ValueError:
        selected = CookieSource.PUBLIC
    if selected == CookieSource.FILE:
        return True, cookie_file, None
    if selected == CookieSource.BROWSER:
        return True, None, browser_cookie_value(cookie_browser)
    return False, None, None


def windows_chromium_cookie_warning(
    cookie_browser: str | None, platform: str | None = None
) -> str | None:
    browser = browser_cookie_value(cookie_browser)
    if is_windows(platform) and browser in WINDOWS_CHROMIUM_COOKIE_BROWSERS:
        return WINDOWS_CHROMIUM_COOKIE_MESSAGE
    return None
