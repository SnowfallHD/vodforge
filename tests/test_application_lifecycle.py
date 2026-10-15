import json
import subprocess
import sys
import threading
import uuid
from dataclasses import replace

import psutil
import pytest

from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.application_lifecycle import ApplicationLifecycle
from yt_downloader.posthog_analytics import (
    PosthogConfig,
    PosthogEventSink,
    capture_payload,
)
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


class Sink:
    enabled = True

    def __init__(self):
        self.events = []

    def __call__(self, event):
        self.events.append(event)
        return True


def setup_owner(tmp_path, *, recorder=lambda event: True):
    consent = AnalyticsConsentOwner(tmp_path)
    consent.choose(True)
    consent.choose_posthog(True)
    sink = Sink()
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.6",
        d1_recorder=recorder,
        posthog_recorder=sink,
    )
    return consent, owner, sink


def test_real_owner_session_context_survives_queue_retry_and_consent_rotation(
    tmp_path, monkeypatch
):
    qa = str(uuid.uuid4())
    monkeypatch.setenv("VODFORGE_POSTHOG_QA_RUN", qa)
    consent, owner, sink = setup_owner(tmp_path, recorder=lambda event: False)
    assert owner.record_app_opened()
    assert owner.shutdown(3)
    pending = _load_outbox(tmp_path / "events.json")[0]
    assert uuid.UUID(pending.posthog_session_id).version == 7
    payload = capture_payload(pending)
    props = payload["properties"]
    assert props["$session_id"] == pending.posthog_session_id
    assert props["qa_run_id"] == props["validation_id"] == qa
    assert props["is_test"] and props["release_channel"] == "test"
    assert props["measurement_scope"] == "qa" and props["schema_version"] == "2"
    assert props["event_sequence"] == 1
    assert not any(key.startswith("posthog_") for key in pending.public_payload())
    owner.flush_async()
    assert owner.shutdown(3)
    assert len(sink.events) == 1  # retry does not create a new session/event
    assert (
        _load_outbox(tmp_path / "events.json")[0].posthog_session_id
        == pending.posthog_session_id
    )
    consent.choose(False)
    owner.set_enabled(False)
    consent.choose(True)
    owner.set_enabled(True)
    assert owner.record("playback_started") and owner.shutdown(3)
    current = _load_outbox(tmp_path / "events.json")[0]
    assert current.posthog_session_id != pending.posthog_session_id
    assert current.posthog_sequence == 1
    consent.choose_posthog(False)
    assert owner.record("run_started") and owner.shutdown(3)
    assert len(sink.events) == 2


def test_normal_lifecycle_and_real_dead_marker_are_content_free(tmp_path):
    consent, owner, sink = setup_owner(tmp_path)
    lifecycle = ApplicationLifecycle(owner, tmp_path)
    lifecycle.ready()
    lifecycle.tick()
    lifecycle.foreground(True)
    lifecycle.foreground(True)
    lifecycle.foreground(False)
    marker = lifecycle._marker
    assert marker and marker.exists()
    # A second live instance must never report this first process as a crash.
    other = ApplicationLifecycle(owner, tmp_path)
    other.tick()
    other.close()
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    pid = process.pid
    process.wait(timeout=5)
    dead = json.loads(marker.read_text())
    dead["pid"] = pid
    dead_marker = marker.parent / (str(uuid.uuid4()) + ".json")
    dead_marker.write_text(json.dumps(dead))
    successor = ApplicationLifecycle(owner, tmp_path)
    successor.tick()
    successor.close()
    lifecycle.close()
    assert owner.shutdown(3)
    actions = [e.action for e in sink.events]
    assert actions.count("unclean_previous_exit") == 1
    assert actions.count("foreground") == actions.count("background") == 1
    assert "startup_ready" in actions and "session_ended" in actions
    assert not list(marker.parent.glob("*.json"))
    assert all(e.feature == "application_lifecycle" for e in sink.events)
    consent.choose(False)


def test_unknown_process_and_revoked_epoch_preserve_privacy(tmp_path, monkeypatch):
    consent, owner, sink = setup_owner(tmp_path)
    first = ApplicationLifecycle(owner, tmp_path)
    first.tick()
    marker = first._marker
    original = psutil.Process

    def unknown(pid=None):
        if pid is not None:
            raise psutil.AccessDenied(pid)
        return original()

    monkeypatch.setattr(psutil, "Process", unknown)
    second = ApplicationLifecycle(owner, tmp_path)
    second.tick()
    assert marker.exists()
    second.close()
    consent.choose(False)
    owner.set_enabled(False)
    first.tick()
    first.report_exception(ValueError, "main_thread")
    first.close()
    assert not marker.exists()
    assert owner.shutdown(3)
    assert not any(e.action == "unclean_previous_exit" for e in sink.events)


def test_hooks_chain_restore_and_never_inspect_exception_contents(
    tmp_path, monkeypatch
):
    _, owner, sink = setup_owner(tmp_path)
    lifecycle = ApplicationLifecycle(owner, tmp_path)
    called = []
    previous = lambda *args: called.append("main")
    monkeypatch.setattr(sys, "excepthook", previous)
    monkeypatch.setattr(threading, "excepthook", lambda args: called.append("worker"))
    lifecycle.install_exception_hooks()
    error = ValueError("PRIVATE /Users/secret/media.mp4?token=private")
    sys.excepthook(ValueError, error, None)
    sys.excepthook(ValueError, error, None)

    class Args:
        exc_type = RuntimeError

    threading.excepthook(Args())
    lifecycle.close()
    assert sys.excepthook is previous
    assert called == ["main", "main", "worker"]
    assert owner.shutdown(3)
    assert len(sink.events) == 2
    assert "PRIVATE" not in json.dumps([capture_payload(e) for e in sink.events])


def test_sanitized_exception_has_one_canonical_event_and_issue_companion(tmp_path):
    _, owner, sink = setup_owner(tmp_path)
    lifecycle = ApplicationLifecycle(owner, tmp_path)
    lifecycle.report_exception(OSError, "worker_thread")
    assert owner.shutdown(3)
    requests = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def opener(request, **kwargs):
        requests.append(json.loads(request.data))
        return Response()

    transport = PosthogEventSink(
        PosthogConfig(True, "phc_abcdefghijkl", "https://us.i.posthog.com"),
        opener=opener,
    )
    assert transport(sink.events[0])
    assert [r["event"] for r in requests] == ["vf_app_feature_used", "$exception"]
    issue = requests[1]["properties"]
    assert issue["$exception_list"][0]["stacktrace"]["frames"] == []
    assert issue["$exception_fingerprint"] == "vodforge:os_error:worker_thread"
    assert issue["$exception_level"] == "error"
    assert requests[0]["uuid"] != requests[1]["uuid"]
    assert requests[0]["properties"]["$session_id"] == issue["$session_id"]


@pytest.mark.parametrize(
    "fields",
    [
        {"posthog_session_id": "PRIVATE"},
        {"posthog_sequence": True},
        {"posthog_elapsed_ms": -1},
        {"posthog_qa_run_id": "PRIVATE"},
    ],
)
def test_untrusted_optional_provider_context_is_not_forwarded(tmp_path, fields):
    _, owner, sink = setup_owner(tmp_path)
    owner.record_app_opened()
    assert owner.shutdown(3)
    payload = capture_payload(replace(sink.events[0], **fields))
    assert "PRIVATE" not in json.dumps(payload)
    if "posthog_sequence" in fields:
        assert "event_sequence" not in payload["properties"]
    if "posthog_elapsed_ms" in fields:
        assert "session_elapsed_ms" not in payload["properties"]


def test_screen_companion_preserves_custom_event_and_closed_route(tmp_path):
    _, owner, sink = setup_owner(tmp_path)
    lifecycle = ApplicationLifecycle(owner, tmp_path)
    lifecycle.ready()
    lifecycle.tick()
    lifecycle.viewed("library")
    lifecycle.viewed("library")
    lifecycle.viewed("PRIVATE/video.mp4")
    lifecycle.close()
    assert owner.shutdown(3)
    views = [e for e in sink.events if e.action == "screen_viewed"]
    assert [e.dimensions["view"] for e in views] == ["forge", "library"]
    requests = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def opener(request, **kwargs):
        requests.append(json.loads(request.data))
        return Response()

    transport = PosthogEventSink(
        PosthogConfig(True, "phc_abcdefghijkl", "https://us.i.posthog.com"),
        opener=opener,
    )
    assert transport(views[1])
    assert [r["event"] for r in requests] == ["vf_app_feature_used", "$screen"]
    assert requests[1]["properties"]["$screen_name"] == "library"
    assert (
        requests[1]["properties"]["$session_id"]
        == requests[0]["properties"]["$session_id"]
    )
    assert requests[1]["uuid"] != requests[0]["uuid"]
