from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from yt_downloader.qt_quick import main as qt_main
from yt_downloader.quality_e2e import QualityE2EAttestationError


class Window:
    def __init__(self) -> None:
        self._title = "VODForge"

    def title(self) -> str:
        return self._title

    def setTitle(self, title: str) -> None:
        self._title = title


def test_qt_launch_uses_existing_isolation_attestor(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "run"
    home = root / "home"
    temporary = root / "tmp"
    app_data = home / "Library" / "Application Support" / "VODForge"
    diagnostics = home / "Library" / "Logs" / "VODForge" / "latest.log"
    output = home / "Downloads"
    for directory in (
        temporary,
        app_data,
        diagnostics.parent,
        output,
        home / ".local" / "share",
        home / "AppData" / "Local",
    ):
        directory.mkdir(parents=True)
    values = {
        "VODFORGE_QUALITY_E2E": "1",
        "VODFORGE_QUALITY_E2E_SESSION_NONCE": "0123456789abcdef0123456789abcdef",
        "VODFORGE_QUALITY_E2E_WINDOW_TOKEN": "VFQ-012345abcdef-L1",
        "VODFORGE_QUALITY_E2E_ISOLATION_ROOT": str(root),
        "HOME": str(home),
        "TMPDIR": str(temporary),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(qt_main, "application_data_dir", lambda: app_data)
    monkeypatch.setattr(qt_main, "DIAGNOSTICS_LOG_PATH", diagnostics)
    bridge = SimpleNamespace(
        _runtime=SimpleNamespace(history_path=app_data / "download-history.json"),
        _output_path=str(output),
        outputPath=str(home / "unrelated recovery destination"),
    )
    window = Window()

    receipt = qt_main.attest_qt_launch(bridge, window)

    assert receipt is not None
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["history_path"] == str(bridge._runtime.history_path)
    assert payload["renderer"] == "qt"
    assert payload["output_root"] == str(output)
    assert window.title() == "VODForge [VFQ-012345abcdef-L1]"
    assert receipt.parent == temporary


def test_qt_launch_accepts_persisted_isolated_output_folder(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "run"
    home = root / "home"
    temporary = root / "tmp"
    app_data = home / "Library" / "Application Support" / "VODForge"
    diagnostics = home / "Library" / "Logs" / "VODForge" / "latest.log"
    output = home / "Downloads" / "chosen-folder"
    for directory in (
        temporary,
        app_data,
        diagnostics.parent,
        output,
        home / ".local" / "share",
        home / "AppData" / "Local",
    ):
        directory.mkdir(parents=True)
    values = {
        "VODFORGE_QUALITY_E2E": "1",
        "VODFORGE_QUALITY_E2E_SESSION_NONCE": "0123456789abcdef0123456789abcdef",
        "VODFORGE_QUALITY_E2E_WINDOW_TOKEN": "VFQ-012345abcdef-L2",
        "VODFORGE_QUALITY_E2E_ISOLATION_ROOT": str(root),
        "HOME": str(home),
        "TMPDIR": str(temporary),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(qt_main, "application_data_dir", lambda: app_data)
    monkeypatch.setattr(qt_main, "DIAGNOSTICS_LOG_PATH", diagnostics)
    bridge = SimpleNamespace(
        _runtime=SimpleNamespace(history_path=app_data / "download-history.json"),
        _output_path=str(output),
        outputPath=str(output),
    )

    receipt = qt_main.attest_qt_launch(bridge, Window())

    assert receipt is not None
    assert json.loads(receipt.read_text(encoding="utf-8"))["output_root"] == str(output)


def test_qt_launch_rejects_output_outside_isolation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VODFORGE_QUALITY_E2E", "1")
    bridge = SimpleNamespace(
        _runtime=SimpleNamespace(history_path=tmp_path / "history.json"),
        _output_path=str(tmp_path / "output"),
    )

    with pytest.raises(QualityE2EAttestationError):
        qt_main.attest_qt_launch(bridge, Window())
