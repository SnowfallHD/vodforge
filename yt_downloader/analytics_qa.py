"""Explicit, bounded frozen-app analytics qualification on a fictional profile.

Does not grant consent, override transports, download media or touch native UI.
The normal Qt app and canonical producers run; provider receipt is independently
verified after exit. This local receipt alone never proves provider ingestion.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .posthog_analytics import installation_distinct_id, valid_qa_run_id
from .product_telemetry import _load_outbox
from .version import __version__, read_build_revision


def validate_qa_receipt(receipt: Path) -> Path:
    label = valid_qa_run_id(os.environ.get("VODFORGE_POSTHOG_QA_RUN", ""))
    raw = os.environ.get("VODFORGE_POSTHOG_QA_HOME", "")
    home = Path(raw)
    if (
        not label
        or not raw
        or not home.is_absolute()
        or home.resolve() != home
        or os.environ.get("HOME") != str(home)
        or os.environ.get("LOCALAPPDATA") != str(home)
        or os.environ.get("QT_QPA_PLATFORM") != "offscreen"
        or not receipt.is_absolute()
        or receipt.parent != home
        or receipt.exists()
        or receipt.is_symlink()
    ):
        raise ValueError(
            "Analytics QA requires a fresh isolated offscreen profile and UUID4 label"
        )
    marker = home / ".vodforge-analytics-qa.json"
    if marker.is_symlink() or marker.stat().st_size > 1024:
        raise ValueError("Invalid analytics QA profile attestation")
    if json.loads(marker.read_text()) != {
        "qa_run_id": label,
        "fictional_profile": True,
    }:
        raise ValueError("Analytics QA profile label mismatch")
    return receipt


def schedule_qa(application: Any, bridge: Any, receipt: Path) -> Any:
    from PySide6.QtCore import QTimer

    deadline = time.monotonic() + 60
    stage = "waiting"
    stop_at = 0.0
    timer = QTimer(application)
    timer.setInterval(250)

    def controlled_exception() -> None:
        # Actual Qt/Python uncaught callback exercises the installed hook. This
        # fixed text is local only; the provider receives a closed category.
        raise RuntimeError("VODForge controlled labeled analytics QA exception")

    def finish(passed: bool, reason: str) -> None:
        from .cloud_funnel import load_or_create_installation_state

        telemetry = bridge._analytics.telemetry
        directory = bridge._runtime.history_path.parent
        state = load_or_create_installation_state(directory / "installation.json")
        pending = _load_outbox(directory / "product-telemetry.json")
        receipt.write_text(
            json.dumps(
                {
                    "qa_run_id": os.environ["VODFORGE_POSTHOG_QA_RUN"],
                    "measurement_scope": "qa",
                    "version": __version__,
                    "build_revision": read_build_revision(),
                    "installation_distinct_id": installation_distinct_id(
                        state.install_id
                    ),
                    "first_party_first_launch_acknowledged": state.first_launch_confirmed,
                    "pending_custom_events": len(pending),
                    "custom_worker_settled": telemetry.shutdown(0)
                    if telemetry
                    else False,
                    "passed_local_runtime": passed,
                    "reason": reason,
                    "provider_ingestion": "unverified: independent labeled production query required",
                    "renderer": "Qt Quick offscreen; no native consent or physical-device claim",
                },
                indent=2,
            )
            + "\n"
        )
        timer.stop()
        application.exit(0 if passed else 3)

    def tick() -> None:
        nonlocal stage, stop_at
        telemetry = bridge._analytics.telemetry
        if time.monotonic() >= deadline:
            bridge.close()
            finish(False, "bounded qualification deadline")
            return
        if stage == "waiting":
            if not bridge._analytics.settled or telemetry is None:
                return
            if (
                not bridge._analytics.allowed
                or telemetry.posthog_admission_epoch() is None
            ):
                bridge.close()
                finish(
                    False,
                    "existing fixture consent/provider policy does not permit delivery",
                )
                return
            stage, stop_at = "running", time.monotonic() + 8
            QTimer.singleShot(0, controlled_exception)
        elif stage == "running" and time.monotonic() >= stop_at:
            bridge.close()
            stage = "closing"
        elif stage == "closing" and telemetry is not None and telemetry.shutdown(0):
            pending = _load_outbox(
                bridge._runtime.history_path.parent / "product-telemetry.json"
            )
            if not pending:
                finish(
                    True,
                    "normal lifecycle and bounded QA exception dispatched; custom outbox acknowledged",
                )

    timer.timeout.connect(tick)
    timer.start()
    return timer
