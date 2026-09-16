"""Immutable machine-readable failure facts. Raw diagnostics stay local."""

import errno
import socket
import ssl

# Used only to classify exceptions, never to execute a process.
import subprocess  # nosec B404
from dataclasses import asdict, dataclass

FAILURE_STAGES = frozenset(
    {
        "preparation",
        "processing",
        "batch",
        "unknown",
        "analysis",
        "reuse",
        "staging",
        "download",
        "image_preparation",
        "transcode",
        "validation",
        "commit",
        "sidecars",
        "history",
        "dispatch",
        "playback",
    }
)
ERROR_TYPES = frozenset(
    {
        "TimeoutError",
        "ConnectionError",
        "PermissionError",
        "FileNotFoundError",
        "OSError",
        "CalledProcessError",
        "DownloadError",
        "ExtractorError",
        "HTTPError",
        "URLError",
        "RuntimeError",
        "ValueError",
        "TypeError",
        "AttributeError",
        "KeyError",
        "IndexError",
        "AssertionError",
        "UnboundLocalError",
        "RecursionError",
        "ZeroDivisionError",
    }
)


# Last shipped frame is an observed location, not proof that the cause originated
# there. Traceback messages, locals and absolute filenames are never inspected.
FIRST_PARTY_MODULES = frozenset(
    {
        "app",
        "engagement_ui",
        "history",
        "libvlc_backend",
        "local_audio_video",
        "local_audio_video_ui",
        "media_player",
        "media_player_ui",
        "output_validation",
        "process_lifecycle",
        "product_telemetry",
        "run_identity",
        "run_state",
        "safe_output",
        "settings_store",
        "telemetry_features",
        "updates",
        "export_planning",
        "original_audio",
        "media_preview",
        "playback_surface",
    }
)


def _first_party_location(error: BaseException) -> dict[str, str | int]:
    location: dict[str, str | int] = {}
    frame = error.__traceback__
    depth = 0
    while frame is not None and depth < 64:
        name = frame.tb_frame.f_globals.get("__name__", "")
        if isinstance(name, str) and name.startswith("yt_downloader."):
            module = name.removeprefix("yt_downloader.")
            if module in FIRST_PARTY_MODULES and 1 <= frame.tb_lineno <= 100000:
                location = {
                    "source_module": module,
                    "source_line": frame.tb_lineno,
                    "source_scope": "first_party_frame",
                }
        frame = frame.tb_next
        depth += 1
    return location


FAILURE_CODES = frozenset(
    {
        "no_video_stream",
        "no_audio_stream",
        "format_unavailable",
        "selector_invalid",
        "login_required",
        "bot_challenge",
        "cookies_unavailable",
        "drm_protected",
        "tls_certificate",
        "tls_handshake",
        "dns_lookup",
        "timeout",
        "connection_refused",
        "connection_reset",
        "http_error",
        "encoder_unavailable",
        "disk_full",
    }
)


def failure_code(error: BaseException) -> str | None:
    if isinstance(error, ssl.SSLCertVerificationError):
        return "tls_certificate"
    if isinstance(error, ssl.SSLError):
        return "tls_handshake"
    if isinstance(error, socket.gaierror):
        return "dns_lookup"
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, ConnectionRefusedError):
        return "connection_refused"
    if isinstance(error, ConnectionResetError):
        return "connection_reset"
    text = str(error).lower()
    if "sslcertverificationerror" in text or "certificate_verify_failed" in text:
        return "tls_certificate"
    if "gaierror" in text:
        return "dns_lookup"
    for code, needles in (
        ("no_video_stream", ("no usable video source", "no video formats")),
        ("no_audio_stream", ("no usable audio source",)),
        ("format_unavailable", ("requested format is not available",)),
        ("selector_invalid", ("could not build a safe video+audio selector",)),
        ("bot_challenge", ("confirm you're not a bot", "sign in to confirm")),
        (
            "cookies_unavailable",
            (
                "could not copy chrome cookie",
                "failed to decrypt",
                "could not find cookies",
            ),
        ),
        (
            "login_required",
            (
                "login required",
                "authentication required",
                "sign in",
            ),
        ),
        (
            "drm_protected",
            (
                "drm protected",
                "drm-protected",
            ),
        ),
        (
            "encoder_unavailable",
            (
                "unknown encoder",
                "no capable devices",
                "cannot load nvcuda",
            ),
        ),
        ("disk_full", ("no space left",)),
    ):
        if any(needle in text for needle in needles):
            return code
    return None


class SourceSelectionError(RuntimeError):
    """Local error text plus strictly numeric format-selection evidence."""

    def __init__(self, message: str, formats: list[dict]):
        super().__init__(message)
        self.format_count = min(len(formats), 10000)
        self.video_format_count = min(
            sum(f.get("vcodec") not in (None, "none", "") for f in formats), 10000
        )
        self.audio_format_count = min(
            sum(f.get("acodec") not in (None, "none", "") for f in formats), 10000
        )


@dataclass(frozen=True)
class FailureDiagnostic:
    failure_code: str | None = None
    format_count: int | None = None
    video_format_count: int | None = None
    audio_format_count: int | None = None
    tls_verify_code: int | None = None
    reason: str = "unknown"
    stage: str = "unknown"
    error_type: str | None = None
    http_status: int | None = None
    os_error: int | None = None
    tool_exit_code: int | None = None
    source_module: str | None = None
    source_line: int | None = None
    source_scope: str | None = None

    def payload(self) -> dict[str, str | int]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def validate_failure_detail(value: dict) -> FailureDiagnostic:
    if set(value) - {
        "failure_code",
        "format_count",
        "video_format_count",
        "audio_format_count",
        "tls_verify_code",
        "reason",
        "stage",
        "error_type",
        "http_status",
        "os_error",
        "tool_exit_code",
        "source_module",
        "source_line",
        "source_scope",
    }:
        raise ValueError("unsupported failure detail")
    if (
        value.get("reason", "unknown") not in FAILURE_REASONS
        or value.get("stage", "unknown") not in FAILURE_STAGES
    ):
        raise ValueError("unsupported failure detail")
    if value.get("error_type") is not None and value["error_type"] not in ERROR_TYPES:
        raise ValueError("unsupported error type")
    if (
        value.get("failure_code") is not None
        and value["failure_code"] not in FAILURE_CODES
    ):
        raise ValueError("unsupported failure code")
    location = {
        key
        for key in ("source_module", "source_line", "source_scope")
        if value.get(key) is not None
    }
    if location and (
        location != {"source_module", "source_line", "source_scope"}
        or value["source_module"] not in FIRST_PARTY_MODULES
        or value["source_scope"] != "first_party_frame"
    ):
        raise ValueError("unsupported source location")
    for key, low, high in (
        ("source_line", 1, 100000),
        ("format_count", 0, 10000),
        ("video_format_count", 0, 10000),
        ("audio_format_count", 0, 10000),
        ("tls_verify_code", 0, 65535),
        ("http_status", 100, 599),
        ("os_error", 0, 65535),
        ("tool_exit_code", -(2**31), 2**32 - 1),
    ):
        item = value.get(key)
        if item is not None and (type(item) is not int or not low <= item <= high):
            raise ValueError("unsupported failure code")
    return FailureDiagnostic(**value)


def capture_failure(
    error: BaseException, *, stage: str = "unknown"
) -> FailureDiagnostic:
    """Extract scalar machine facts; never serialize args, commands or messages."""
    facts: dict = {
        "reason": "unknown",
        "stage": stage if stage in FAILURE_STAGES else "unknown",
    }
    pending = [error]
    seen: set[int] = set()
    text_reason = "unknown"
    while pending and len(seen) < 8:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        facts.update(_first_party_location(current))
        code = failure_code(current)
        if code is not None:
            facts["failure_code"] = code
        if isinstance(current, SourceSelectionError):
            for key in ("format_count", "video_format_count", "audio_format_count"):
                facts[key] = getattr(current, key)
        if isinstance(current, ssl.SSLCertVerificationError):
            value = getattr(current, "verify_code", None)
            if type(value) is int and 0 <= value <= 65535:
                facts["tls_verify_code"] = value
        if isinstance(current, (ssl.SSLError, socket.gaierror)):
            facts["reason"] = "network"
        name = type(current).__name__
        if name in ERROR_TYPES:
            facts["error_type"] = name
        if isinstance(current, TimeoutError):
            facts["reason"] = "network"
        elif isinstance(current, PermissionError):
            facts["reason"] = "permission_denied"
        elif isinstance(current, FileNotFoundError):
            facts["reason"] = "filesystem"
        if text_reason == "unknown":
            text_reason = classify_failure(str(current))
        for attribute in ("status", "code"):
            value = getattr(current, attribute, None)
            if type(value) is int and 100 <= value <= 599:
                facts["http_status"] = value
        if (
            isinstance(current, OSError)
            and not isinstance(current, (ssl.SSLError, socket.gaierror))
            and type(current.errno) is int
            and 0 <= current.errno <= 65535
        ):
            facts["os_error"] = current.errno
        if (
            isinstance(current, subprocess.CalledProcessError)
            and type(current.returncode) is int
            and -(2**31) <= current.returncode < 2**32
        ):
            facts["tool_exit_code"] = current.returncode
        for attribute in ("__cause__", "__context__", "cause", "reason"):
            nested = getattr(current, attribute, None)
            if isinstance(nested, BaseException):
                pending.append(nested)
        # yt-dlp also preserves the underlying exception in an exc_info tuple.
        exc_info = getattr(current, "exc_info", None)
        if (
            isinstance(exc_info, tuple)
            and len(exc_info) == 3
            and isinstance(exc_info[1], BaseException)
        ):
            pending.append(exc_info[1])
    os_reason = {
        errno.ENOSPC: "disk_full",
        errno.EACCES: "permission_denied",
        errno.EPERM: "permission_denied",
        errno.EROFS: "permission_denied",
        errno.ENOENT: "filesystem",
        errno.EIO: "filesystem",
        errno.ENOMEM: "resource_exhausted",
        errno.EMFILE: "resource_exhausted",
        errno.ENFILE: "resource_exhausted",
        errno.ETIMEDOUT: "network",
        errno.ECONNRESET: "network",
        errno.ECONNREFUSED: "network",
    }.get(facts.get("os_error", -1))
    http_reason = {
        401: "authentication_required",
        404: "source_unavailable",
        410: "source_unavailable",
        429: "rate_limited",
        408: "network",
        502: "network",
        503: "network",
        504: "network",
    }.get(facts.get("http_status", -1))
    # A 403 alone does not establish whether login, geography, or policy blocked
    # access. Preserve the actual code without inventing a more precise cause.
    facts["reason"] = (
        os_reason
        or http_reason
        or (facts["reason"] if facts["reason"] != "unknown" else text_reason)
    )
    return FailureDiagnostic(**facts)


FAILURE_REASONS = frozenset(
    {
        "network",
        "rate_limited",
        "authentication_required",
        "source_unavailable",
        "disk_full",
        "permission_denied",
        "transcoding",
        "validation",
        "unknown",
        "dependency_missing",
        "unsupported_format",
        "invalid_input",
        "output_conflict",
        "source_restricted",
        "provider_extraction",
        "filesystem",
        "resource_exhausted",
    }
)


def classify_failure(message: str) -> str:
    """Best-effort classification, never an error-message sanitization/upload path."""
    text = message[:16384].casefold()
    for reason, markers in (
        (
            "dependency_missing",
            (
                "ffmpeg is required",
                "ffprobe is required",
                "yt-dlp import failed",
                "deno not found",
                "missing runtime",
                "javascript runtime",
                "js runtime",
            ),
        ),
        ("disk_full", ("no space left", "disk full", "not enough space")),
        (
            "permission_denied",
            ("permission denied", "access is denied", "read-only file system"),
        ),
        (
            "resource_exhausted",
            ("out of memory", "cannot allocate memory", "too many open files"),
        ),
        ("rate_limited", ("429", "too many requests", "rate limit")),
        (
            "source_restricted",
            (
                "not available in your country",
                "geo-restricted",
                "members-only",
                "age-restricted",
            ),
        ),
        (
            "authentication_required",
            ("sign in", "login required", "authentication", "cookies", "private video"),
        ),
        (
            "source_unavailable",
            (
                "video unavailable",
                "video has been removed",
                "video is not available",
                "404",
                "copyright",
            ),
        ),
        (
            "network",
            (
                "timed out",
                "timeout",
                "connection",
                "network",
                "unable to resolve",
                "name resolution",
                "http error 502",
                "http error 503",
                "http error 504",
            ),
        ),
        (
            "output_conflict",
            ("already exists", "output conflict", "unsafe output", "symlink"),
        ),
        (
            "filesystem",
            (
                "no such file or directory",
                "input/output error",
                "device not configured",
                "stale file handle",
            ),
        ),
        (
            "unsupported_format",
            (
                "requested format is not available",
                "unsupported codec",
                "unsupported format",
                "no video formats",
                "no usable video source",
                "no usable audio source",
            ),
        ),
        (
            "invalid_input",
            (
                "invalid url",
                "unsupported url",
                "invalid image",
                "invalid audio",
                "invalid input",
            ),
        ),
        (
            "provider_extraction",
            (
                "unable to extract",
                "signature extraction",
                "nsig extraction",
                "javascript challenge",
            ),
        ),
        (
            "validation",
            (
                "validation",
                "ffprobe",
                "invalid output",
                "corrupt",
                "does not match its export plan",
                "output duration",
                "output container",
                "output file is missing or empty",
                "output does not contain",
                "completed without producing the expected",
            ),
        ),
        ("transcoding", ("ffmpeg", "encoder", "transcod", "conversion failed")),
    ):
        if any(marker in text for marker in markers):
            return reason
    return "unknown"
