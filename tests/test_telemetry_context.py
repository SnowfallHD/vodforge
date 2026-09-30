"""Bounded environment/failure evidence and independently opted-in attachments."""

import errno
import json
from types import SimpleNamespace

import pytest

from yt_downloader import telemetry_features
from yt_downloader.failure_diagnostics import capture_failure, validate_failure_detail
from yt_downloader.support_diagnostics import FailureContext, diagnostics_attachment
from yt_downloader.support_payload import feedback_payload

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


@pytest.mark.parametrize(
    "message,expected",
    [
        (
            "could not find firefox cookies database in /Users/PRIVATE",
            "database_missing",
        ),
        ("Could not copy Chrome cookie database", "database_access_denied"),
        ("cookies database is locked PRIVATE", "database_locked"),
        ("failed to decrypt cookie PRIVATE_TOKEN", "decryption_failed"),
        (
            "cookies.txt does not look like a Netscape format cookies file",
            "invalid_cookie_file",
        ),
        ("cookies are no longer valid PRIVATE", "expired"),
        ("cookies unavailable PRIVATE", "unknown"),
        ("HTTP Error 403", None),
        ("Sign in to confirm your age", None),
    ],
)
def test_cookie_failure_records_observed_reason_without_secret_or_expiration_guess(
    message, expected
):
    detail = capture_failure(RuntimeError(message)).payload()
    assert detail.get("cookie_failure") == expected
    assert "PRIVATE" not in json.dumps(detail)
    assert validate_failure_detail(detail).payload() == detail
    assert (
        "cookie_failure"
        not in capture_failure(RuntimeError(message), inspect_text=False).payload()
    )


@pytest.mark.parametrize(
    "path,style,units,component",
    [
        ("/Users/PRIVATE/movie.mp4", "posix", 24, 9),
        (r"C:\Users\PRIVATE\movie.mp4", "windows", 26, 9),
        (r"\\SERVER\PRIVATE\movie.mp4", "windows", 26, 9),
        ("/PRIVATE/😀.mp4", "posix", 17, 8),
    ],
)
def test_actual_os_path_failure_reports_lengths_not_content(
    path, style, units, component
):
    detail = capture_failure(
        PermissionError(errno.EACCES, "PRIVATE", path), inspect_text=False
    ).payload()
    assert detail["reason"] == "permission_denied"
    assert detail["path_style"] == style
    assert detail["path_units"] == units
    assert detail["path_longest_component_bytes"] == component
    assert "PRIVATE" not in json.dumps(detail) and "SERVER" not in json.dumps(detail)
    validate_failure_detail(detail)


def test_trace_records_only_shipped_frames_without_locals_or_filenames():
    namespace = {"__name__": "yt_downloader.export_planning"}
    exec(  # noqa: S102 - fixed synthetic traceback fixture, never input
        compile(
            'def inner():\n    secret="PRIVATE"\n    raise RuntimeError(secret)\ndef outer():\n    inner()\n',
            "/Users/PRIVATE/module.py",
            "exec",
        ),
        namespace,
    )
    try:
        namespace["outer"]()
    except RuntimeError as error:
        detail = capture_failure(error).payload()
    assert detail["source_trace"] == "export_planning:5>export_planning:3"
    assert detail["source_line"] == 3
    assert "PRIVATE" not in json.dumps(detail)
    validate_failure_detail(detail)


@pytest.mark.parametrize(
    "detail",
    [
        {"cookie_failure": "token=PRIVATE"},
        {"source_trace": "/Users/PRIVATE/module.py:2"},
        {"source_trace": "app:1>" * 8 + "app:1"},
        {"source_trace": "app:0"},
        {"path_units": 4},
        {
            "path_style": "windows",
            "path_units": 1,
            "path_component_count": 1,
            "path_longest_component_bytes": True,
        },
    ],
)
def test_automatic_context_rejects_arbitrary_values_and_incomplete_facts(detail):
    with pytest.raises((ValueError, TypeError)):
        validate_failure_detail(detail)


@pytest.mark.parametrize(
    "system,value,expected",
    [
        ("Darwin", "15.6.1", "15.6.1"),
        ("Windows", "10.0.26100", "10.0.26100"),
        ("Linux", "6.8.0-PRIVATE-HOST", "6.8.0"),
        ("Linux", "PRIVATE-HOST", None),
    ],
)
def test_system_context_preserves_numeric_versions_without_host_suffix(
    monkeypatch, system, value, expected
):
    telemetry_features.system_dimensions.cache_clear()
    monkeypatch.setattr(telemetry_features.platform, "system", lambda: system)
    monkeypatch.setattr(telemetry_features.platform, "mac_ver", lambda: (value, "", ""))
    monkeypatch.setattr(
        telemetry_features.platform, "win32_ver", lambda: ("", value, "", "")
    )
    monkeypatch.setattr(telemetry_features.platform, "release", lambda: value)
    try:
        details = telemetry_features.system_dimensions()
        assert details.get("os_version") == expected
        assert "PRIVATE" not in json.dumps(details)
        telemetry_features.validate_dimensions(details)
    finally:
        telemetry_features.system_dimensions.cache_clear()


def test_resource_unavailability_does_not_break_telemetry(monkeypatch):
    monkeypatch.setattr(
        telemetry_features.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=16 * 1024**3, available=3 * 1024**3),
    )
    assert telemetry_features.resource_dimensions() == {
        "memory_total_mb": "16384",
        "memory_available_mb": "3072",
    }

    def unavailable():
        raise OSError("PRIVATE")

    monkeypatch.setattr(telemetry_features.psutil, "virtual_memory", unavailable)
    assert telemetry_features.resource_dimensions() == {}


@pytest.mark.parametrize(
    "diagnostics,source,folder",
    [
        (False, False, False),
        (False, True, True),
        (True, False, False),
        (True, True, True),
    ],
)
def test_support_attachments_have_separate_consent_and_exact_preview(
    diagnostics, source, folder
):
    context = FailureContext(
        "bounded evidence",
        "https://youtu.be/8mv2Gonsdog?list=PRIVATE&token=PRIVATE",
        r"C:\Users\PRIVATE\Videos",
    )
    payload = feedback_payload(
        reason="Other",
        message="Report",
        include_diagnostics=diagnostics,
        include_video_url=source,
        include_output_folder=folder,
        context=context,
    )
    assert payload["diagnostics"] == diagnostics_attachment(
        context, include_diagnostics=diagnostics, include_output_folder=folder
    )
    assert ("PRIVATE" in payload["diagnostics"]) is (diagnostics and folder)
    assert payload["video_url"] == (
        "https://www.youtube.com/watch?v=8mv2Gonsdog" if source else ""
    )
    assert "token" not in payload["video_url"]


def test_optional_folder_cannot_overflow_or_inject_preview_lines():
    for folder in ("x" * 10000, "PRIVATE\nCookie: secret"):
        context = FailureContext("bounded evidence", output_folder=folder)
        assert (
            diagnostics_attachment(
                context, include_diagnostics=True, include_output_folder=True
            )
            == "bounded evidence"
        )
    context = FailureContext("e" * 6000, output_folder="x" * 1024)
    assert (
        len(
            diagnostics_attachment(
                context, include_diagnostics=True, include_output_folder=True
            )
        )
        <= 6000
    )


@pytest.mark.parametrize("permitted", [False, True])
def test_context_is_collected_only_after_permission_and_survives_immutable_replay(
    tmp_path, monkeypatch, permitted
):
    from yt_downloader import product_telemetry
    from yt_downloader.analytics_consent import AnalyticsConsentOwner
    from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox

    consent = AnalyticsConsentOwner(tmp_path)
    consent.choose(permitted)
    harvested = []

    def collect():
        harvested.append(True)
        return {"os_version": "10.0.26100", "cpu_logical_count": "16"}

    monkeypatch.setattr(product_telemetry, "system_dimensions", collect)
    monkeypatch.setattr(
        product_telemetry, "resource_dimensions", lambda: {"memory_available_mb": "42"}
    )
    path = tmp_path / "product-telemetry.json"
    owner = ProductTelemetryOwner(
        state_path=path,
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.2",
        d1_recorder=lambda _: False,
        heycatch_recorder=lambda *_a, **_kw: False,
    )
    owner.observe_nvidia_driver("572.83")
    assert owner.record_app_opened() is permitted
    assert (
        owner.record(
            "run_failed",
            failure_detail=capture_failure(
                RuntimeError("failed to decrypt cookie PRIVATE")
            ).payload(),
        )
        is permitted
    )
    assert owner.shutdown(2)
    if not permitted:
        assert harvested == []
        assert not path.exists()
        return
    stored = [e.public_payload() for e in _load_outbox(path)]
    for event in stored:
        assert event["dimensions"]["os_version"] == "10.0.26100"
        assert event["dimensions"]["nvidia_driver"] == "572.83"
        assert event["dimensions"]["memory_available_mb"] == "42"
        assert "PRIVATE" not in json.dumps(event)
    assert stored[1]["failure_detail"]["cookie_failure"] == "decryption_failed"
    harvested.clear()
    delivered = []
    restarted = ProductTelemetryOwner(
        state_path=path,
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.2",
        d1_recorder=lambda e: delivered.append(e.public_payload()) is None,
        heycatch_recorder=lambda *_a, **_kw: True,
    )
    restarted.flush_async()
    assert restarted.shutdown(2)
    assert delivered == stored and harvested == []


def test_nvidia_context_rejects_non_numeric_driver_data(tmp_path):
    from yt_downloader.product_telemetry import ProductTelemetryOwner

    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events",
        installation_state_path=tmp_path / "installation",
        app_version="0.2.2",
        enabled=False,
    )
    with pytest.raises(ValueError):
        owner.observe_nvidia_driver("PRIVATE-UUID")
