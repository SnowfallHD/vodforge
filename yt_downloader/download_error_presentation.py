"""Bounded failure explanations and next steps for the existing download surfaces."""

from typing import Self

from .failure_diagnostics import capture_failure, classify_failure

BROWSER_GUIDANCE = (
    "You can try Settings → YouTube access → Browser, then select your browser. "
    "Use a browser where you can watch this video."
)

# Same closed vocabulary as failure_diagnostics; no second failure classifier.
FAILURE_GUIDANCE = {
    "network": "The connection failed. Check your internet connection, then retry. If the site is unavailable, wait and try later.",
    "rate_limited": "The site is limiting requests. Wait before retrying; repeated retries may prolong the limit.",
    "authentication_required": f"The site requires access verification. {BROWSER_GUIDANCE}",
    "source_unavailable": "The source is unavailable. Open the link in your browser to check it. If it was removed, use another source.",
    "disk_full": "There is not enough free disk space. Free space on the output drive or choose another output folder, then retry.",
    "permission_denied": "A required file or folder could not be accessed. Check its permissions and close apps using it, or choose an output folder you can write to, then retry.",
    "transcoding": "Media conversion failed. Check Technical details, then retry once. If it repeats, use Support → Send feedback and include diagnostics.",
    "validation": "The output failed validation. Retry once with the same settings. If it repeats, use Support → Send feedback and include diagnostics. Technical details identifies the failed check.",
    "unknown": "The download could not finish. Check Library for a saved output before retrying. If it repeats, use Support → Send feedback and include diagnostics. See Technical details for the recorded cause.",
    "dependency_missing": "A required download component is unavailable. Update or reinstall VODForge, then retry. See Technical details for the missing component.",
    "unsupported_format": "The requested format or quality is unavailable. Choose another format or a lower quality setting, then retry.",
    "invalid_input": "The input could not be used. Check the source link or selected input file, correct it, then try again.",
    "output_conflict": "The output location conflicts with an existing file or an unsafe path. Choose another output folder and retry; keep existing files until you have checked them.",
    "source_restricted": "The site restricts access to this source. Check whether you can play it in your browser. If you have access, select that browser in Settings → YouTube access; otherwise use another source.",
    "provider_extraction": "The site's media information could not be read. Update VODForge and retry. If it repeats, use Support → Send feedback and include diagnostics.",
    "filesystem": "A required file or drive could not be read or written. Check that the drive is connected and the file exists; choose another output folder if needed, then retry.",
    "resource_exhausted": "The computer ran out of resources. Close other demanding apps, then retry. For video conversion, a lower output resolution may help.",
}


class DownloadErrorMessage(str):
    """Friendly terminal text carrying an approved recovery action."""

    action = "choose_output_folder"
    action_label = "Choose folder"
    code = "output_path_too_long"


class YouTubeAccessMessage(str):
    """Terminal text that offers to open Settings → YouTube access.

    The string is the full sentence form for logs and run details; the
    attributes hold the same content split up for the recovery pop-up.
    """

    action = "open_youtube_access"
    action_label = "YouTube access"
    code = "youtube_access_required"
    # Named "heading", not "title", so str.title() keeps working.
    heading: str
    summary: str
    steps: tuple[str, ...]
    tip: str
    kept: str

    def __new__(
        cls,
        text: str,
        *,
        title: str = "",
        summary: str = "",
        steps: tuple[str, ...] = (),
        tip: str = "",
        kept: str = "",
    ) -> Self:
        message = super().__new__(cls, text)
        message.heading = title
        message.summary = summary or (text if not title else "")
        message.steps = tuple(steps)
        message.tip = tip
        message.kept = kept
        return message

    def with_kept(self, count: int) -> "YouTubeAccessMessage":
        """The same message after a playlist kept some finished videos."""
        kept = (
            "1 finished video was kept."
            if count == 1
            else f"{count} finished videos were kept."
        )
        return YouTubeAccessMessage(
            f"{kept} {self}",
            title=self.heading,
            summary=self.summary,
            steps=self.steps,
            tip=self.tip,
            kept=kept,
        )

    def presentation(self) -> dict[str, object]:
        """Fields for the pop-up, in display order."""
        return {
            "title": self.heading or "YouTube needs a signed-in browser",
            "summary": self.summary,
            "kept": self.kept,
            "steps": list(self.steps),
            "tip": self.tip,
        }


# Failure codes and yt-dlp warnings meaning YouTube wants a signed-in browser.
ACCESS_CHALLENGE_CODES = frozenset({"bot_challenge", "login_required"})


def is_youtube_access_challenge(diagnostic: object) -> bool:
    """Whether a captured failure shows YouTube's sign-in or bot check."""
    if diagnostic is None:
        return False
    return (
        getattr(diagnostic, "failure_code", None) in ACCESS_CHALLENGE_CODES
        or getattr(diagnostic, "extractor_warning", None) == "bot_challenge"
    )


VPN_TIP = "Using a VPN? Turning it off for this download often helps too."


def youtube_access_message(
    *, cookies_on: bool = False, stopped_after: int | None = None
) -> YouTubeAccessMessage:
    """Explain YouTube's bot check and the setting that usually clears it."""
    title = "YouTube wants to confirm you're not a bot"
    if stopped_after:
        summary = (
            f"This happened on {stopped_after} videos in a row, so VODForge "
            "stopped the playlist."
        )
    else:
        summary = "VODForge couldn't read this video."
    if cookies_on:
        steps: tuple[str, ...] = (
            (
                "Open YouTube access and pick a browser where you're signed in "
                "to YouTube and can play the video, or use cookies.txt."
            ),
            "Retry the download.",
        )
    else:
        steps = (
            "Open YouTube access and choose Browser.",
            "Pick a browser where you're signed in to YouTube.",
            "Retry the download.",
        )
    text = " ".join(
        (f"{title}.", summary, "In Settings → YouTube access:", *steps, VPN_TIP)
    )
    return YouTubeAccessMessage(
        text, title=title, summary=summary, steps=steps, tip=VPN_TIP
    )


def _output_path_budget_error(error: object) -> object | None:
    # Import lazily: app composes this presenter and owns the typed path error.
    from .download_service import OutputPathBudgetError

    seen: set[int] = set()
    pending = [error]
    while pending and len(seen) < 8:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, OutputPathBudgetError):
            return current
        for name in ("error", "__cause__", "__context__"):
            nested = getattr(current, name, None)
            if isinstance(nested, BaseException):
                pending.append(nested)
    return None


def download_error_message(error: object) -> str:
    """Pair every known category and unknown failure with a bounded next step."""
    path_error = _output_path_budget_error(error)
    if path_error is not None:
        return DownloadErrorMessage(str(path_error))
    text = str(error)[:16384].lower()
    diagnostic = capture_failure(error) if isinstance(error, BaseException) else None
    reason = diagnostic.reason if diagnostic is not None else classify_failure(text)
    if "subtitles" in text and reason == "rate_limited":
        return (
            "The site rate-limited the selected subtitles. No output was committed. "
            "Wait before retrying, or turn translated subtitles Off in Options "
            "if you want the video without that translation."
        )
    if "selected translated subtitles are unavailable" in text:
        return (
            "The selected translation is unavailable or its source language could not "
            "be verified. No output was committed. Choose another language or turn "
            "translated subtitles Off in Options."
        )
    # Machine evidence takes priority over ambiguous provider wording.
    if "could not reset the batch failure report" in text and reason != "disk_full":
        return "Could not reset the batch failure report. Check that the log folder is writable, then retry."
    # A known missing cookie store needs access-source recovery, not an output
    # folder change. Keep stronger disk/resource/network evidence authoritative.
    if (
        diagnostic is not None
        and diagnostic.failure_code == "cookies_unavailable"
        and diagnostic.cookie_failure == "database_missing"
        and reason in {"filesystem", "authentication_required", "unknown"}
    ):
        return (
            "The selected browser's cookie database could not be found. "
            "In Settings → YouTube access, choose an installed browser where you "
            "can play the video, or provide cookies.txt. If the video needs no "
            "sign-in, choose Public."
        )
    if (
        diagnostic is not None
        and reason != "unknown"
        and (diagnostic.os_error is not None or diagnostic.http_status is not None)
    ):
        return FAILURE_GUIDANCE[reason]
    if reason in {"disk_full", "permission_denied", "filesystem", "resource_exhausted"}:
        return FAILURE_GUIDANCE[reason]
    if any(
        term in text
        for term in (
            "h264_nvenc",
            "cannot load nvcuda",
            "required nvenc api",
            "no nvenc capable devices",
        )
    ):
        return "NVIDIA encoding failed. In Settings, turn off Use NVIDIA NVENC for MP4 encoding and retry with CPU encoding. To use NVIDIA again, update your graphics driver and check that your GPU supports NVENC. Technical details contains the encoder's error."
    if "only an hdr video source" in text:
        return "This video is only available in HDR. Choose a video with an SDR version for these MP4 presets, then retry."
    if "no valid" in text and "output" in text:
        return "No valid output was produced. Review each failed item's reason and next step in Technical details, then retry the failed sources."
    if "could not copy chrome cookie database" in text or "issues/7271" in text:
        return "Your browser's sign-in information could not be read. Close the browser and retry, or select another browser where you can play the video in Settings → YouTube access. You can also provide cookies.txt."
    if any(
        term in text
        for term in ("confirm your age", "age-restricted", "age restricted")
    ):
        return f"YouTube requires age verification for this video. {BROWSER_GUIDANCE}"
    if "sign in to confirm" in text or "confirm you're not a bot" in text:
        return youtube_access_message()
    if "did not return the requested playlist item" in text:
        return (
            "YouTube did not confirm that it found this video, so nothing was saved. "
            "Check the video's link in your browser before trying again."
        )
    if "no usable audio source" in text:
        if diagnostic is not None and diagnostic.format_count == 0:
            return (
                "No downloadable audio was available because YouTube returned no media "
                "formats. Check that the video plays in your browser before trying again."
            )
        if diagnostic is not None and diagnostic.format_count:
            return (
                "YouTube returned media formats, but none had usable audio. "
                "Check that the video has sound before trying again."
            )
        return (
            "No downloadable audio was available for this link. "
            "Check that the video plays in your browser before trying again."
        )
    if "no video formats" in text or "no usable video source" in text:
        return f"No downloadable video was available for this link. {BROWSER_GUIDANCE}"
    if "requested format is not available" in text:
        return "The selected quality is unavailable. Choose a lower quality or another output format, then retry."
    return FAILURE_GUIDANCE[reason]


def technical_download_error(error: object) -> str:
    """Retain bounded redacted causes, including wrapped/provider/process errors."""
    from .support_diagnostics import redact_line

    reason = (
        capture_failure(error).reason
        if isinstance(error, BaseException)
        else classify_failure(str(error))
    )
    rows = [f"Failure category: {reason}"]
    pending = [error]
    seen: set[int] = set()
    while pending and len(seen) < 4:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        # CalledProcessError.__str__ includes the whole command. Keep the exit
        # status and stderr instead, without copying command arguments.
        exit_code = getattr(current, "returncode", None)
        message = (
            f"Process exited with status {exit_code}"
            if isinstance(exit_code, int)
            else str(current).strip()
        )
        rows.append(
            f"Failure details: {type(current).__name__}: "
            + (
                "\n".join(redact_line(line) for line in message[:4096].splitlines()[:4])
                or "No further error detail was provided."
            )
        )
        stderr = getattr(current, "stderr", None)
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        if isinstance(stderr, str) and stderr.strip():
            rows.extend(redact_line(line) for line in stderr[-2048:].splitlines()[-3:])
        for attribute in ("__cause__", "__context__", "cause", "reason"):
            nested = getattr(current, attribute, None)
            if isinstance(nested, BaseException):
                pending.append(nested)
        exc_info = getattr(current, "exc_info", None)
        if (
            isinstance(exc_info, tuple)
            and len(exc_info) == 3
            and isinstance(exc_info[1], BaseException)
        ):
            pending.append(exc_info[1])
    detail = "\n".join(rows)[:3400]
    return f"{detail}\nNext step: {download_error_message(error)}"
