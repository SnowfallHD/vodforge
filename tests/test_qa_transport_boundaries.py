"""Marked QA cannot silently fall through to production collectors."""

import pytest

from yt_downloader import telemetry_policy
from yt_downloader.posthog_analytics import PosthogConfig


@pytest.mark.parametrize(
    "marker",
    ["VODFORGE_POSTHOG_QA_RUN", "VODFORGE_POSTHOG_QA_HOME", "VODFORGE_QA_PROFILE"],
)
def test_marked_qa_without_preview_credentials_is_off(tmp_path, monkeypatch, marker):
    monkeypatch.setattr(telemetry_policy.sys, "_MEIPASS", str(tmp_path), raising=False)
    (tmp_path / "VODFORGE_TELEMETRY_POLICY").write_text("production")
    monkeypatch.delenv("VODFORGE_DISABLE_TELEMETRY", raising=False)
    monkeypatch.delenv("VODFORGE_QUALITY_E2E", raising=False)
    monkeypatch.delenv("VODFORGE_QA_PREVIEW_TELEMETRY", raising=False)
    monkeypatch.delenv("VODFORGE_QA_ACCESS_KEY", raising=False)
    value = (
        "3a095a15-bef2-4e6b-bb7e-5df466c103c7"
        if marker == "VODFORGE_POSTHOG_QA_RUN"
        else str(tmp_path / "fictional-home")
    )
    monkeypatch.setenv(marker, value)
    assert not telemetry_policy.production_telemetry_allowed()
    assert not telemetry_policy.telemetry_collection_allowed()
    assert not PosthogConfig.from_environment({marker: value}).enabled


def test_credentialed_existing_preview_route_never_enables_provider(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(telemetry_policy.sys, "_MEIPASS", str(tmp_path), raising=False)
    (tmp_path / "VODFORGE_TELEMETRY_POLICY").write_text("production")
    monkeypatch.delenv("VODFORGE_DISABLE_TELEMETRY", raising=False)
    environment = {
        "VODFORGE_QUALITY_E2E": "1",
        "VODFORGE_QA_PREVIEW_TELEMETRY": "1",
        "VODFORGE_QA_ACCESS_KEY": "a" * 64,
        "VODFORGE_QA_PROFILE": str(tmp_path / "isolated"),
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    assert telemetry_policy.preview_telemetry_allowed()
    assert telemetry_policy.telemetry_collection_allowed()
    assert not telemetry_policy.production_telemetry_allowed()
    assert telemetry_policy.telemetry_site_origin() == telemetry_policy.PREVIEW_ORIGIN
    assert not PosthogConfig.from_environment(environment).enabled
