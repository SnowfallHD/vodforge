"""Focused regression gate: useful evidence without private content or host CA files."""

import json
import ssl
import urllib.error
from types import SimpleNamespace

import pytest

from yt_downloader.failure_diagnostics import capture_failure, validate_failure_detail
from yt_downloader.telemetry_features import export_dimensions


def test_source_selection_failure_retains_counts_without_private_formats():
    from yt_downloader.export_planning import _select_auto_sources

    formats = [
        {
            "vcodec": "none",
            "acodec": "aac",
            "url": "https://private/token",
            "format_id": "private",
        }
    ]
    with pytest.raises(RuntimeError) as caught:
        _select_auto_sources(formats, 1080)
    detail = capture_failure(caught.value, stage="preparation").payload()
    assert detail["failure_code"] == "no_video_stream"
    assert (
        detail["format_count"],
        detail["video_format_count"],
        detail["audio_format_count"],
    ) == (1, 0, 1)
    assert "private" not in json.dumps(detail)
    assert validate_failure_detail(detail).payload() == detail


def test_possible_provider_causes_do_not_override_observed_empty_formats():
    from yt_downloader.failure_diagnostics import capture_failure

    error = RuntimeError(
        "No usable video source was found. This can happen when a JavaScript "
        "runtime is missing or the site is rate limiting the connection."
    )
    detail = capture_failure(error, stage="analysis").payload()
    assert detail["failure_code"] == "no_video_stream"
    assert detail["reason"] == "unsupported_format"
    assert "deno" not in json.dumps(detail).lower()


def test_nested_certificate_reason_survives_generic_wrapper():
    cause = ssl.SSLCertVerificationError(1, "private hostname and path")
    cause.verify_code = 20
    wrapped = urllib.error.URLError(cause)
    error = RuntimeError("generic failure")
    error.__cause__ = wrapped
    detail = capture_failure(error).payload()
    assert detail["failure_code"] == "tls_certificate"
    assert detail["tls_verify_code"] == 20
    assert detail["reason"] == "network"
    assert "private" not in json.dumps(detail)


def test_cookie_change_is_visible_without_cookie_identity():
    job = SimpleNamespace(url="https://youtube.com/watch?v=private", use_cookies=False)
    before = export_dimensions(job)
    job.use_cookies = True
    job.cookie_browser = "private-browser-profile"
    after = export_dimensions(job)
    assert before["cookie_access"] == "disabled"
    assert after["cookie_access"] == "browser"
    assert after["provider"] == "youtube"
    assert "private" not in json.dumps(after)


def test_update_context_has_roots_without_developer_certificate_paths(monkeypatch):
    from yt_downloader import updates

    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent-vodforge-cert.pem")
    monkeypatch.setenv("SSL_CERT_DIR", "/nonexistent-vodforge-certs")
    monkeypatch.setattr(updates, "qa_update_feed", lambda: None)
    observed = []

    def open_request(request, *, timeout, context):
        observed.append(context)
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname
        assert context.cert_store_stats()["x509_ca"] > 50
        return object()

    monkeypatch.setattr(updates.urllib.request, "urlopen", open_request)
    updates._open_update_request(
        urllib.request.Request(updates.LATEST_RELEASE_API), timeout=1
    )
    assert len(observed) == 1


@pytest.mark.parametrize(
    "key,value",
    [
        ("failure_code", "https://private"),
        ("format_count", -1),
        ("tls_verify_code", True),
        ("message", "private"),
    ],
)
def test_diagnostic_allowlist_rejects_content(key, value):
    with pytest.raises(ValueError):
        validate_failure_detail({key: value})


def test_settings_projection_excludes_sensitive_and_unknown_preferences():
    from yt_downloader.telemetry_features import (
        settings_dimensions,
        validate_dimensions,
    )

    values = {
        "output_type": "MP4",
        "manual_crf": "23",
        "write_info_json": True,
        "output_dir": "/Users/private",
        "cookie_file": "secret",
        "tags": "private",
        "custom_accent": "#123456",
        "future_setting": "private",
    }
    projected = settings_dimensions(values)
    assert projected == {
        "setting_output_type": "MP4",
        "setting_manual_crf": "23",
        "setting_write_info_json": "enabled",
    }
    assert validate_dimensions(projected) == projected


@pytest.mark.usefixtures("production_telemetry_contract")
def test_settings_transitions_preserve_a_b_a_and_suppress_unchanged(tmp_path):
    from tests.test_product_telemetry import _permitted_installation
    from yt_downloader.product_telemetry import ProductTelemetryOwner

    _permitted_installation(tmp_path / "installation.json")
    seen = []
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.2",
        d1_recorder=lambda e: seen.append(e) or True,
        heycatch_recorder=lambda *_a, **_k: True,
    )
    for choice in ("disabled", "disabled", "browser", "disabled"):
        assert owner.record_feature(
            "settings", "snapshot", dimensions={"cookie_access": choice}
        )
        assert owner.shutdown(2)
    assert [e.dimensions for e in seen] == [
        {"cookie_access": "disabled"},
        {"cookie_access": "browser"},
        {"cookie_access": "disabled"},
    ]


def test_packaged_runtime_gate_rejects_missing_certificate_bundle(monkeypatch):
    from yt_downloader import app

    def missing():
        raise FileNotFoundError("certificate bundle absent")

    monkeypatch.setattr(app, "update_ssl_context", missing)
    assert app.runtime_smoke() == 1


def test_qt_packaged_runtime_gate_requires_deno_but_not_legacy_player(monkeypatch):
    from yt_downloader import app

    class Roots:
        def cert_store_stats(self):
            return {"x509_ca": 100}

    monkeypatch.setattr(app, "update_ssl_context", Roots)
    monkeypatch.setattr(
        app.DownloaderApp, "_find_ffmpeg", staticmethod(lambda: "ffmpeg")
    )
    monkeypatch.setattr(
        app.DownloaderApp, "_find_ffprobe", staticmethod(lambda: "ffprobe")
    )
    monkeypatch.setattr(app.DownloaderApp, "_find_deno", staticmethod(lambda: "deno"))
    monkeypatch.setattr(app, "probe_runtime_version", lambda name, _path: name)
    monkeypatch.setattr(
        app, "_smoke_ytdlp_stack", lambda: ("pinned", "pinned", ("solver",))
    )
    monkeypatch.setattr(app, "find_libvlc_runtime", lambda: None)
    assert app.runtime_smoke(require_libvlc=False) == 0
    assert app.runtime_smoke() == 1
    monkeypatch.setattr(app.DownloaderApp, "_find_deno", staticmethod(lambda: None))
    assert app.runtime_smoke(require_libvlc=False) == 1


def test_every_persisted_setting_has_an_explicit_privacy_decision():
    import ast
    import inspect
    import textwrap

    from yt_downloader.app import DownloaderApp
    from yt_downloader.telemetry_features import SETTINGS_BOOLEANS, SETTINGS_CHOICES

    tree = ast.parse(
        textwrap.dedent(inspect.getsource(DownloaderApp._settings_variables))
    )
    keys = {
        key.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key in node.keys
        if isinstance(key, ast.Constant)
    }
    excluded = {"output_dir", "custom_accent", "whats_new_seen"}
    bucketed = {"manual_video_bitrate", "manual_audio_bitrate"}
    assert keys == set(SETTINGS_CHOICES) | SETTINGS_BOOLEANS | bucketed | excluded


def test_settings_save_failure_does_not_report_successful_snapshot(
    tmp_path, monkeypatch
):
    from tests.test_settings_store import _Scheduler, _Variable
    from yt_downloader import settings_store

    seen = []
    owner = settings_store.SettingsPersistenceOwner(
        tmp_path / "settings.json", on_saved=seen.append
    )
    owner.bind(_Scheduler(), {"output_type": _Variable("MP4")})

    def fail(*_args):
        raise settings_store.SettingsError("disk full")

    monkeypatch.setattr(settings_store, "save_settings", fail)
    owner.flush()
    assert seen == []
