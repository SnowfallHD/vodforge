from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from yt_downloader.cloud_funnel import (
    CLOUD_CLICK_ENDPOINT,
    CLOUD_LAUNCH_ENDPOINT,
    CLOUD_SEEN_ENDPOINT,
    InstallationIdentityError,
    InstallationState,
    cloud_page_url,
    installation_platform,
    installation_state_path,
    load_or_create_installation_state,
    mark_first_launch_confirmed,
    mark_cloud_seen_confirmed,
    record_cloud_click,
    record_first_launch,
    record_cloud_seen,
)


class JsonResponse:
    status = 200

    def __enter__(self) -> "JsonResponse":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return b'{"ok":true}'


def test_installation_state_uses_normal_app_data_and_persists_across_reloads(tmp_path: Path):
    path = installation_state_path(data_dir=tmp_path / "VODForge")
    first = load_or_create_installation_state(path)
    second = load_or_create_installation_state(path)

    assert path == tmp_path / "VODForge" / "installation.json"
    assert second.install_id == first.install_id
    assert second.first_launch_confirmed is False
    assert second.cloud_seen_confirmed is False
    assert json.loads(path.read_text(encoding="utf-8"))["install_id"] == first.install_id


def test_marking_seen_preserves_install_id_across_restart(tmp_path: Path):
    path = installation_state_path(data_dir=tmp_path)
    original = load_or_create_installation_state(path)
    marked = mark_cloud_seen_confirmed(path, original.install_id)
    restarted = load_or_create_installation_state(path)

    assert marked.install_id == original.install_id
    assert restarted == marked
    assert restarted.cloud_seen_confirmed is True


def test_marking_first_launch_persists_across_restart_and_version_changes(tmp_path: Path):
    path = installation_state_path(data_dir=tmp_path)
    original = load_or_create_installation_state(path)
    marked = mark_first_launch_confirmed(path, original.install_id)
    restarted = load_or_create_installation_state(path)

    assert marked.install_id == original.install_id
    assert restarted == marked
    assert restarted.first_launch_confirmed is True
    assert restarted.cloud_seen_confirmed is False


def test_existing_installation_state_without_launch_flag_remains_compatible(tmp_path: Path):
    path = installation_state_path(data_dir=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "schema_version": 1,
            "install_id": "f9c775b1-4c5a-47c4-87bb-81fe51881e54",
            "cloud_seen_confirmed": True,
        }),
        encoding="utf-8",
    )

    state = load_or_create_installation_state(path)

    assert state.first_launch_confirmed is False
    assert state.cloud_seen_confirmed is True


def test_invalid_state_is_not_silently_replaced(tmp_path: Path):
    path = installation_state_path(data_dir=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"install_id":"hardware-derived"}', encoding="utf-8")

    with pytest.raises(InstallationIdentityError, match="unsupported schema"):
        load_or_create_installation_state(path)

    assert path.read_text(encoding="utf-8") == '{"install_id":"hardware-derived"}'


def test_platform_mapping_is_narrow_and_non_identifying():
    assert installation_platform("darwin") == "macos"
    assert installation_platform("win32") == "windows"
    assert installation_platform("linux") == "linux"
    assert installation_platform("freebsd") == "unknown"


def test_seen_payload_reuses_same_id_when_app_version_changes():
    state = InstallationState("f9c775b1-4c5a-47c4-87bb-81fe51881e54")
    requests: list[tuple[str, dict[str, str]]] = []

    def opener(request: Any, *, timeout: float) -> JsonResponse:
        assert timeout == 4.0
        requests.append((request.full_url, json.loads(request.data.decode("utf-8"))))
        return JsonResponse()

    assert record_cloud_seen(state, app_version="0.1.4", platform_name="darwin", opener=opener)
    assert record_cloud_seen(state, app_version="0.2.0", platform_name="darwin", opener=opener)
    assert [request[0] for request in requests] == [CLOUD_SEEN_ENDPOINT, CLOUD_SEEN_ENDPOINT]
    assert {request[1]["install_id"] for request in requests} == {state.install_id}
    assert [request[1]["app_version"] for request in requests] == ["0.1.4", "0.2.0"]


def test_first_launch_payload_reuses_install_id_and_reports_platform_and_version():
    state = InstallationState("f9c775b1-4c5a-47c4-87bb-81fe51881e54")
    captured: dict[str, Any] = {}

    def opener(request: Any, *, timeout: float) -> JsonResponse:
        captured.update(url=request.full_url, payload=json.loads(request.data.decode("utf-8")), timeout=timeout)
        return JsonResponse()

    assert record_first_launch(state, app_version="0.1.5", platform_name="win32", opener=opener)
    assert captured == {
        "url": CLOUD_LAUNCH_ENDPOINT,
        "payload": {
            "install_id": state.install_id,
            "platform": "windows",
            "app_version": "0.1.5",
        },
        "timeout": 4.0,
    }


def test_click_payload_and_cloud_url_contain_only_random_install_id():
    state = InstallationState("f9c775b1-4c5a-47c4-87bb-81fe51881e54")
    captured: dict[str, Any] = {}

    def opener(request: Any, *, timeout: float) -> JsonResponse:
        captured.update(url=request.full_url, payload=json.loads(request.data.decode("utf-8")), timeout=timeout)
        return JsonResponse()

    assert record_cloud_click(state, opener=opener)
    assert captured == {
        "url": CLOUD_CLICK_ENDPOINT,
        "payload": {"install_id": state.install_id},
        "timeout": 4.0,
    }
    assert cloud_page_url(state.install_id) == f"https://getvodforge.com/cloud?iid={state.install_id}"
    assert cloud_page_url(None) == "https://getvodforge.com/cloud"
