"""Immutable machine-readable failure facts. Raw diagnostics stay local."""

import errno

# Used only to classify exceptions, never to execute a process.
import subprocess  # nosec B404
from dataclasses import asdict, dataclass

FAILURE_STAGES = frozenset({"preparation", "processing", "batch", "unknown"})
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
    }
)


@dataclass(frozen=True)
class FailureDiagnostic:
    reason: str = "unknown"
    stage: str = "unknown"
    error_type: str | None = None
    http_status: int | None = None
    os_error: int | None = None
    tool_exit_code: int | None = None

    def payload(self) -> dict[str, str | int]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def validate_failure_detail(value: dict) -> FailureDiagnostic:
    if set(value) - {
        "reason",
        "stage",
        "error_type",
        "http_status",
        "os_error",
        "tool_exit_code",
    }:
        raise ValueError("unsupported failure detail")
    if (
        value.get("reason", "unknown") not in FAILURE_REASONS
        or value.get("stage", "unknown") not in FAILURE_STAGES
    ):
        raise ValueError("unsupported failure detail")
    if value.get("error_type") is not None and value["error_type"] not in ERROR_TYPES:
        raise ValueError("unsupported error type")
    for key, low, high in (
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
