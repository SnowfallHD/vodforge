import json
import os
import sys
from pathlib import Path

import pytest
from quality_harness import native_ui_checks
from quality_harness.native_ui_checks import complete_native_report
from quality_harness.util import CommandResult, run_command


@pytest.mark.parametrize(
    "body,expected",
    [
        ("<testcase name='native' />", True),
        ("", False),
        ("<testcase><skipped /></testcase>", False),
        ("<testcase><failure /></testcase>", False),
        ("<testcase><error /></testcase>", False),
    ],
)
def test_native_evidence_requires_executed_successes(tmp_path, body, expected):
    report = tmp_path / "report.xml"
    report.write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>")
    assert complete_native_report(report) is expected


def test_missing_native_evidence_fails(tmp_path):
    assert not complete_native_report(tmp_path / "missing.xml")


def test_native_scenario_uses_schema_compatible_evidence(tmp_path, monkeypatch):
    def run(*args, **kwargs):
        assert "tests/test_archive_actual_playback.py" in args[0]
        assert "tests/test_watch_queue_native.py" in args[0]
        assert "tests/test_shared_header_action_native.py" in args[0]
        assert kwargs["env"]["VODFORGE_ACTUAL_PLAYBACK_TESTS"] == "1"
        (tmp_path / "native.xml").write_text("<testsuite><testcase /></testsuite>")
        return CommandResult(args[0], 0, 1.0, "1 passed", "")

    monkeypatch.setattr(native_ui_checks, "run_command", run)
    scenario, findings = native_ui_checks.native_surface_contract(tmp_path, tmp_path)
    assert scenario["status"] == "passed"
    assert isinstance(scenario["evidence"], list)
    assert all(isinstance(item, str) for item in scenario["evidence"])
    assert not findings


def test_qt_candidate_uses_rendered_qml_contract_instead_of_tk_native_suite(
    tmp_path, monkeypatch
):
    def run(command, **kwargs):
        assert "tests/test_qt_scene_port.py" in command
        assert "tests/test_qt_terminal_item_events.py" in command
        assert "tests/test_archive_actual_playback.py" not in command
        assert "tests/test_scene_inflight_native.py" not in command
        assert kwargs["env"]["VODFORGE_UI"] == "qt"
        assert kwargs["env"]["QT_QPA_PLATFORM"] == "offscreen"
        (tmp_path / "native.xml").write_text("<testsuite><testcase /></testsuite>")
        return CommandResult(command, 0, 0.1, "passed", "")

    monkeypatch.setattr(native_ui_checks, "run_command", run)
    scenario, _ = native_ui_checks.native_surface_contract(tmp_path, tmp_path, ui="qt")
    assert scenario["status"] == "passed"
    assert scenario["metrics"]["ui"] == "qt"


def test_native_timeout_retains_raw_result_and_cannot_reuse_old_success(
    tmp_path, monkeypatch
):
    (tmp_path / "native.xml").write_text("<testsuite><testcase /></testsuite>")

    def timed_out(command, **kwargs):
        assert kwargs["timeout"] == 1800
        return CommandResult(
            command,
            None,
            1800.1,
            "partial native progress",
            "last warning",
            timed_out=True,
        )

    monkeypatch.setattr(native_ui_checks, "run_command", timed_out)
    scenario, _ = native_ui_checks.native_surface_contract(tmp_path, tmp_path)
    assert scenario["status"] == "failed"
    assert scenario["duration_seconds"] == 1800.1
    assert scenario["metrics"]["timed_out"]
    assert scenario["error"] == "Native suite exceeded 1800 seconds"
    assert not (tmp_path / "native.xml").exists()
    raw = json.loads((tmp_path / "native-command.json").read_text())
    assert raw["timed_out"] and not raw["unavailable"]
    assert raw["stdout"] == "partial native progress"
    assert raw["stderr"] == "last warning"


def test_actual_command_timeout_retains_both_flushed_output_streams(tmp_path):
    result = run_command(
        [
            sys.executable,
            "-c",
            "import sys,time; print('OUT sentinel',flush=True); print('ERR sentinel',file=sys.stderr,flush=True); time.sleep(10)",
        ],
        cwd=tmp_path,
        timeout=0.3,
    )
    assert result.timed_out and result.returncode is None
    assert result.stdout == "OUT sentinel\n"
    assert result.stderr == "ERR sentinel\n"


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_common_native_contracts_run_on_both_platforms(tmp_path, monkeypatch, platform):
    monkeypatch.setattr(native_ui_checks.sys, "platform", platform)

    def run(command, **kwargs):
        for family in (
            "foundation_acceptance",
            "library_file_actions",
            "relink_consent",
            "relink_navigation",
            "relink_admission",
            "relink_layout",
            "widget_reveal",
            "button_parity",
            "inline_description",
            "player_layout",
            "startup_update",
        ):
            assert f"tests/test_{family}_native.py" in command
        for family in (
            "library_restraint",
            "description_readability",
            "archive_overlay_reveal",
            "surface_raster",
            "surface_memory",
            "view_transition",
        ):
            assert (f"tests/test_{family}_native.py" in command) == (
                platform == "darwin"
            )
        (tmp_path / "native.xml").write_text("<testsuite><testcase /></testsuite>")
        return CommandResult(command, 0, 1.0, "native fixture passed", "")

    monkeypatch.setattr(native_ui_checks, "run_command", run)
    scenario, _ = native_ui_checks.native_surface_contract(tmp_path, tmp_path)
    assert scenario["status"] == "passed"


def test_native_report_plugin_does_not_require_inherited_pythonpath(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("PYTHONPATH", raising=False)

    def run(command, **kwargs):
        assert command[command.index("-p") + 1] == "quality_harness.native_reports"
        assert kwargs["env"]["PYTHONPATH"].split(os.pathsep) == [
            str(tmp_path.resolve()),
            str((tmp_path / "engineering-quality").resolve()),
        ]
        (tmp_path / "native.xml").write_text("<testsuite><testcase /></testsuite>")
        return CommandResult(command, 0, 1.0, "passed", "")

    monkeypatch.setattr(native_ui_checks, "run_command", run)
    scenario, _ = native_ui_checks.native_surface_contract(tmp_path, tmp_path)
    assert scenario["status"] == "passed"


def test_native_child_imports_ignore_inherited_path_and_cwd_contamination(
    tmp_path, monkeypatch
):
    import subprocess
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    poison = tmp_path / "unrelated"
    poison.mkdir()
    for name in ("yt_downloader", "quality_harness"):
        package = poison / name
        package.mkdir()
        (package / "__init__.py").write_text(
            "raise RuntimeError('wrong checkout imported')"
        )
    monkeypatch.chdir(poison)
    monkeypatch.setenv("PYTHONPATH", str(poison))

    def run(command, **kwargs):
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json,yt_downloader.app,quality_harness.native_reports; "
                    "print(json.dumps([yt_downloader.app.__file__,quality_harness.native_reports.__file__]))"
                ),
            ],
            cwd=kwargs["cwd"],
            env=kwargs["env"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert probe.returncode == 0, probe.stderr
        app_path, harness_path = map(Path, json.loads(probe.stdout))
        assert app_path.resolve().is_relative_to(repo / "yt_downloader")
        assert harness_path.resolve().is_relative_to(repo / "engineering-quality")
        assert kwargs["env"]["VODFORGE_NATIVE_SOURCE_ROOT"] == str(repo)
        assert kwargs["env"]["VODFORGE_NATIVE_HARNESS_ROOT"] == str(
            repo / "engineering-quality"
        )
        (tmp_path / "native.xml").write_text("<testsuite><testcase /></testsuite>")
        return CommandResult(command, 0, 1.0, "import probe passed", "")

    monkeypatch.setattr(native_ui_checks, "run_command", run)
    scenario, _ = native_ui_checks.native_surface_contract(repo, tmp_path)
    assert scenario["status"] == "passed"


def test_native_import_receipt_rejects_wrong_checkout_before_tests(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from quality_harness import native_reports

    monkeypatch.setenv("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path / "evidence"))
    monkeypatch.setenv("VODFORGE_NATIVE_SOURCE_ROOT", str(tmp_path / "expected"))
    monkeypatch.setenv("VODFORGE_NATIVE_HARNESS_ROOT", str(tmp_path / "harness"))

    def module(name):
        path = tmp_path / ("harness" if name.startswith("quality_harness") else "wrong")
        return SimpleNamespace(__file__=str(path / "module.py"))

    monkeypatch.setattr(native_reports.importlib, "import_module", module)
    with pytest.raises(pytest.UsageError, match="outside expected root"):
        native_reports.pytest_sessionstart(None)
    receipt = json.loads((tmp_path / "evidence" / "native-imports.json").read_text())
    assert Path(receipt["imported_modules"]["yt_downloader.app"]).parent.name == "wrong"
    assert receipt["expected_roots"]["source"] == str(tmp_path / "expected")


@pytest.mark.parametrize("profile", ["normal", "deep"])
def test_native_profile_controls_held_out_exploration(tmp_path, monkeypatch, profile):
    def run(command, **kwargs):
        assert kwargs["env"]["VODFORGE_NATIVE_PROFILE"] == profile
        (tmp_path / "native.xml").write_text("<testsuite><testcase /></testsuite>")
        return CommandResult(command, 0, 0.1, "passed", "")

    monkeypatch.setattr(native_ui_checks, "run_command", run)
    scenario, _ = native_ui_checks.native_surface_contract(
        tmp_path, tmp_path, profile=profile
    )
    assert scenario["status"] == "passed"
