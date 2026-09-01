from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from .history import application_data_dir
from .private_files import write_private_bytes

SETTINGS_SCHEMA_VERSION = 1
MAX_SETTINGS_FILE_BYTES = 64 * 1024


class SettingsError(RuntimeError):
    """Raised when persisted preferences cannot be read or written safely."""


class _TkVariable(Protocol):
    def get(self) -> Any: ...

    def trace_add(self, mode: str, callback: Any) -> Any: ...


class _TkScheduler(Protocol):
    def after(self, milliseconds: int, callback: Any) -> str: ...

    def after_cancel(self, identifier: str) -> None: ...


def settings_file_path(**kwargs: Any) -> Path:
    return application_data_dir(**kwargs) / "settings.json"


def load_settings(path: Path) -> dict[str, Any]:
    """Load one bounded settings object; malformed files remain untouched."""

    try:
        if not path.exists():
            return {}
        if path.stat().st_size > MAX_SETTINGS_FILE_BYTES:
            raise SettingsError("VODForge settings are unexpectedly large.")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SettingsError(f"VODForge settings could not be loaded: {exc}") from exc
    if not isinstance(payload, dict):
        raise SettingsError("VODForge settings do not contain an object.")
    if payload.get("schema_version") != SETTINGS_SCHEMA_VERSION:
        raise SettingsError("VODForge settings use an unsupported schema version.")
    values = payload.get("values")
    if not isinstance(values, dict):
        raise SettingsError("VODForge settings do not contain preference values.")
    return dict(values)


def save_settings(path: Path, values: Mapping[str, Any]) -> None:
    """Atomically persist non-secret preferences with private permissions."""

    payload = {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "values": dict(values),
    }
    try:
        encoded = json.dumps(
            payload, ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")
        if len(encoded) > MAX_SETTINGS_FILE_BYTES:
            raise SettingsError("VODForge settings exceed the safe size limit.")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_private_bytes(path, encoded)
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, SettingsError):
            raise
        raise SettingsError(f"VODForge settings could not be saved: {exc}") from exc


class SettingsPersistenceOwner:
    """Own preference loading, debounced Tk observation, and private writes."""

    def __init__(self, path: Path, *, diagnostic: Any = None) -> None:
        self.path = path
        self._diagnostic = diagnostic or (lambda _message: None)
        self._scheduler: _TkScheduler | None = None
        self._variables: dict[str, _TkVariable] = {}
        self._save_after_id: str | None = None
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        try:
            return load_settings(self.path)
        except SettingsError as exc:
            self._diagnostic(str(exc))
            return {}

    def bind(
        self,
        scheduler: _TkScheduler,
        variables: Mapping[str, _TkVariable],
    ) -> None:
        self._scheduler = scheduler
        self._variables = dict(variables)
        for variable in self._variables.values():
            variable.trace_add("write", self._schedule)

    def _schedule(self, *_args: Any) -> None:
        scheduler = self._scheduler
        if scheduler is None:
            return
        with self._lock:
            if self._save_after_id is not None:
                try:
                    scheduler.after_cancel(self._save_after_id)
                except Exception as exc:  # noqa: BLE001 - Tk teardown makes IDs transient
                    self._diagnostic(
                        f"settings save timer could not be replaced: {type(exc).__name__}"
                    )
            self._save_after_id = scheduler.after(250, self.flush)

    def values(self) -> dict[str, Any]:
        values = {key: variable.get() for key, variable in self._variables.items()}
        if values.get("mp3_cover_art_mode") == "Custom art":
            values["mp3_cover_art_mode"] = "No Art"
        return values

    def flush(self) -> None:
        scheduler = self._scheduler
        with self._lock:
            pending = self._save_after_id
            self._save_after_id = None
        if pending is not None and scheduler is not None:
            try:
                scheduler.after_cancel(pending)
            except Exception as exc:  # noqa: BLE001 - Tk teardown makes IDs transient
                self._diagnostic(
                    f"settings save timer could not be cancelled: {type(exc).__name__}"
                )
        try:
            save_settings(self.path, self.values())
        except SettingsError as exc:
            self._diagnostic(str(exc))
