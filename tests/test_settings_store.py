from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from yt_downloader.settings_store import (
    SETTINGS_SCHEMA_VERSION,
    SettingsError,
    SettingsPersistenceOwner,
    load_settings,
    save_settings,
    settings_file_path,
)


class _Variable:
    def __init__(self, value: object) -> None:
        self.value = value
        self.callback = None

    def get(self) -> object:
        return self.value

    def trace_add(self, _mode: str, callback: object) -> str:
        self.callback = callback
        return "trace"


class _Scheduler:
    def __init__(self) -> None:
        self.pending: dict[str, object] = {}
        self.cancelled: list[str] = []
        self._next = 0

    def after(self, milliseconds: int, callback: object) -> str:
        assert milliseconds == 250
        self._next += 1
        identifier = f"after-{self._next}"
        self.pending[identifier] = callback
        return identifier

    def after_cancel(self, identifier: str) -> None:
        self.cancelled.append(identifier)
        self.pending.pop(identifier, None)


def test_settings_round_trip_is_private_and_atomic(tmp_path: Path) -> None:
    path = tmp_path / "state" / "settings.json"
    values = {
        "output_dir": str(tmp_path / "Desktop"),
        "quality": "720p HD",
        "write_thumbnail": False,
    }

    save_settings(path, values)

    assert load_settings(path) == values
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert list(path.parent.glob("*.tmp")) == []


def test_settings_path_uses_private_application_data_location(tmp_path: Path) -> None:
    assert settings_file_path(platform_name="darwin", home=tmp_path) == (
        tmp_path / "Library" / "Application Support" / "VODForge" / "settings.json"
    )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"schema_version": 999, "values": {}},
        {"schema_version": SETTINGS_SCHEMA_VERSION, "values": []},
    ],
)
def test_malformed_settings_fail_closed_without_rewriting(
    tmp_path: Path, payload: object
) -> None:
    path = tmp_path / "settings.json"
    original = json.dumps(payload).encode()
    path.write_bytes(original)

    with pytest.raises(SettingsError):
        load_settings(path)

    assert path.read_bytes() == original


def test_settings_do_not_receive_url_cookie_or_tag_fields(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    values = {"output_dir": str(tmp_path), "output_type": "MP4"}
    save_settings(path, values)

    text = path.read_text(encoding="utf-8")
    assert "url" not in text.casefold()
    assert "cookie" not in text.casefold()
    assert "tags" not in text.casefold()


def test_settings_owner_debounces_changes_and_flushes_latest_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    output = _Variable(str(tmp_path / "Desktop"))
    cover = _Variable("Custom art")
    scheduler = _Scheduler()
    owner = SettingsPersistenceOwner(path)
    owner.bind(scheduler, {"output_dir": output, "mp3_cover_art_mode": cover})

    assert callable(output.callback)
    output.callback()  # type: ignore[operator]
    first = next(iter(scheduler.pending))
    output.value = str(tmp_path / "Movies")
    output.callback()  # type: ignore[operator]

    assert first in scheduler.cancelled
    owner.flush()
    assert load_settings(path) == {
        "output_dir": str(tmp_path / "Movies"),
        "mp3_cover_art_mode": "No Art",
    }
    assert scheduler.pending == {}
