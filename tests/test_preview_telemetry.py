import urllib.request

import pytest

from yt_downloader import telemetry_policy as policy
from yt_downloader import telemetry_transport as transport


@pytest.fixture
def preview(tmp_path, monkeypatch):
    monkeypatch.setattr(policy.sys, "_MEIPASS", str(tmp_path), raising=False)
    (tmp_path / "VODFORGE_TELEMETRY_POLICY").write_text("preview")
    monkeypatch.delenv("VODFORGE_DISABLE_TELEMETRY", raising=False)
    monkeypatch.setenv("VODFORGE_QUALITY_E2E", "1")
    monkeypatch.setenv("VODFORGE_QA_ACCESS_KEY", "a" * 64)
    monkeypatch.setenv("VODFORGE_QA_PROFILE", str(tmp_path / "profile"))
    return tmp_path


def test_explicit_preview_is_never_production(preview):
    assert policy.preview_telemetry_allowed()
    assert policy.telemetry_collection_allowed()
    assert not policy.production_telemetry_allowed()
    from yt_downloader.history import application_data_dir

    assert application_data_dir() == preview / "profile"


@pytest.mark.parametrize(
    "variable,value",
    [
        ("VODFORGE_QA_ACCESS_KEY", ""),
        ("VODFORGE_QA_PROFILE", "relative"),
        ("VODFORGE_DISABLE_TELEMETRY", "1"),
    ],
)
def test_preview_requires_complete_explicit_configuration(
    preview, monkeypatch, variable, value
):
    monkeypatch.setenv(variable, value)
    assert not policy.telemetry_collection_allowed()


@pytest.mark.parametrize("marker", ["disabled", "production", "invalid"])
def test_qa_flags_cannot_enable_other_builds(preview, marker):
    (preview / "VODFORGE_TELEMETRY_POLICY").write_text(marker)
    assert not policy.telemetry_collection_allowed()


def test_fixed_preview_transport_preserves_payload(preview, monkeypatch):
    observed = []

    class Opener:
        def open(self, request, **kwargs):
            observed.append(request)
            return "response"

    monkeypatch.setattr(transport.urllib.request, "build_opener", lambda *_: Opener())
    req = urllib.request.Request(
        "https://getvodforge.com/api/funnel/launch",
        data=b"{}",
        headers={"Authorization": "Bearer test"},
    )
    assert transport.telemetry_urlopen(req, timeout=1) == "response"
    assert observed[0].full_url == policy.PREVIEW_ORIGIN + "/api/funnel/launch"
    assert observed[0].data == b"{}"
    assert observed[0].get_header("User-agent") == "VODForge"
    assert observed[0].get_header("X-vodforge-qa-key") == "a" * 64


@pytest.mark.parametrize(
    "url",
    [
        "https://in.heycatch.ai/capture/",
        "http://getvodforge.com/api/funnel/launch",
        "https://getvodforge.com.evil/api/funnel/launch",
        "https://getvodforge.com/pro",
    ],
)
def test_preview_rejects_every_other_destination(preview, url):
    with pytest.raises(OSError):
        transport.telemetry_urlopen(urllib.request.Request(url))


def test_preview_forbids_redirects(preview):
    with pytest.raises(OSError):
        transport._NoRedirect().redirect_request(
            None, None, 302, "", {}, "https://getvodforge.com"
        )


def test_signed_release_can_only_route_to_preview_with_explicit_qa(
    preview, monkeypatch
):
    (preview / "VODFORGE_TELEMETRY_POLICY").write_text("production")
    monkeypatch.setenv("VODFORGE_QA_PREVIEW_TELEMETRY", "1")
    assert policy.preview_telemetry_allowed()
    assert not policy.production_telemetry_allowed()
    monkeypatch.delenv("VODFORGE_QUALITY_E2E")
    assert not policy.telemetry_collection_allowed()


def test_disabled_artifact_cannot_be_enabled_by_release_qa(preview, monkeypatch):
    (preview / "VODFORGE_TELEMETRY_POLICY").write_text("disabled")
    monkeypatch.setenv("VODFORGE_QA_PREVIEW_TELEMETRY", "1")
    assert not policy.telemetry_collection_allowed()
