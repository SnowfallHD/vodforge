from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, overload

QUALITY_E2E_MODE_ENV = "VODFORGE_QUALITY_E2E"
QUALITY_E2E_NONCE_ENV = "VODFORGE_QUALITY_E2E_SESSION_NONCE"
# This is the name of a visible window-identity environment field, not a credential.
QUALITY_E2E_WINDOW_TOKEN_ENV = "VODFORGE_QUALITY_E2E_WINDOW_TOKEN"  # nosec B105
QUALITY_E2E_LAUNCH_ID_ENV = "VODFORGE_QUALITY_E2E_LAUNCH_ID"
QUALITY_E2E_ISOLATION_ROOT_ENV = "VODFORGE_QUALITY_E2E_ISOLATION_ROOT"
QUALITY_E2E_SCHEMA_VERSION = "1.0.0"
QUALITY_E2E_ATTESTATION_PREFIX = "vodforge-e2e-attestation-"
QUALITY_E2E_LIBRARY_VISIBILITY_PREFIX = "vodforge-e2e-library-visibility-"
QUALITY_E2E_LIBRARY_BOTTOM_ALIGNMENT_TOLERANCE_PX = 2
QUALITY_E2E_MIN_TITLE_VISIBLE_LINES = 2

_NONCE_RE = re.compile(r"[0-9a-f]{32}")
_WINDOW_TOKEN_RE = re.compile(r"[A-Za-z0-9._-]{8,64}")


class QualityE2EAttestationError(RuntimeError):
    """Raised when an explicitly requested quality-E2E launch is not isolated."""


class _StringValue(Protocol):
    def get(self) -> str: ...


class QualityE2EApp(Protocol):
    @property
    def history_path(self) -> Path: ...

    @property
    def output_var(self) -> _StringValue: ...

    @overload
    def title(self, value: None = None) -> str: ...

    @overload
    def title(self, value: str) -> None: ...


class _GeometryWidget(Protocol):
    def cget(self, key: str) -> object: ...

    def winfo_ismapped(self) -> bool: ...

    def winfo_viewable(self) -> bool: ...

    def winfo_rootx(self) -> int: ...

    def winfo_rooty(self) -> int: ...

    def winfo_width(self) -> int: ...

    def winfo_height(self) -> int: ...


class _DescriptionWidget(_GeometryWidget, Protocol):
    def get(self, start: str, end: str) -> str: ...

    def dlineinfo(self, index: str) -> tuple[int, ...] | None: ...


def quality_e2e_mode_enabled(environ: Mapping[str, str] | None = None) -> bool:
    environment = os.environ if environ is None else environ
    return environment.get(QUALITY_E2E_MODE_ENV) == "1"


def _required_environment_value(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "")
    if not value:
        raise QualityE2EAttestationError(f"missing required environment value: {name}")
    return value


def _canonical_path(value: str | Path, *, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise QualityE2EAttestationError(f"{label} must be an absolute path")
    normalized = Path(os.path.normpath(str(path)))
    if normalized != path:
        raise QualityE2EAttestationError(f"{label} must be lexically canonical")
    return path


def _existing_directory_without_symlinks(value: str | Path, *, label: str) -> Path:
    path = _canonical_path(value, label=label)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise QualityE2EAttestationError(
            f"{label} is not an existing directory"
        ) from exc
    if resolved != path:
        raise QualityE2EAttestationError(f"{label} must not contain symlink components")
    try:
        mode = path.stat(follow_symlinks=False).st_mode
    except OSError as exc:
        raise QualityE2EAttestationError(f"{label} could not be inspected") from exc
    if not stat.S_ISDIR(mode):
        raise QualityE2EAttestationError(f"{label} is not a directory")
    return path


def _require_exact_path(actual: Path, expected: Path, *, label: str) -> Path:
    canonical = _canonical_path(actual, label=label)
    if canonical != expected:
        raise QualityE2EAttestationError(
            f"{label} does not match the isolated quality-E2E path"
        )
    if canonical.resolve(strict=False) != canonical:
        raise QualityE2EAttestationError(f"{label} must not contain symlink components")
    return canonical


def _require_path_beneath(path: Path, root: Path, *, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise QualityE2EAttestationError(
            f"{label} escapes the isolated quality-E2E root"
        ) from exc


def _write_exclusive_private_json(path: Path, payload: dict[str, object]) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise QualityE2EAttestationError(
            "quality-E2E attestation target must be a new private file"
        ) from exc
    write_error: OSError | None = None
    try:
        if os.name != "nt" and hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        remaining = memoryview(encoded)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("quality-E2E attestation write did not advance")
            remaining = remaining[written:]
        os.fsync(descriptor)
    except OSError as exc:
        write_error = exc
    finally:
        os.close(descriptor)
    if write_error is not None:
        try:
            path.unlink()
        except OSError:
            pass
        raise QualityE2EAttestationError(
            "quality-E2E attestation could not be written completely"
        ) from write_error

    try:
        file_stat = path.stat(follow_symlinks=False)
    except OSError as exc:
        try:
            path.unlink()
        except OSError:
            pass
        raise QualityE2EAttestationError(
            "quality-E2E attestation could not be inspected"
        ) from exc
    permissions_invalid = os.name != "nt" and stat.S_IMODE(file_stat.st_mode) != 0o600
    if not stat.S_ISREG(file_stat.st_mode) or permissions_invalid:
        try:
            path.unlink()
        except OSError:
            pass
        raise QualityE2EAttestationError(
            "quality-E2E attestation is not a private regular file"
        )


def _widget_bounds(widget: _GeometryWidget) -> dict[str, int]:
    return {
        "x": int(widget.winfo_rootx()),
        "y": int(widget.winfo_rooty()),
        "width": int(widget.winfo_width()),
        "height": int(widget.winfo_height()),
    }


def _bounds_inside(child: Mapping[str, int], parent: Mapping[str, int]) -> bool:
    return (
        child["x"] >= parent["x"]
        and child["y"] >= parent["y"]
        and child["x"] + child["width"] <= parent["x"] + parent["width"]
        and child["y"] + child["height"] <= parent["y"] + parent["height"]
    )


def write_quality_e2e_library_visibility_receipt(
    *,
    details: _GeometryWidget,
    library_table: _GeometryWidget,
    tags_body: _GeometryWidget,
    description_heading: _GeometryWidget,
    description: _DescriptionWidget,
    full_title: str,
    displayed_title: str,
    displayed_title_visible_lines: int,
    full_location: str,
    displayed_location: str,
    expected_details_height: int,
    environ: Mapping[str, str] | None = None,
    pid: int | None = None,
    recorded_at: str | None = None,
) -> Path | None:
    """Receipt real Tk visibility without changing ordinary application behavior."""

    environment = os.environ if environ is None else environ
    if not quality_e2e_mode_enabled(environment):
        return None
    nonce = _required_environment_value(environment, QUALITY_E2E_NONCE_ENV)
    if _NONCE_RE.fullmatch(nonce) is None:
        raise QualityE2EAttestationError("quality-E2E session nonce is invalid")
    window_token = _required_environment_value(
        environment, QUALITY_E2E_WINDOW_TOKEN_ENV
    )
    if _WINDOW_TOKEN_RE.fullmatch(window_token) is None:
        raise QualityE2EAttestationError("quality-E2E window token is invalid")
    launch_id = _required_environment_value(environment, QUALITY_E2E_LAUNCH_ID_ENV)
    if _NONCE_RE.fullmatch(launch_id) is None:
        raise QualityE2EAttestationError("quality-E2E launch ID is invalid")
    isolation_root = _existing_directory_without_symlinks(
        _required_environment_value(environment, QUALITY_E2E_ISOLATION_ROOT_ENV),
        label="quality-E2E isolation root",
    )
    tmp_path = _existing_directory_without_symlinks(
        _required_environment_value(environment, "TMPDIR"),
        label="quality-E2E temporary directory",
    )
    if tmp_path != isolation_root / "tmp":
        raise QualityE2EAttestationError(
            "quality-E2E temporary directory does not belong to the isolation root"
        )

    if isinstance(displayed_title_visible_lines, bool) or not isinstance(
        displayed_title_visible_lines, int
    ):
        raise QualityE2EAttestationError(
            "quality-E2E displayed title visible-line count is invalid"
        )

    details_bounds = _widget_bounds(details)
    library_table_bounds = _widget_bounds(library_table)
    try:
        configured_details_height = int(str(details.cget("height")))
    except (TypeError, ValueError) as exc:
        raise QualityE2EAttestationError(
            "quality-E2E Selected Item configured height is invalid"
        ) from exc
    heading_bounds = _widget_bounds(description_heading)
    tags_bounds = _widget_bounds(tags_body)
    description_bounds = _widget_bounds(description)
    description_bottom_px = description_bounds["y"] + description_bounds["height"]
    library_table_bottom_px = library_table_bounds["y"] + library_table_bounds["height"]
    description_table_bottom_delta_px = description_bottom_px - library_table_bottom_px
    description_bottom_aligned_with_library_table = bool(
        abs(description_table_bottom_delta_px)
        <= QUALITY_E2E_LIBRARY_BOTTOM_ALIGNMENT_TOLERANCE_PX
    )
    description_tags_height_delta_px = (
        description_bounds["height"] - tags_bounds["height"]
    )
    description_body_larger_than_tags_body = description_tags_height_delta_px > 0
    first_line = description.dlineinfo("1.0")
    first_line_visible = bool(
        first_line is not None
        and len(first_line) >= 4
        and int(first_line[1]) >= 0
        and int(first_line[1]) + int(first_line[3]) <= description_bounds["height"]
    )
    description_text = description.get("1.0", "end-1c")
    heading_fully_inside = _bounds_inside(heading_bounds, details_bounds)
    body_fully_inside = _bounds_inside(description_bounds, details_bounds)
    tags_fully_inside = _bounds_inside(tags_bounds, details_bounds)
    heading_visible = bool(
        description_heading.winfo_ismapped() and description_heading.winfo_viewable()
    )
    body_visible = bool(description.winfo_ismapped() and description.winfo_viewable())
    library_table_visible = bool(
        library_table.winfo_ismapped() and library_table.winfo_viewable()
    )
    tags_visible = bool(tags_body.winfo_ismapped() and tags_body.winfo_viewable())
    path_ellipsized = bool(
        full_location
        and displayed_location != full_location
        and displayed_location.endswith("…")
    )
    title_ellipsized = bool(
        full_title and displayed_title != full_title and displayed_title.endswith("…")
    )
    title_minimum_visible_lines_preserved = (
        displayed_title_visible_lines >= QUALITY_E2E_MIN_TITLE_VISIBLE_LINES
    )
    fixed_height_preserved = configured_details_height == int(expected_details_height)
    verified = bool(
        description_text.strip()
        and heading_visible
        and body_visible
        and library_table_visible
        and tags_visible
        and heading_fully_inside
        and tags_fully_inside
        and body_fully_inside
        and description_bottom_aligned_with_library_table
        and description_body_larger_than_tags_body
        and first_line_visible
        and path_ellipsized
        and title_ellipsized
        and title_minimum_visible_lines_preserved
        and fixed_height_preserved
    )
    payload: dict[str, object] = {
        "schema_version": QUALITY_E2E_SCHEMA_VERSION,
        "session_nonce": nonce,
        "launch_id": launch_id,
        "window_token": window_token,
        "pid": os.getpid() if pid is None else int(pid),
        "details_bounds": details_bounds,
        "library_table_bounds": library_table_bounds,
        "tags_body_bounds": tags_bounds,
        "description_heading_bounds": heading_bounds,
        "description_bounds": description_bounds,
        "details_height_px": details_bounds["height"],
        "details_allocated_height_px": details_bounds["height"],
        "details_configured_height_px": configured_details_height,
        "expected_details_height_px": int(expected_details_height),
        "fixed_height_preserved": fixed_height_preserved,
        "description_heading_mapped_and_viewable": heading_visible,
        "description_body_mapped_and_viewable": body_visible,
        "library_table_mapped_and_viewable": library_table_visible,
        "tags_body_mapped_and_viewable": tags_visible,
        "description_heading_fully_inside_details": heading_fully_inside,
        "tags_body_fully_inside_details": tags_fully_inside,
        "description_body_fully_inside_details": body_fully_inside,
        "description_bottom_px": description_bottom_px,
        "library_table_bottom_px": library_table_bottom_px,
        "description_table_bottom_delta_px": description_table_bottom_delta_px,
        "description_table_bottom_tolerance_px": (
            QUALITY_E2E_LIBRARY_BOTTOM_ALIGNMENT_TOLERANCE_PX
        ),
        "description_bottom_aligned_with_library_table": (
            description_bottom_aligned_with_library_table
        ),
        "description_body_height_px": description_bounds["height"],
        "tags_body_height_px": tags_bounds["height"],
        "description_tags_height_delta_px": description_tags_height_delta_px,
        "description_body_larger_than_tags_body": (
            description_body_larger_than_tags_body
        ),
        "description_first_line_visible": first_line_visible,
        "description_sha256": hashlib.sha256(
            description_text.encode("utf-8")
        ).hexdigest(),
        "description_length": len(description_text),
        "path_ellipsized": path_ellipsized,
        "title_ellipsized": title_ellipsized,
        "full_title_sha256": hashlib.sha256(full_title.encode("utf-8")).hexdigest(),
        "displayed_title_visible_lines": displayed_title_visible_lines,
        "minimum_displayed_title_visible_lines": (QUALITY_E2E_MIN_TITLE_VISIBLE_LINES),
        "title_minimum_visible_lines_preserved": (
            title_minimum_visible_lines_preserved
        ),
        "verified": verified,
        "recorded_at": recorded_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    filename = f"{QUALITY_E2E_LIBRARY_VISIBILITY_PREFIX}{nonce}-{window_token}.json"
    receipt_path = tmp_path / filename
    if receipt_path.parent != tmp_path or receipt_path.name != filename:
        raise QualityE2EAttestationError(
            "quality-E2E Library visibility receipt path is invalid"
        )
    _write_exclusive_private_json(receipt_path, payload)
    return receipt_path


def write_quality_e2e_startup_attestation(
    app: QualityE2EApp,
    *,
    app_version: str,
    application_data_path: Path,
    diagnostics_path: Path,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    executable: Path | None = None,
    pid: int | None = None,
    ppid: int | None = None,
    recorded_at: str | None = None,
) -> Path | None:
    """Attest one isolated app launch; remain inert outside explicit E2E mode."""
    environment = os.environ if environ is None else environ
    if not quality_e2e_mode_enabled(environment):
        return None

    nonce = _required_environment_value(environment, QUALITY_E2E_NONCE_ENV)
    if _NONCE_RE.fullmatch(nonce) is None:
        raise QualityE2EAttestationError(
            "quality-E2E session nonce must be 32 lowercase hexadecimal characters"
        )
    window_token = _required_environment_value(
        environment, QUALITY_E2E_WINDOW_TOKEN_ENV
    )
    if _WINDOW_TOKEN_RE.fullmatch(window_token) is None:
        raise QualityE2EAttestationError("quality-E2E window token is invalid")

    isolation_root = _existing_directory_without_symlinks(
        _required_environment_value(environment, QUALITY_E2E_ISOLATION_ROOT_ENV),
        label="quality-E2E isolation root",
    )
    expected_home = isolation_root / "home"
    expected_tmp = isolation_root / "tmp"
    home_path = _existing_directory_without_symlinks(
        Path.home() if home is None else home, label="quality-E2E home"
    )
    tmp_path = _existing_directory_without_symlinks(
        _required_environment_value(environment, "TMPDIR"),
        label="quality-E2E temporary directory",
    )
    if home_path != expected_home or tmp_path != expected_tmp:
        raise QualityE2EAttestationError(
            "HOME and TMPDIR must be the isolated quality-E2E home and tmp directories"
        )

    expected_xdg = home_path / ".local" / "share"
    expected_local_app_data = home_path / "AppData" / "Local"
    _require_exact_path(
        _canonical_path(
            _required_environment_value(environment, "XDG_DATA_HOME"),
            label="XDG_DATA_HOME",
        ),
        expected_xdg,
        label="XDG_DATA_HOME",
    )
    _require_exact_path(
        _canonical_path(
            _required_environment_value(environment, "LOCALAPPDATA"),
            label="LOCALAPPDATA",
        ),
        expected_local_app_data,
        label="LOCALAPPDATA",
    )

    app_data = _canonical_path(application_data_path, label="application-data path")
    history_path = _canonical_path(app.history_path, label="history path")
    diagnostic_file = _canonical_path(diagnostics_path, label="diagnostics path")
    output_root = _canonical_path(app.output_var.get(), label="default output root")
    for label, path in (
        ("application-data path", app_data),
        ("history path", history_path),
        ("diagnostics path", diagnostic_file),
        ("default output root", output_root),
    ):
        _require_path_beneath(path, home_path, label=label)
        if path.resolve(strict=False) != path:
            raise QualityE2EAttestationError(
                f"{label} must not contain symlink components"
            )
    if history_path != app_data / "download-history.json":
        raise QualityE2EAttestationError(
            "history path does not belong to the isolated application-data directory"
        )
    expected_output_root = home_path / "Downloads"
    if output_root != expected_output_root:
        raise QualityE2EAttestationError(
            "default output root does not match the isolated Downloads directory"
        )
    _existing_directory_without_symlinks(output_root, label="default output root")

    window_title = f"VODForge [{window_token}]"
    app.title(window_title)
    if app.title() != window_title:
        raise QualityE2EAttestationError("quality-E2E window title was not applied")

    attestation_path = tmp_path / f"{QUALITY_E2E_ATTESTATION_PREFIX}{nonce}.json"
    if (
        attestation_path.parent != tmp_path
        or attestation_path.name != f"{QUALITY_E2E_ATTESTATION_PREFIX}{nonce}.json"
    ):
        raise QualityE2EAttestationError("quality-E2E attestation path is invalid")
    executable_path = _canonical_path(
        Path(sys.executable) if executable is None else executable,
        label="runtime executable",
    )
    payload: dict[str, object] = {
        "schema_version": QUALITY_E2E_SCHEMA_VERSION,
        "session_nonce": nonce,
        "pid": os.getpid() if pid is None else pid,
        "ppid": os.getppid() if ppid is None else ppid,
        "executable": str(executable_path),
        "app_version": app_version,
        "window_title": window_title,
        "home": str(home_path),
        "application_data_dir": str(app_data),
        "history_path": str(history_path),
        "diagnostics_dir": str(diagnostic_file.parent),
        "diagnostics_path": str(diagnostic_file),
        "output_root": str(output_root),
        "tmp_dir": str(tmp_path),
        "recorded_at": recorded_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    _write_exclusive_private_json(attestation_path, payload)
    return attestation_path
