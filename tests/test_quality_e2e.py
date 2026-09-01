from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

import yt_downloader.app as app_module
from yt_downloader.quality_e2e import (
    QUALITY_E2E_ATTESTATION_PREFIX,
    QUALITY_E2E_ISOLATION_ROOT_ENV,
    QUALITY_E2E_LAUNCH_ID_ENV,
    QUALITY_E2E_LIBRARY_BOTTOM_ALIGNMENT_TOLERANCE_PX,
    QUALITY_E2E_LIBRARY_VISIBILITY_PREFIX,
    QUALITY_E2E_MIN_TITLE_VISIBLE_LINES,
    QUALITY_E2E_MODE_ENV,
    QUALITY_E2E_NONCE_ENV,
    QUALITY_E2E_WINDOW_TOKEN_ENV,
    QualityE2EAttestationError,
    write_quality_e2e_library_visibility_receipt,
    write_quality_e2e_startup_attestation,
)

SESSION_NONCE = "0123456789abcdef0123456789abcdef"
WINDOW_TOKEN = "VFQ-012345abcdef-L1"
LAUNCH_ID = "fedcba9876543210fedcba9876543210"


def _clean_library_invariant_receipt() -> SimpleNamespace:
    return SimpleNamespace(
        row_count=1,
        canonical_run_ids=("run-1",),
        projected_run_ids=("run-1",),
        statuses=("Completed",),
        violation_codes=(),
    )


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


class _FakeWidget:
    def __init__(
        self,
        *,
        x: int,
        y: int,
        width: int,
        height: int,
        mapped: bool = True,
        viewable: bool = True,
        configured_height: int | None = None,
    ) -> None:
        self.bounds = (x, y, width, height)
        self.mapped = mapped
        self.viewable = viewable
        self.configured_height = (
            height if configured_height is None else configured_height
        )

    def cget(self, key: str) -> object:
        if key != "height":
            raise KeyError(key)
        return self.configured_height

    def winfo_ismapped(self) -> bool:
        return self.mapped

    def winfo_viewable(self) -> bool:
        return self.viewable

    def winfo_rootx(self) -> int:
        return self.bounds[0]

    def winfo_rooty(self) -> int:
        return self.bounds[1]

    def winfo_width(self) -> int:
        return self.bounds[2]

    def winfo_height(self) -> int:
        return self.bounds[3]


class _FakeDescriptionWidget(_FakeWidget):
    def __init__(self, *, text: str, first_line: tuple[int, ...] | None, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.first_line = first_line

    def get(self, _start: str, _end: str) -> str:
        return self.text

    def dlineinfo(self, _index: str) -> tuple[int, ...] | None:
        return self.first_line


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
        QUALITY_E2E_LAUNCH_ID_ENV: LAUNCH_ID,
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


def test_quality_e2e_library_visibility_receipts_real_widget_geometry(
    tmp_path: Path,
) -> None:
    environment, _app, _home, _application_data, _diagnostics = _isolated_launch(
        tmp_path
    )
    description_text = "This packaged Description must remain visibly reachable."

    result = write_quality_e2e_library_visibility_receipt(
        details=_FakeWidget(
            x=100,
            y=100,
            width=410,
            height=390,
            configured_height=360,
        ),
        library_table=_FakeWidget(x=100, y=180, width=900, height=247),
        tags_body=_FakeWidget(x=110, y=205, width=385, height=72),
        description_heading=_FakeWidget(x=110, y=285, width=130, height=18),
        description=_FakeDescriptionWidget(
            x=110,
            y=307,
            width=385,
            height=120,
            text=description_text,
            first_line=(9, 7, 250, 16, 12),
        ),
        full_title="An intentionally extreme title " * 8,
        displayed_title="An intentionally extreme title…",
        displayed_title_visible_lines=2,
        full_location="Saved in /an/intentionally/extreme/output/path/" * 5,
        displayed_location="Saved in /an/intentionally/extreme…",
        expected_details_height=360,
        overview=_FakeWidget(x=100, y=100, width=410, height=101),
        location_label=_FakeWidget(x=110, y=178, width=250, height=18),
        library_invariant_receipt=_clean_library_invariant_receipt(),
        environ=environment,
        pid=4321,
        recorded_at="2026-08-31T06:00:00Z",
    )

    expected = Path(environment["TMPDIR"]) / (
        f"{QUALITY_E2E_LIBRARY_VISIBILITY_PREFIX}{SESSION_NONCE}-{WINDOW_TOKEN}.json"
    )
    assert result == expected
    payload = json.loads(expected.read_text(encoding="utf-8"))
    assert payload["verified"] is True
    assert payload["fixed_height_preserved"] is True
    assert payload["details_allocated_height_px"] == 390
    assert payload["details_configured_height_px"] == 360
    assert payload["description_heading_fully_inside_details"] is True
    assert payload["description_body_fully_inside_details"] is True
    assert payload["library_table_mapped_and_viewable"] is True
    assert payload["tags_body_mapped_and_viewable"] is True
    assert payload["tags_body_fully_inside_details"] is True
    assert payload["description_bottom_px"] == 427
    assert payload["library_table_bottom_px"] == 427
    assert payload["description_table_bottom_delta_px"] == 0
    assert payload["description_table_bottom_tolerance_px"] == (
        QUALITY_E2E_LIBRARY_BOTTOM_ALIGNMENT_TOLERANCE_PX
    )
    assert payload["description_bottom_aligned_with_library_table"] is True
    assert payload["description_body_height_px"] == 120
    assert payload["tags_body_height_px"] == 72
    assert payload["description_tags_height_delta_px"] == 48
    assert payload["description_body_larger_than_tags_body"] is True
    assert payload["description_first_line_visible"] is True
    assert payload["path_ellipsized"] is True
    assert payload["location_text_policy_satisfied"] is True
    assert payload["location_mapped_and_viewable"] is True
    assert payload["location_fully_inside_overview"] is True
    assert payload["location_fully_inside_details"] is True
    assert payload["title_ellipsized"] is True
    assert payload["displayed_title_visible_lines"] == 2
    assert payload["minimum_displayed_title_visible_lines"] == (
        QUALITY_E2E_MIN_TITLE_VISIBLE_LINES
    )
    assert payload["title_minimum_visible_lines_preserved"] is True
    assert payload["launch_id"] == LAUNCH_ID
    assert payload["pid"] == 4321
    if os.name != "nt":
        assert stat.S_IMODE(expected.stat().st_mode) == 0o600


def test_quality_e2e_library_visibility_requires_complete_terminal_status(
    tmp_path: Path,
) -> None:
    environment, _app, _home, _application_data, _diagnostics = _isolated_launch(
        tmp_path
    )
    full_status = "Skipped — Video skipped by user"

    result = write_quality_e2e_library_visibility_receipt(
        details=_FakeWidget(
            x=100,
            y=100,
            width=410,
            height=390,
            configured_height=360,
        ),
        library_table=_FakeWidget(x=100, y=180, width=900, height=247),
        tags_body=_FakeWidget(x=110, y=205, width=385, height=72),
        description_heading=_FakeWidget(x=110, y=285, width=130, height=18),
        description=_FakeDescriptionWidget(
            x=110,
            y=307,
            width=385,
            height=120,
            text="Visible terminal-item description",
            first_line=(9, 7, 250, 16, 12),
        ),
        full_title="An intentionally extreme title " * 8,
        displayed_title="An intentionally extreme title…",
        displayed_title_visible_lines=2,
        full_location=full_status,
        displayed_location=full_status,
        expected_details_height=360,
        overview=_FakeWidget(x=100, y=100, width=410, height=101),
        location_label=_FakeWidget(x=110, y=178, width=250, height=18),
        location_is_status=True,
        library_invariant_receipt=_clean_library_invariant_receipt(),
        environ=environment,
    )

    assert result is not None
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["verified"] is True
    assert payload["path_ellipsized"] is False
    assert payload["status_text_fully_preserved"] is True
    assert payload["location_fully_inside_overview"] is True


def test_quality_e2e_library_visibility_marks_clipped_description_unverified(
    tmp_path: Path,
) -> None:
    environment, _app, _home, _application_data, _diagnostics = _isolated_launch(
        tmp_path
    )

    result = write_quality_e2e_library_visibility_receipt(
        details=_FakeWidget(
            x=100,
            y=100,
            width=410,
            height=390,
            configured_height=360,
        ),
        library_table=_FakeWidget(x=100, y=180, width=900, height=247),
        tags_body=_FakeWidget(x=110, y=405, width=385, height=72),
        description_heading=_FakeWidget(x=110, y=495, width=130, height=18),
        description=_FakeDescriptionWidget(
            x=110,
            y=517,
            width=385,
            height=120,
            text="Persisted but clipped",
            first_line=(9, 7, 180, 16, 12),
        ),
        full_title="Long title " * 20,
        displayed_title="Long title…",
        displayed_title_visible_lines=2,
        full_location="Saved in /long/path/" * 20,
        displayed_location="Saved in /long/path…",
        expected_details_height=360,
        library_invariant_receipt=_clean_library_invariant_receipt(),
        environ=environment,
    )

    assert result is not None
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["verified"] is False
    assert payload["description_heading_fully_inside_details"] is False
    assert payload["description_body_fully_inside_details"] is False
    assert payload["description_bottom_aligned_with_library_table"] is False


def test_quality_e2e_library_visibility_marks_bottom_misalignment_unverified(
    tmp_path: Path,
) -> None:
    environment, _app, _home, _application_data, _diagnostics = _isolated_launch(
        tmp_path
    )

    result = write_quality_e2e_library_visibility_receipt(
        details=_FakeWidget(
            x=100,
            y=100,
            width=410,
            height=390,
            configured_height=360,
        ),
        library_table=_FakeWidget(x=100, y=180, width=900, height=247),
        tags_body=_FakeWidget(x=110, y=205, width=385, height=72),
        description_heading=_FakeWidget(x=110, y=285, width=130, height=18),
        description=_FakeDescriptionWidget(
            x=110,
            y=307,
            width=385,
            height=110,
            text="Visible but not aligned",
            first_line=(9, 7, 180, 16, 12),
        ),
        full_title="Long title " * 20,
        displayed_title="Long title…",
        displayed_title_visible_lines=2,
        full_location="Saved in /long/path/" * 20,
        displayed_location="Saved in /long/path…",
        expected_details_height=360,
        library_invariant_receipt=_clean_library_invariant_receipt(),
        environ=environment,
    )

    assert result is not None
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["description_body_fully_inside_details"] is True
    assert payload["description_table_bottom_delta_px"] == -10
    assert payload["description_bottom_aligned_with_library_table"] is False
    assert payload["verified"] is False


def test_quality_e2e_library_visibility_requires_description_larger_than_tags(
    tmp_path: Path,
) -> None:
    environment, _app, _home, _application_data, _diagnostics = _isolated_launch(
        tmp_path
    )

    result = write_quality_e2e_library_visibility_receipt(
        details=_FakeWidget(
            x=100,
            y=100,
            width=410,
            height=390,
            configured_height=360,
        ),
        library_table=_FakeWidget(x=100, y=180, width=900, height=247),
        tags_body=_FakeWidget(x=110, y=195, width=385, height=120),
        description_heading=_FakeWidget(x=110, y=285, width=130, height=18),
        description=_FakeDescriptionWidget(
            x=110,
            y=307,
            width=385,
            height=120,
            text="Visible and aligned but not larger than Tags",
            first_line=(9, 7, 250, 16, 12),
        ),
        full_title="Long title " * 20,
        displayed_title="Long title…",
        displayed_title_visible_lines=2,
        full_location="Saved in /long/path/" * 20,
        displayed_location="Saved in /long/path…",
        expected_details_height=360,
        library_invariant_receipt=_clean_library_invariant_receipt(),
        environ=environment,
    )

    assert result is not None
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["description_bottom_aligned_with_library_table"] is True
    assert payload["description_tags_height_delta_px"] == 0
    assert payload["description_body_larger_than_tags_body"] is False
    assert payload["verified"] is False


def test_quality_e2e_library_visibility_requires_two_measured_title_lines(
    tmp_path: Path,
) -> None:
    environment, _app, _home, _application_data, _diagnostics = _isolated_launch(
        tmp_path
    )

    result = write_quality_e2e_library_visibility_receipt(
        details=_FakeWidget(
            x=100,
            y=100,
            width=410,
            height=390,
            configured_height=360,
        ),
        library_table=_FakeWidget(x=100, y=180, width=900, height=247),
        tags_body=_FakeWidget(x=110, y=205, width=385, height=72),
        description_heading=_FakeWidget(x=110, y=285, width=130, height=18),
        description=_FakeDescriptionWidget(
            x=110,
            y=307,
            width=385,
            height=120,
            text="Visible, aligned Description text",
            first_line=(9, 7, 250, 16, 12),
        ),
        full_title="An intentionally extreme title " * 20,
        displayed_title="An intentionally extreme title…",
        displayed_title_visible_lines=1,
        full_location="Saved in /an/intentionally/extreme/path/" * 20,
        displayed_location="Saved in /an/intentionally/extreme…",
        expected_details_height=360,
        library_invariant_receipt=_clean_library_invariant_receipt(),
        environ=environment,
    )

    assert result is not None
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["displayed_title_visible_lines"] == 1
    assert payload["title_minimum_visible_lines_preserved"] is False
    assert payload["verified"] is False


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
