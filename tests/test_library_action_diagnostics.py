"""Actual admission/removal producers, durable queue and private outbox."""

from __future__ import annotations

import json

import pytest

from yt_downloader.product_telemetry import _load_outbox

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


def diagnostic_rows(app, tmp_path):
    assert app.product_telemetry.shutdown(2)
    rows = [
        event.public_payload()
        for event in _load_outbox(tmp_path / "telemetry/events.json")
    ]
    encoded = json.dumps(rows)
    assert "Private" not in encoded and str(tmp_path) not in encoded
    assert "https://" not in encoded
    return [row for row in rows if row.get("feature") == "library_action_operation"]
