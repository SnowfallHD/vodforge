from pathlib import Path

import pytest

from yt_downloader import telemetry_policy


@pytest.mark.parametrize(
    "marker,allowed",
    [(None, False), ("disabled", False), ("invalid", False), ("production", True)],
)
def test_build_policy(tmp_path, monkeypatch, marker, allowed):
    monkeypatch.delenv("VODFORGE_DISABLE_TELEMETRY", raising=False)
    monkeypatch.delenv("VODFORGE_QUALITY_E2E", raising=False)
    monkeypatch.setattr(telemetry_policy.sys, "_MEIPASS", str(tmp_path), raising=False)
    if marker is not None:
        (tmp_path / "VODFORGE_TELEMETRY_POLICY").write_text(marker)
    assert telemetry_policy.production_telemetry_allowed() is allowed


@pytest.mark.parametrize(
    "override", ["VODFORGE_DISABLE_TELEMETRY", "VODFORGE_QUALITY_E2E"]
)
def test_journeys_suppress_even_release_artifacts(tmp_path, monkeypatch, override):
    monkeypatch.setattr(telemetry_policy.sys, "_MEIPASS", str(tmp_path), raising=False)
    (tmp_path / "VODFORGE_TELEMETRY_POLICY").write_text("production")
    monkeypatch.setenv(override, "1")
    assert not telemetry_policy.production_telemetry_allowed()


def test_source_checkout_cannot_enable_production(monkeypatch):
    monkeypatch.delattr(telemetry_policy.sys, "_MEIPASS", raising=False)
    monkeypatch.setenv("VODFORGE_BUILD_TELEMETRY", "production")
    assert not telemetry_policy.production_telemetry_allowed()


def test_disabled_transports_never_call_network(monkeypatch):
    from yt_downloader import (
        cloud_funnel,
        heycatch_telemetry,
        install_attribution,
        product_telemetry,
    )

    def forbidden(*args, **kwargs):
        pytest.fail("disabled telemetry attempted network access")

    for module in (
        cloud_funnel,
        heycatch_telemetry,
        install_attribution,
        product_telemetry,
    ):
        name = (
            "production_telemetry_allowed"
            if module is heycatch_telemetry
            else "telemetry_collection_allowed"
        )
        monkeypatch.setattr(module, name, lambda: False)
    assert not cloud_funnel._post_json("https://getvodforge.com", {}, opener=forbidden)
    assert not heycatch_telemetry._capture(
        "first_launch", "unused", {}, opener=forbidden
    )
    assert (
        install_attribution._post_json_object(
            "https://getvodforge.com", {}, opener=forbidden
        )
        is None
    )
    assert not product_telemetry._post_d1_event(None, opener=forbidden)


def test_release_builds_explicitly_enable_telemetry():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/release.yml").read_text()
    assert workflow.count("VODFORGE_BUILD_TELEMETRY: production") == 2
    for script in ("build_macos.sh", "build_windows.ps1"):
        assert "VODFORGE_TELEMETRY_POLICY" in (root / script).read_text()


def test_disabled_owners_do_not_open_browser_or_persist_delivery(tmp_path, monkeypatch):
    from yt_downloader import install_attribution, product_telemetry
    from yt_downloader.cloud_funnel import (
        CLOUD_PAGE_URL,
        InstallationState,
        cloud_page_url,
    )

    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")

    def forbidden(*args, **kwargs):
        pytest.fail("test run attempted external delivery")

    path = tmp_path / "installation.json"
    state = InstallationState(install_id="8ea7e42f-6b48-4110-9e92-aaf94e4f0f3a")
    owner = install_attribution.InstallationAttributionOwner(
        path, first_party_recorder=forbidden, browser_opener=forbidden
    )
    assert owner.deliver_first_launch(state, app_version="0.1.8") == state
    assert not path.exists()
    assert cloud_page_url(state.install_id) == CLOUD_PAGE_URL
    outbox = tmp_path / "events.json"
    events = product_telemetry.ProductTelemetryOwner(
        state_path=outbox,
        installation_state_path=path,
        app_version="0.1.8",
        d1_recorder=forbidden,
        heycatch_recorder=forbidden,
    )
    assert not events.record_app_opened()
    events._flush()
    assert not outbox.exists()
