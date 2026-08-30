from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quality_harness import packaged_e2e
from quality_harness.packaged_e2e import (
    SMOKE_UI_EVENT_ORDER,
    _history_persistence_receipt,
    _persisted_state_snapshot,
    _probe_media,
    _validate_driver_trace,
)
from quality_harness.util import CommandResult, sha256_file


def _driver_trace(
    session_dir: Path, *, omit: set[str] | None = None
) -> dict[str, object]:
    omit = omit or set()
    ui_dir = session_dir / "ui"
    ui_dir.mkdir(parents=True)
    events = []
    screenshots = []
    started = datetime(2026, 8, 30, tzinfo=timezone.utc)
    for index, name in enumerate(SMOKE_UI_EVENT_ORDER):
        if name in omit:
            continue
        screenshot = None
        if name != "restart_requested":
            path = ui_dir / f"{index:02d}-{name}.png"
            path.write_bytes(b"not-an-empty-receipt")
            screenshot = str(path)
            screenshots.append(str(path))
        events.append(
            {
                "event": name,
                "observed_at": (started + timedelta(seconds=index))
                .isoformat()
                .replace("+00:00", "Z"),
                "screenshot": screenshot,
            }
        )
    return {"events": events, "screenshots": screenshots, "notes": []}


def test_driver_trace_requires_ordered_timestamped_session_screenshots(
    tmp_path: Path,
) -> None:
    payload = _driver_trace(tmp_path)
    receipt = _validate_driver_trace(payload, profile="smoke", session_dir=tmp_path)

    assert receipt["valid"] is True
    assert receipt["order_valid"] is True
    assert receipt["timestamps_monotonic"] is True
    assert receipt["invalid_screenshot_events"] == []
    assert all(item["sha256"] for item in receipt["screenshot_receipts"])

    payload["events"][2], payload["events"][3] = (
        payload["events"][3],
        payload["events"][2],
    )  # type: ignore[index]
    invalid = _validate_driver_trace(payload, profile="smoke", session_dir=tmp_path)
    assert invalid["valid"] is False
    assert invalid["order_valid"] is False
    assert invalid["timestamps_monotonic"] is False


def test_driver_trace_preserves_library_only_evidence_gap(tmp_path: Path) -> None:
    receipt = _validate_driver_trace(
        _driver_trace(tmp_path, omit={"library_observed"}),
        profile="smoke",
        session_dir=tmp_path,
    )

    assert receipt["valid"] is False
    assert receipt["structural_valid"] is True
    assert receipt["missing_events"] == ["library_observed"]


def test_driver_trace_rejects_screenshot_outside_session(tmp_path: Path) -> None:
    payload = _driver_trace(tmp_path / "session")
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    first = payload["events"][0]  # type: ignore[index]
    first["screenshot"] = str(outside)  # type: ignore[index]
    payload["screenshots"].append(str(outside))  # type: ignore[union-attr]

    receipt = _validate_driver_trace(
        payload, profile="smoke", session_dir=tmp_path / "session"
    )
    assert receipt["valid"] is False
    assert receipt["invalid_screenshot_events"] == ["app_visible"]


def test_media_probe_uses_exact_bundled_ffprobe(monkeypatch, tmp_path: Path) -> None:
    ffprobe = tmp_path / "artifact" / "Contents" / "Frameworks" / "ffprobe"
    ffprobe.parent.mkdir(parents=True)
    ffprobe.write_bytes(b"packaged ffprobe")
    media = tmp_path / "final.mp4"
    media.write_bytes(b"media")
    observed_commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs) -> CommandResult:
        observed_commands.append(command)
        return CommandResult(
            command=command,
            returncode=0,
            duration_seconds=0.01,
            stdout=json.dumps(
                {"format": {"format_name": "mp4"}, "streams": [{"codec_type": "video"}]}
            ),
            stderr="",
        )

    monkeypatch.setattr(packaged_e2e, "run_command", fake_run)
    probes = _probe_media(
        [media],
        {"bundled_ffprobe": {"path": str(ffprobe), "sha256": sha256_file(ffprobe)}},
        repo_root=tmp_path,
    )

    assert probes[0]["readable"] is True
    assert observed_commands[0][0] == str(ffprobe.resolve())
    assert probes[0]["ffprobe_sha256"] == sha256_file(ffprobe)


def test_history_persistence_binds_two_launches_to_stable_output(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    media = home / "Downloads" / "Channel" / "video.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"committed-media")
    history_path = (
        home / "Library" / "Application Support" / "VODForge" / "download-history.json"
    )
    history_path.parent.mkdir(parents=True)
    history_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "items": [
                    {
                        "id": "fixture",
                        "vodforge_output_type": "MP4",
                        "vodforge_encoding_summary": {
                            "output": {"Output file path": str(media)}
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    baseline = _persisted_state_snapshot(home)
    probes = [{"path": str(media), "sha256": sha256_file(media), "readable": True}]
    launches = [
        {"returncode": 0},
        {"returncode": 0, "reason": "driver_requested_restart"},
    ]

    receipt = _history_persistence_receipt(
        home,
        probes,
        launches,
        f"Loaded download history: {history_path}",
        baseline,
        expected_output_type="MP4",
    )

    assert receipt["verified"] is True
    assert receipt["launch_count_at_least_two"] is True
    assert receipt["media_hashes_stable_across_restart"] is True
    assert receipt["history_hash_stable_across_restart"] is True
