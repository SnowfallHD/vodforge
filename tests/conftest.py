import pytest


@pytest.fixture
def production_telemetry_contract(monkeypatch):
    """Exercise release logic with the individual tests' fake transports only."""
    from yt_downloader import (
        analytics_consent,
        cloud_funnel,
        heycatch_telemetry,
        install_attribution,
        product_telemetry,
    )

    for module in (
        analytics_consent,
        cloud_funnel,
        heycatch_telemetry,
        install_attribution,
        product_telemetry,
    ):
        monkeypatch.setattr(module, "production_telemetry_allowed", lambda: True)
