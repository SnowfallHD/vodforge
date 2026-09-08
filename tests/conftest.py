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
        name = (
            "production_telemetry_allowed"
            if module is heycatch_telemetry
            else "telemetry_collection_allowed"
        )
        monkeypatch.setattr(module, name, lambda: True)
