from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

import yt_downloader.app as app_module
from yt_downloader.quality_e2e import (
    QUALITY_E2E_ATTESTATION_PREFIX,
    QUALITY_E2E_ISOLATION_ROOT_ENV,
    QUALITY_E2E_MODE_ENV,
    QUALITY_E2E_NONCE_ENV,
    QUALITY_E2E_WINDOW_TOKEN_ENV,
    QualityE2EAttestationError,
    write_quality_e2e_startup_attestation,
)

SESSION_NONCE = "0123456789abcdef0123456789abcdef"
WINDOW_TOKEN = "VFQ-012345abcdef-L1"


class _FakeStringValue:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class _FakeApp:
    def __init__(self, *, history_path: Path, output_root: Path) -> None:
        self.history_path = history_path
        self.output_var = _FakeStringValue(str(output_root))
        self._window_title = "VODForge"

    def title(self, value: str | None = None) -> str:
        if value is not None:
            self._window_title = value
        return self._window_title


def _isolated_launch(
    tmp_path: Path,
) -> tuple[dict[str, str], _FakeApp, Path, Path, Path]:
    isolation_root = tmp_path / "isolated-run"
    home = isolation_root / "home"
    isolated_tmp = isolation_root / "tmp"
    output_root = home / "Downloads"
    application_data = home / "Library" / "Application Support" / "VODForge"
    diagnostics_path = home / "Library" / "Logs" / "VODForge" / "latest.log"
    for directory in (
        isolation_root,
        home,
        isolated_tmp,
        output_root,
        application_data,
        diagnostics_path.parent,
        home / ".local" / "share",
        home / "AppData" / "Local",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    environment = {
        QUALITY_E2E_MODE_ENV: "1",
        QUALITY_E2E_NONCE_ENV: SESSION_NONCE,
        QUALITY_E2E_WINDOW_TOKEN_ENV: WINDOW_TOKEN,
        QUALITY_E2E_ISOLATION_ROOT_ENV: str(isolation_root),
        "HOME": str(home),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "TMPDIR": str(isolated_tmp),
    }
    app = _FakeApp(
        history_path=application_data / "download-history.json",
        output_root=output_root,
    )
    return environment, app, home, application_data, diagnostics_path


def test_quality_e2e_attestation_is_inert_without_explicit_mode(tmp_path: Path) -> None:
    app = _FakeApp(
        history_path=tmp_path / "ordinary-history.json",
        output_root=tmp_path / "ordinary-output",
    )

    result = write_quality_e2e_startup_attestation(
        app,
        app_version="9.8.7-dev",
        application_data_path=tmp_path / "ordinary-data",
        diagnostics_path=tmp_path / "ordinary.log",
        environ={QUALITY_E2E_MODE_ENV: "true"},
    )

    assert result is None
    assert app.title() == "VODForge"
    assert list(tmp_path.glob(f"{QUALITY_E2E_ATTESTATION_PREFIX}*.json")) == []


def test_quality_e2e_attestation_receipts_exact_isolated_startup(
    tmp_path: Path,
) -> None:
    environment, app, home, application_data, diagnostics_path = _isolated_launch(
        tmp_path
    )

    result = write_quality_e2e_startup_attestation(
        app,
        app_version="9.8.7-dev",
        application_data_path=application_data,
        diagnostics_path=diagnostics_path,
        environ=environment,
        home=home,
        executable=Path("/Applications/VODForge.app/Contents/MacOS/VODForge"),
        pid=4321,
        ppid=1234,
        recorded_at="2026-08-31T01:02:03Z",
    )

    expected = Path(environment["TMPDIR"]) / (
        f"{QUALITY_E2E_ATTESTATION_PREFIX}{SESSION_NONCE}.json"
    )
    assert result == expected
    assert app.title() == f"VODForge [{WINDOW_TOKEN}]"
    payload = json.loads(expected.read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": "1.0.0",
        "session_nonce": SESSION_NONCE,
        "pid": 4321,
        "ppid": 1234,
        "executable": "/Applications/VODForge.app/Contents/MacOS/VODForge",
        "app_version": "9.8.7-dev",
        "window_title": f"VODForge [{WINDOW_TOKEN}]",
        "home": str(home),
        "application_data_dir": str(application_data),
        "history_path": str(application_data / "download-history.json"),
        "diagnostics_dir": str(diagnostics_path.parent),
        "diagnostics_path": str(diagnostics_path),
        "output_root": str(home / "Downloads"),
        "tmp_dir": environment["TMPDIR"],
        "recorded_at": "2026-08-31T01:02:03Z",
    }
    if os.name != "nt":
        assert stat.S_IMODE(expected.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("environment_key", "value"),
    [
        (QUALITY_E2E_NONCE_ENV, "../escape"),
        (QUALITY_E2E_NONCE_ENV, "A" * 32),
        (QUALITY_E2E_WINDOW_TOKEN_ENV, "bad token with spaces"),
        ("TMPDIR", "relative/tmp"),
    ],
)
def test_quality_e2e_attestation_rejects_invalid_contract_values(
    tmp_path: Path, environment_key: str, value: str
) -> None:
    environment, app, home, application_data, diagnostics_path = _isolated_launch(
        tmp_path
    )
    environment[environment_key] = value

    with pytest.raises(QualityE2EAttestationError):
        write_quality_e2e_startup_attestation(
            app,
            app_version="9.8.7-dev",
            application_data_path=application_data,
            diagnostics_path=diagnostics_path,
            environ=environment,
            home=home,
        )

    assert app.title() == "VODForge"
    assert list((tmp_path / "isolated-run").rglob("*.json")) == []


@pytest.mark.parametrize(
    "environment_key",
    [
        QUALITY_E2E_NONCE_ENV,
        QUALITY_E2E_WINDOW_TOKEN_ENV,
        QUALITY_E2E_ISOLATION_ROOT_ENV,
        "XDG_DATA_HOME",
        "LOCALAPPDATA",
        "TMPDIR",
    ],
)
def test_quality_e2e_attestation_rejects_missing_contract_values(
    tmp_path: Path, environment_key: str
) -> None:
    environment, app, home, application_data, diagnostics_path = _isolated_launch(
        tmp_path
    )
    environment.pop(environment_key)

    with pytest.raises(QualityE2EAttestationError, match="missing required"):
        write_quality_e2e_startup_attestation(
            app,
            app_version="9.8.7-dev",
            application_data_path=application_data,
            diagnostics_path=diagnostics_path,
            environ=environment,
            home=home,
        )


def test_quality_e2e_attestation_rejects_ordinary_home_and_output(
    tmp_path: Path,
) -> None:
    environment, app, _home, application_data, diagnostics_path = _isolated_launch(
        tmp_path
    )
    ordinary_home = tmp_path / "ordinary-home"
    ordinary_output = ordinary_home / "Downloads"
    ordinary_output.mkdir(parents=True)
    app.output_var.value = str(ordinary_output)

    with pytest.raises(QualityE2EAttestationError, match="HOME and TMPDIR"):
        write_quality_e2e_startup_attestation(
            app,
            app_version="9.8.7-dev",
            application_data_path=application_data,
            diagnostics_path=diagnostics_path,
            environ=environment,
            home=ordinary_home,
        )


def test_quality_e2e_attestation_never_follows_existing_target_symlink(
    tmp_path: Path,
) -> None:
    environment, app, home, application_data, diagnostics_path = _isolated_launch(
        tmp_path
    )
    outside = tmp_path / "outside.json"
    outside.write_text("untouched", encoding="utf-8")
    target = Path(environment["TMPDIR"]) / (
        f"{QUALITY_E2E_ATTESTATION_PREFIX}{SESSION_NONCE}.json"
    )
    try:
        target.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"file symlinks are unavailable on this host: {exc}")

    with pytest.raises(QualityE2EAttestationError, match="new private file"):
        write_quality_e2e_startup_attestation(
            app,
            app_version="9.8.7-dev",
            application_data_path=application_data,
            diagnostics_path=diagnostics_path,
            environ=environment,
            home=home,
        )

    assert target.is_symlink()
    assert outside.read_text(encoding="utf-8") == "untouched"


def test_quality_e2e_attestation_rejects_symlinked_isolation_root(
    tmp_path: Path,
) -> None:
    environment, app, home, application_data, diagnostics_path = _isolated_launch(
        tmp_path
    )
    linked_root = tmp_path / "linked-run"
    try:
        linked_root.symlink_to(tmp_path / "isolated-run", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable on this host: {exc}")
    environment[QUALITY_E2E_ISOLATION_ROOT_ENV] = str(linked_root)

    with pytest.raises(QualityE2EAttestationError, match="symlink components"):
        write_quality_e2e_startup_attestation(
            app,
            app_version="9.8.7-dev",
            application_data_path=application_data,
            diagnostics_path=diagnostics_path,
            environ=environment,
            home=home,
        )


def test_main_destroys_rejected_quality_e2e_app_before_mainloop(monkeypatch) -> None:
    class FakeRoot:
        destroyed = False
        mainloop_called = False

        def destroy(self) -> None:
            self.destroyed = True

        def mainloop(self) -> None:
            self.mainloop_called = True

    root = FakeRoot()
    monkeypatch.setattr(app_module, "DownloaderApp", lambda: root)
    monkeypatch.setattr(
        app_module,
        "write_quality_e2e_startup_attestation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            QualityE2EAttestationError("not isolated")
        ),
    )
    monkeypatch.setattr(app_module.sys, "argv", ["VODForge"])

    with pytest.raises(SystemExit, match="quality-E2E startup rejected"):
        app_module.main()

    assert root.destroyed is True
    assert root.mainloop_called is False
