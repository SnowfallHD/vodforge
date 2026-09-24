"""The selected Qt renderer must own its presentation telemetry gate."""

from __future__ import annotations

import json
from types import SimpleNamespace

from quality_harness import diagnostic_pipeline, util
from quality_harness.qt_diagnostic_probes import QT_PRESENTATION_CASES


def test_qt_gate_selects_actual_qml_producers(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setenv("VODFORGE_SITE_REPO", str(tmp_path / "site"))
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        (tmp_path / "result" / "receipt.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "case_count": len(QT_PRESENTATION_CASES),
                    "stored_events": 21,
                }
            )
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(util, "run_command", run)
    receipt, _ = diagnostic_pipeline.diagnostic_surface_contract(
        source, tmp_path / "result", ui="qt"
    )
    assert receipt["status"] == "passed"
    assert [
        commands[0][i + 1] for i, value in enumerate(commands[0]) if value == "--case"
    ] == list(QT_PRESENTATION_CASES)
    assert "cold_ready" not in commands[0]


def test_qt_gate_rejects_missing_producer_cases(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setenv("VODFORGE_SITE_REPO", str(tmp_path / "site"))

    def run(_command, **_kwargs):
        (tmp_path / "result" / "receipt.json").write_text(
            json.dumps({"passed": True, "case_count": 0, "stored_events": 0})
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(util, "run_command", run)
    receipt, _ = diagnostic_pipeline.diagnostic_surface_contract(
        source, tmp_path / "result", ui="qt"
    )
    assert receipt["status"] == "failed"
