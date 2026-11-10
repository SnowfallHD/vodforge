"""Every event the app can send is accepted by the server.

The server rejects an event whose action or field value it doesn't know, and the
app then discards it as permanently rejected. 0.2.6 sends recovery_schema "2",
which the server didn't accept, so every 0.2.6 recovery event was thrown away.
This compares the app's closed vocabulary with the server's copy in the website
repository (checked out next to this one, as for the release gate).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from yt_downloader import telemetry_features

SERVER = (
    Path(__file__).resolve().parents[3] / "vodforge-site/src/lib/product-telemetry.ts"
)


def server_table(name: str) -> dict[str, list[str]]:
    source = SERVER.read_text(encoding="utf-8")
    match = re.search(
        r"export const " + name + r"[^=]*=\s*(\{.*?\});\n", source, re.DOTALL
    )
    assert match, f"{name} not found in {SERVER}"
    return json.loads(match.group(1))


@pytest.mark.skipif(not SERVER.is_file(), reason="website repository not checked out")
def test_server_accepts_every_action_the_app_can_send():
    server = server_table("FEATURE_ACTIONS")
    missing = {
        feature: sorted(set(actions) - set(server.get(feature, [])))
        for feature, actions in telemetry_features.FEATURE_ACTIONS.items()
        if set(actions) - set(server.get(feature, []))
    }
    assert not missing, missing


@pytest.mark.skipif(not SERVER.is_file(), reason="website repository not checked out")
def test_server_accepts_every_dimension_value_the_app_can_send():
    server = server_table("DIMENSION_CHOICES")
    missing = {
        name: sorted(set(values) - set(server.get(name, [])))
        for name, values in telemetry_features.DIMENSION_CHOICES.items()
        if set(values) - set(server.get(name, []))
    }
    assert not missing, missing
