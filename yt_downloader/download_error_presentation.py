"""Bounded user-facing download failures; raw evidence belongs in diagnostics."""

BROWSER_GUIDANCE = (
    "You can try Settings → YouTube access → Browser, then select your browser. "
    "Use a browser where you can watch this video."
)


def download_error_message(error: object) -> str:
    """Never expose unbounded provider text or infer a restriction from no formats."""
    text = str(error).lower()
    if "could not reset the batch failure report" in text:
        return "Could not reset the batch failure report. Check that the log folder is writable, then retry."
    if "no valid" in text and "output" in text:
        return (
            "No valid output was produced. See Technical details for the failed items."
        )
    if "could not copy chrome cookie database" in text or "issues/7271" in text:
        return (
            "Your browser's sign-in information could not be read. Try closing the "
            "browser or selecting Firefox under Settings → YouTube access → Browser. "
            "The cookies.txt option is also available for manual setup."
        )
    if any(
        term in text
        for term in ("confirm your age", "age-restricted", "age restricted")
    ):
        issue = "YouTube requires age verification for this video."
    elif "sign in to confirm" in text or "confirm you're not a bot" in text:
        issue = "YouTube is asking you to confirm your sign-in."
    elif "503" in text or "429" in text:
        issue = "YouTube is temporarily refusing this request. Try again later."
    elif any(
        term in text
        for term in (
            "video unavailable",
            "video is not available",
            "content isn't available",
        )
    ):
        issue = "YouTube reported that this video is unavailable."
    elif "no video formats" in text or ("no usable" in text and "video" in text):
        issue = "No downloadable video was available for this link."
    elif "requested format is not available" in text:
        issue = "The selected quality is unavailable. Try another quality setting."
    elif "javascript runtime" in text or "js runtime" in text:
        return "A required download component is unavailable. Try updating VODForge. See Technical details for more information."
    else:
        return "The download could not finish. See Technical details for the cause."
    return f"{issue} {BROWSER_GUIDANCE}"
