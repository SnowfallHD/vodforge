"""Shared, session-only YouTube access selection for Tk and Qt."""

from __future__ import annotations

from pathlib import Path

from .models import CookieSource
from .platform_services import is_windows
from .youtube_access import COOKIE_BROWSER_PLACEHOLDER, COOKIE_BROWSER_VALUES

WINDOWS_CHROMIUM_COOKIE_BROWSERS = {
    "brave",
    "chrome",
    "chromium",
    "edge",
    "opera",
    "vivaldi",
}
WINDOWS_CHROMIUM_COOKIE_MESSAGE = (
    "Chrome/Edge/Brave/Chromium browser-cookie import is unreliable on Windows because Chromium locks its cookie database. "
    "Choose cookies.txt with an exported YouTube cookies.txt file, choose Firefox browser cookies under Browser, or switch YouTube access to Public."
)


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
