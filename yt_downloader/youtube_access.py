"""Shared access choices and explanatory copy for Settings and offline tours."""

from .models import CookieSource

COOKIE_BROWSER_PLACEHOLDER = "Choose a browser"
COOKIE_BROWSER_VALUES = {
    "Chrome": "chrome",
    "Edge": "edge",
    "Firefox": "firefox",
    "Brave": "brave",
    "Chromium": "chromium",
    "Opera": "opera",
    "Vivaldi": "vivaldi",
}
COOKIE_BROWSER_OPTIONS = [COOKIE_BROWSER_PLACEHOLDER, *COOKIE_BROWSER_VALUES]
COOKIE_SOURCE_OPTIONS = (
    CookieSource.PUBLIC.value,
    CookieSource.BROWSER.value,
    CookieSource.FILE.value,
)
ACCESS_TITLE = "YOUTUBE ACCESS & AGE RESTRICTIONS"
ACCESS_DESCRIPTION = (
    "For age-restricted or sign-in-required videos, try Browser and select the "
    "browser you use for YouTube. Public needs no account."
)
ACCESS_TOOLTIP = (
    "Public downloads without your account. Browser uses your existing YouTube "
    "sign-in and is the easiest option to try for restricted videos. Your account "
    "must have access; age verification may still be required. "
    "cookies.txt is an optional manual alternative."
)
BROWSER_TOOLTIP = (
    "Select the browser where you are signed in to YouTube. Your system may ask "
    "permission to read its sign-in storage. VODForge does not save the cookie "
    "contents. This does not guarantee access to restricted videos."
)
