from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen

import pytest
from quality_harness import packaged_e2e
from quality_harness.fault_server import (
    CANCELLATION_ROUTE,
    QUEUED_LIBRARY_DESCRIPTION_STRESS_ROUTE,
    SLOW_LIBRARY_DESCRIPTION_STRESS_ROUTE,
    FixtureHTTPServer,
)
from quality_harness.fixtures import (
    LIBRARY_DESCRIPTION_STRESS_DESCRIPTION,
    LIBRARY_DESCRIPTION_STRESS_SELECTED_TITLE,
    LIBRARY_DESCRIPTION_STRESS_TITLE,
)
from quality_harness.packaged_e2e import (
    _history_persistence_receipt,
    _library_description_visibility_receipt,
    _persisted_state_snapshot,
    _probe_media,
    _validate_driver_trace,
)
from quality_harness.util import CommandResult, sha256_file

from yt_downloader.quality_e2e import (
    QUALITY_E2E_LIBRARY_BOTTOM_ALIGNMENT_TOLERANCE_PX,
    QUALITY_E2E_LIBRARY_VISIBILITY_PREFIX,
    QUALITY_E2E_MIN_TITLE_VISIBLE_LINES,
)


def test_packaged_session_uses_slow_description_stress_fixture() -> None:
    fields = packaged_e2e._packaged_fixture_session_fields(
        lambda route: f"http://fixture.invalid{route}"
    )

    assert fields["input_url"] == (
        f"http://fixture.invalid{SLOW_LIBRARY_DESCRIPTION_STRESS_ROUTE}"
    )
    assert fields["slow_input_url"] == f"http://fixture.invalid{CANCELLATION_ROUTE}"
    assert fields["queued_input_url"] == (
        f"http://fixture.invalid{QUEUED_LIBRARY_DESCRIPTION_STRESS_ROUTE}"
    )
    assert (
        len(
            {fields[key] for key in ("input_url", "slow_input_url", "queued_input_url")}
        )
        == 3
    )
    expectation = fields["library_visibility_expectation"]
    assert expectation["page_title"] == LIBRARY_DESCRIPTION_STRESS_TITLE
    assert (
        expectation["selected_item_title"] == LIBRARY_DESCRIPTION_STRESS_SELECTED_TITLE
    )
    assert expectation["description"] == LIBRARY_DESCRIPTION_STRESS_DESCRIPTION


def test_slow_description_stress_route_preserves_metadata_and_uses_slow_hls(
    tmp_path: Path,
) -> None:
    with (
        FixtureHTTPServer(tmp_path) as server,
        urlopen(
            server.url(SLOW_LIBRARY_DESCRIPTION_STRESS_ROUTE), timeout=5
        ) as response,
    ):
        document = response.read().decode("utf-8")

    assert LIBRARY_DESCRIPTION_STRESS_TITLE in document
    assert LIBRARY_DESCRIPTION_STRESS_DESCRIPTION in document
    assert "/slow/hls/hls-long/master.m3u8" in document


def test_dedicated_queue_route_preserves_description(tmp_path: Path) -> None:
    with FixtureHTTPServer(tmp_path) as server:
        with urlopen(
            server.url(QUEUED_LIBRARY_DESCRIPTION_STRESS_ROUTE), timeout=5
        ) as response:
            document = response.read().decode()
        with urlopen(server.url(CANCELLATION_ROUTE), timeout=5) as response:
            cancellation = response.read().decode()
    assert LIBRARY_DESCRIPTION_STRESS_TITLE in document
    assert LIBRARY_DESCRIPTION_STRESS_DESCRIPTION in document
    assert LIBRARY_DESCRIPTION_STRESS_TITLE not in cancellation
    assert "/slow/hls/hls-long/master.m3u8" in cancellation


def test_real_extractor_separates_cancellation_and_queue_identities(
    tmp_path: Path,
) -> None:
    from yt_dlp import YoutubeDL

    hls = tmp_path / "hls-long"
    hls.mkdir()
    (hls / "master.m3u8").write_text(
        "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n"
        "#EXTINF:6,\nsegment.ts\n#EXT-X-ENDLIST\n"
    )
    with (
        FixtureHTTPServer(tmp_path) as server,
        YoutubeDL(
            {"quiet": True, "no_warnings": True, "skip_download": True}
        ) as extractor,
    ):
        fields = packaged_e2e._packaged_fixture_session_fields(server.url)
        identities = [
            extractor.extract_info(fields[key], download=False, process=False)["id"]
            for key in ("input_url", "slow_input_url", "queued_input_url")
        ]
    assert len(set(identities)) == 3


def test_fixture_throttle_applies_only_to_slow_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"fixture transport" * 2200
    (tmp_path / "short-av.mp4").write_bytes(payload)
    delays = []
    monkeypatch.setattr("quality_harness.fault_server.time.sleep", delays.append)
    with FixtureHTTPServer(tmp_path, slow_chunk_delay=0.25) as server:
        with urlopen(server.url("/media/short-av.mp4"), timeout=5) as response:
            assert response.read() == payload
        assert delays == []
        with urlopen(server.url("/slow/media/short-av.mp4"), timeout=5) as response:
            assert response.read() == payload
    assert delays == [0.25] * 3


@pytest.mark.parametrize("delay", [-1, 1.1, float("nan"), float("inf")])
def test_fixture_rejects_unbounded_throttle(tmp_path: Path, delay: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        FixtureHTTPServer(tmp_path, slow_chunk_delay=delay)


def _driver_trace(
    session_dir: Path,
    *,
    omit: set[str] | None = None,
    session_nonce: str | None = None,
    launches: list[dict[str, object]] | None = None,
    profile: str = "smoke",
) -> dict[str, object]:
    omit = omit or set()
    ui_dir = session_dir / "ui"
    ui_dir.mkdir(parents=True)
    events = []
    screenshots = []
    started = datetime(2026, 8, 30, tzinfo=timezone.utc)
    for index, name in enumerate(packaged_e2e._required_ui_event_order(profile)):
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
        if session_nonce is not None and launches is not None:
            sequence = {
                "restart_observed": 2,
                "consent_denied_observed": 3,
                "telemetry_disabled_observed": 4,
            }.get(name, 1)
            launch = next(
                item for item in launches if item["launch_sequence"] == sequence
            )
            events[-1].update(
                {
                    "session_nonce": session_nonce,
                    "launch_id": launch["launch_id"],
                    "launch_sequence": sequence,
                    "pid": launch["pid"],
                    "process_create_time": launch["create_time"],
                    "executable_sha256": launch["executable_sha256"],
                    "bundle_tree_sha256": launch["bundle_tree_sha256"],
                    "window_id": 1000 + index,
                    "window_owner_pid": launch["pid"],
                    "window_title_token": launch["window_token"],
                    "native_window_identity": {
                        "verified": True,
                        "window_id": 1000 + index,
                        "owner_pid": launch["pid"],
                        "title": f"VODForge [{launch['window_token']}]",
                        "layer": 0,
                    },
                }
            )
    return {"events": events, "screenshots": screenshots, "notes": []}


@pytest.mark.parametrize(
    "defect", [None, "wrong_launch", "preview_enabled", "production_enabled"]
)
def test_telemetry_trace_binds_privacy_checks_to_their_reopened_processes(
    tmp_path: Path, defect: str | None
) -> None:
    launches = [
        {
            "launch_sequence": sequence,
            "launch_id": str(sequence) * 32,
            "pid": 7000 + sequence,
            "create_time": float(sequence),
            "executable_sha256": "a" * 64,
            "bundle_tree_sha256": "b" * 64,
            "window_token": f"VFQ-test-L{sequence}",
            "attestation": {
                "telemetry_preview": sequence < 4,
                "telemetry_production": False,
            },
        }
        for sequence in range(1, 5)
    ]
    nonce = "f" * 32
    trace = _driver_trace(
        tmp_path, profile="telemetry", session_nonce=nonce, launches=launches
    )
    if defect == "wrong_launch":
        trace["events"][-2]["launch_sequence"] = 1
    elif defect == "preview_enabled":
        launches[-1]["attestation"]["telemetry_preview"] = True
    elif defect == "production_enabled":
        launches[-1]["attestation"]["telemetry_production"] = True
    receipt = _validate_driver_trace(
        trace,
        profile="telemetry",
        session_dir=tmp_path,
        session_nonce=nonce,
        launches=launches,
    )
    assert receipt["valid"] is (defect is None)


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


def test_packaged_library_description_receipt_requires_visible_fixed_height_geometry(
    tmp_path: Path,
) -> None:
    nonce = "0123456789abcdef0123456789abcdef"
    launch = {
        "launch_id": "fedcba9876543210fedcba9876543210",
        "launch_sequence": 1,
        "pid": 7001,
        "create_time": 101.5,
        "executable_sha256": "a" * 64,
        "bundle_tree_sha256": "b" * 64,
        "window_token": "VFQ-0123456789ab-L1",
    }
    restart = {
        **launch,
        "launch_id": "11111111111111111111111111111111",
        "launch_sequence": 2,
        "pid": 7002,
        "create_time": 202.5,
        "window_token": "VFQ-0123456789ab-L2",
    }
    launches = [launch, restart]
    trace = _driver_trace(
        tmp_path / "session",
        session_nonce=nonce,
        launches=launches,
    )
    description_event = next(
        item
        for item in trace["events"]
        if item["event"] == "library_description_observed"
    )
    description_event["observed_text"] = LIBRARY_DESCRIPTION_STRESS_DESCRIPTION
    isolated_tmp = tmp_path / "isolated" / "tmp"
    isolated_tmp.mkdir(parents=True)
    state_paths = {"tmp": str(isolated_tmp)}
    receipt_path = isolated_tmp / (
        f"{QUALITY_E2E_LIBRARY_VISIBILITY_PREFIX}{nonce}-{launch['window_token']}.json"
    )
    description_sha256 = hashlib.sha256(
        LIBRARY_DESCRIPTION_STRESS_DESCRIPTION.encode("utf-8")
    ).hexdigest()
    title_sha256 = hashlib.sha256(
        LIBRARY_DESCRIPTION_STRESS_SELECTED_TITLE.encode("utf-8")
    ).hexdigest()
    payload = {
        "session_nonce": nonce,
        "launch_id": launch["launch_id"],
        "window_token": launch["window_token"],
        "pid": launch["pid"],
        "description_sha256": description_sha256,
        "full_title_sha256": title_sha256,
        "details_height_px": 390,
        "details_allocated_height_px": 390,
        "details_configured_height_px": 360,
        "expected_details_height_px": 360,
        "displayed_title_visible_lines": 2,
        "minimum_displayed_title_visible_lines": (QUALITY_E2E_MIN_TITLE_VISIBLE_LINES),
        "description_bounds": {"x": 110, "y": 307, "width": 385, "height": 120},
        "library_table_bounds": {"x": 100, "y": 180, "width": 900, "height": 247},
        "tags_body_bounds": {"x": 110, "y": 205, "width": 385, "height": 72},
        "description_bottom_px": 427,
        "library_table_bottom_px": 427,
        "description_table_bottom_delta_px": 0,
        "description_table_bottom_tolerance_px": (
            QUALITY_E2E_LIBRARY_BOTTOM_ALIGNMENT_TOLERANCE_PX
        ),
        "verified": True,
        "fixed_height_preserved": True,
        "description_heading_mapped_and_viewable": True,
        "description_body_mapped_and_viewable": True,
        "library_table_mapped_and_viewable": True,
        "tags_body_mapped_and_viewable": True,
        "description_heading_fully_inside_details": True,
        "tags_body_fully_inside_details": True,
        "description_body_fully_inside_details": True,
        "description_bottom_aligned_with_library_table": True,
        "description_body_height_px": 120,
        "tags_body_height_px": 72,
        "description_tags_height_delta_px": 48,
        "description_body_larger_than_tags_body": True,
        "description_first_line_visible": True,
        "path_ellipsized": True,
        "title_ellipsized": True,
        "title_minimum_visible_lines_preserved": True,
        "library_projection_invariants_clean": True,
        "library_projection_row_count": 1,
        "library_projection_canonical_run_ids": ["run-1"],
        "library_projection_projected_run_ids": ["run-1"],
        "library_projection_statuses": ["Completed"],
        "library_projection_violation_codes": [],
    }
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")
    receipt_path.chmod(0o600)

    receipt = _library_description_visibility_receipt(
        state_paths=state_paths,
        driver_trace=trace,
        launches=launches,
        session_nonce=nonce,
        expected_description=LIBRARY_DESCRIPTION_STRESS_DESCRIPTION,
    )
    assert receipt["verified"] is True
    assert receipt["errors"] == []

    for broken_key in (
        "description_body_fully_inside_details",
        "library_table_mapped_and_viewable",
        "tags_body_mapped_and_viewable",
        "description_bottom_aligned_with_library_table",
        "description_body_larger_than_tags_body",
        "description_first_line_visible",
        "path_ellipsized",
        "title_ellipsized",
        "title_minimum_visible_lines_preserved",
        "fixed_height_preserved",
        "library_projection_invariants_clean",
    ):
        broken = dict(payload)
        broken[broken_key] = False
        receipt_path.write_text(json.dumps(broken), encoding="utf-8")
        rejected = _library_description_visibility_receipt(
            state_paths=state_paths,
            driver_trace=trace,
            launches=launches,
            session_nonce=nonce,
            expected_description=LIBRARY_DESCRIPTION_STRESS_DESCRIPTION,
        )
        assert rejected["verified"] is False
        assert any(broken_key in error for error in rejected["errors"])

    invariant_violation = dict(payload)
    invariant_violation["library_projection_violation_codes"] = [
        "transient_projection_without_owner"
    ]
    receipt_path.write_text(json.dumps(invariant_violation), encoding="utf-8")
    rejected = _library_description_visibility_receipt(
        state_paths=state_paths,
        driver_trace=trace,
        launches=launches,
        session_nonce=nonce,
        expected_description=LIBRARY_DESCRIPTION_STRESS_DESCRIPTION,
    )
    assert rejected["verified"] is False
    assert any("violation codes" in error for error in rejected["errors"])

    forged_alignment = dict(payload)
    forged_alignment["description_bounds"] = {
        "x": 110,
        "y": 307,
        "width": 385,
        "height": 110,
    }
    receipt_path.write_text(json.dumps(forged_alignment), encoding="utf-8")
    rejected = _library_description_visibility_receipt(
        state_paths=state_paths,
        driver_trace=trace,
        launches=launches,
        session_nonce=nonce,
        expected_description=LIBRARY_DESCRIPTION_STRESS_DESCRIPTION,
    )
    assert rejected["verified"] is False
    assert any("not aligned" in error for error in rejected["errors"])
    assert any(
        "description_bottom_px mismatch" in error for error in rejected["errors"]
    )

    altered_tolerance = dict(payload)
    altered_tolerance["description_table_bottom_tolerance_px"] = (
        QUALITY_E2E_LIBRARY_BOTTOM_ALIGNMENT_TOLERANCE_PX + 1
    )
    receipt_path.write_text(json.dumps(altered_tolerance), encoding="utf-8")
    rejected = _library_description_visibility_receipt(
        state_paths=state_paths,
        driver_trace=trace,
        launches=launches,
        session_nonce=nonce,
        expected_description=LIBRARY_DESCRIPTION_STRESS_DESCRIPTION,
    )
    assert rejected["verified"] is False
    assert any(
        "description_table_bottom_tolerance_px mismatch" in error
        for error in rejected["errors"]
    )

    equal_tag_height = dict(payload)
    equal_tag_height["tags_body_bounds"] = {
        "x": 110,
        "y": 195,
        "width": 385,
        "height": 120,
    }
    receipt_path.write_text(json.dumps(equal_tag_height), encoding="utf-8")
    rejected = _library_description_visibility_receipt(
        state_paths=state_paths,
        driver_trace=trace,
        launches=launches,
        session_nonce=nonce,
        expected_description=LIBRARY_DESCRIPTION_STRESS_DESCRIPTION,
    )
    assert rejected["verified"] is False
    assert any("not larger than" in error for error in rejected["errors"])
    assert any(
        "description_tags_height_delta_px mismatch" in error
        for error in rejected["errors"]
    )

    missing_tags_bounds = dict(payload)
    missing_tags_bounds.pop("tags_body_bounds")
    receipt_path.write_text(json.dumps(missing_tags_bounds), encoding="utf-8")
    rejected = _library_description_visibility_receipt(
        state_paths=state_paths,
        driver_trace=trace,
        launches=launches,
        session_nonce=nonce,
        expected_description=LIBRARY_DESCRIPTION_STRESS_DESCRIPTION,
    )
    assert rejected["verified"] is False
    assert any("tags_body_bounds is invalid" in error for error in rejected["errors"])

    one_title_line = dict(payload)
    one_title_line["displayed_title_visible_lines"] = 1
    receipt_path.write_text(json.dumps(one_title_line), encoding="utf-8")
    rejected = _library_description_visibility_receipt(
        state_paths=state_paths,
        driver_trace=trace,
        launches=launches,
        session_nonce=nonce,
        expected_description=LIBRARY_DESCRIPTION_STRESS_DESCRIPTION,
    )
    assert rejected["verified"] is False
    assert any(
        "fewer than 2 measured visible lines" in error for error in rejected["errors"]
    )

    raw_page_title = dict(payload)
    raw_page_title["full_title_sha256"] = hashlib.sha256(
        LIBRARY_DESCRIPTION_STRESS_TITLE.encode("utf-8")
    ).hexdigest()
    receipt_path.write_text(json.dumps(raw_page_title), encoding="utf-8")
    rejected = _library_description_visibility_receipt(
        state_paths=state_paths,
        driver_trace=trace,
        launches=launches,
        session_nonce=nonce,
        expected_description=LIBRARY_DESCRIPTION_STRESS_DESCRIPTION,
    )
    assert rejected["verified"] is False
    assert any("full_title_sha256 mismatch" in error for error in rejected["errors"])


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


def test_driver_trace_binds_every_receipt_to_exact_launch_provenance(
    tmp_path: Path,
) -> None:
    nonce = "0123456789abcdef0123456789abcdef"
    launches: list[dict[str, object]] = [
        {
            "launch_id": "launch-one",
            "launch_sequence": 1,
            "pid": 7001,
            "create_time": 101.5,
            "executable_sha256": "a" * 64,
            "bundle_tree_sha256": "b" * 64,
            "window_token": "VFQ-0123456789ab-L1",
        },
        {
            "launch_id": "launch-two",
            "launch_sequence": 2,
            "pid": 7002,
            "create_time": 202.5,
            "executable_sha256": "a" * 64,
            "bundle_tree_sha256": "b" * 64,
            "window_token": "VFQ-0123456789ab-L2",
        },
    ]
    payload = _driver_trace(tmp_path, session_nonce=nonce, launches=launches)

    receipt = _validate_driver_trace(
        payload,
        profile="smoke",
        session_dir=tmp_path,
        session_nonce=nonce,
        launches=launches,
    )

    assert receipt["valid"] is True
    assert receipt["provenance_required"] is True
    assert receipt["invalid_provenance_events"] == []
    assert all(item["valid"] for item in receipt["provenance_receipts"])

    first_event = payload["events"][0]
    first_event["capture_method"] = "screencapture-window-id"
    first_event["capture_window_identity"] = {
        "verified": True,
        "owner_pid": first_event["window_owner_pid"],
        "window_id": 9999,
        "title": "VODForge Player — fixture",
    }
    assert (
        _validate_driver_trace(
            payload,
            profile="smoke",
            session_dir=tmp_path,
            session_nonce=nonce,
            launches=launches,
        )["valid"]
        is True
    )
    first_event["capture_window_identity"]["owner_pid"] = -1
    assert (
        _validate_driver_trace(
            payload,
            profile="smoke",
            session_dir=tmp_path,
            session_nonce=nonce,
            launches=launches,
        )["valid"]
        is False
    )


def test_driver_trace_rejects_pid_and_window_token_from_another_launch(
    tmp_path: Path,
) -> None:
    nonce = "0123456789abcdef0123456789abcdef"
    launches: list[dict[str, object]] = [
        {
            "launch_id": "launch-one",
            "launch_sequence": 1,
            "pid": 7001,
            "create_time": 101.5,
            "executable_sha256": "a" * 64,
            "bundle_tree_sha256": "b" * 64,
            "window_token": "VFQ-0123456789ab-L1",
        },
        {
            "launch_id": "launch-two",
            "launch_sequence": 2,
            "pid": 7002,
            "create_time": 202.5,
            "executable_sha256": "a" * 64,
            "bundle_tree_sha256": "b" * 64,
            "window_token": "VFQ-0123456789ab-L2",
        },
    ]
    payload = _driver_trace(tmp_path, session_nonce=nonce, launches=launches)
    progress = next(
        item
        for item in payload["events"]  # type: ignore[union-attr]
        if item["event"] == "progress_observed"
    )
    progress["pid"] = 7002
    progress["window_owner_pid"] = 7002
    progress["window_title_token"] = "VFQ-0123456789ab-L2"

    receipt = _validate_driver_trace(
        payload,
        profile="smoke",
        session_dir=tmp_path,
        session_nonce=nonce,
        launches=launches,
    )

    assert receipt["valid"] is False
    assert receipt["structural_valid"] is False
    assert receipt["invalid_provenance_events"] == ["progress_observed"]
    progress_receipt = next(
        item
        for item in receipt["provenance_receipts"]
        if item["event"] == "progress_observed"
    )
    assert set(progress_receipt["errors"]) == {
        "pid mismatch",
        "window_owner_pid mismatch",
        "window_title_token mismatch",
        "native_window_identity is missing or invalid",
    }


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


@pytest.mark.parametrize(
    "defect",
    [
        None,
        "wrong_format",
        "missing_file",
        "changed_media",
        "missing_sentinel",
        "unbound_file",
    ],
)
def test_telemetry_persistence_covers_mixed_outputs_and_designated_description(
    tmp_path: Path, defect: str | None
) -> None:
    home = tmp_path / "home"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    items = []
    probes = []
    for suffix, output_type in (
        ("mp4", "MP4"),
        ("mp3", "MP3"),
        ("opus", "Original audio"),
        ("m4a", "Original audio"),
    ):
        media = downloads / f"export.{suffix}"
        media.write_bytes(suffix.encode())
        items.append(
            {
                "title": "Description fixture" if suffix == "mp4" else "Another source",
                "description": "sentinel"
                if suffix == "mp4"
                else "Ordinary description",
                "vodforge_output_type": output_type,
                "vodforge_encoding_summary": {
                    "output": {"Output file path": str(media)}
                },
            }
        )
        probes.append(
            {"path": str(media), "sha256": sha256_file(media), "readable": True}
        )
    history = (
        home / "Library" / "Application Support" / "VODForge" / "download-history.json"
    )
    history.parent.mkdir(parents=True)
    if defect == "wrong_format":
        items[-1]["vodforge_output_type"] = "MP3"
    elif defect == "missing_sentinel":
        items[0]["description"] = "truncated"
    elif defect == "unbound_file":
        items.pop()
    history.write_text(json.dumps({"items": items}))
    baseline = _persisted_state_snapshot(home)
    assert len(baseline["media"]) == 4
    if defect == "missing_file":
        Path(probes[-1]["path"]).unlink()
        probes.pop()
    elif defect == "changed_media":
        probes[-1]["sha256"] = "f" * 64
    receipt = _history_persistence_receipt(
        home,
        probes,
        [{}, {"reason": "driver_requested_restart"}],
        f"Loaded download history: {history}",
        baseline,
        expected_output_type=None,
        expected_description="sentinel",
        expected_description_title="Description fixture",
    )
    assert receipt["verified"] is (defect is None)
