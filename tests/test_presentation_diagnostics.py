"""Budget, ordering, original-consent and optional-sink boundaries."""

from __future__ import annotations

import json
import uuid

import pytest

from tests.test_product_telemetry import _permitted_installation
from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.presentation_diagnostics import PresentationObservations
from yt_downloader.product_telemetry import BoundProductOperation, ProductTelemetryOwner
from yt_downloader.telemetry_features import validate_dimensions

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


class Sink:
    def __init__(self, fail=False):
        self.events = []
        self.fail = fail

    def bind_operation(self, feature, *, operation_key):
        def record(action, dimensions):
            validate_dimensions(dimensions)
            self.events.append((operation_key, action, dict(dimensions)))
            if self.fail:
                raise OSError("PRIVATE failed sink")
            return True

        return BoundProductOperation(lambda: True, record)


def facts(role="none", artwork="ready"):
    return {
        "presentation_surface": "watch",
        "presentation_trigger": "entry",
        "presentation_sampling": "full",
        "mode_eligible_bucket": "6_20",
        "query_state": "inactive",
        "filter_state": "inactive",
        "presentation_mode": "playlists",
        "mode_origin": "default",
        "presentation_population": "saved_media",
        "eligible_bucket": "6_20",
        "matching_bucket": "6_20",
        "rendered_bucket": "2_5",
        "artwork_expected_bucket": "2_5",
        "artwork_displayed_bucket": "2_5",
        "artwork_unavailable_bucket": "0",
        "missing_image_bucket": "0" if role == "none" else "1",
        "missing_image_role": role,
        "artwork_state": artwork,
        "presentation_visibility": "visible",
        "presentation_scene": "current",
        "presentation_audit": "under_2ms",
        "lag_bucket": "under_50ms",
        "lag_measurement": "ui_pump_delay",
        "artwork_batch": "current",
    }


@pytest.mark.parametrize("fail", [False, True])
def test_sampling_preserves_later_fault_recovery_and_terminal_capacity(fail):
    sink = Sink(fail)
    owner = PresentationObservations(sink, "watch")
    for _ in range(200):
        owner.begin("resize")
        owner.observe(facts(artwork="pending"), pending=True)
        owner.observe(facts(), pending=False)
    ordinary = list(sink.events)
    assert any(
        action == "sampled" and row["presentation_sampling"] == "healthy_sampled"
        for _, action, row in ordinary
    )
    for _ in range(50):
        owner.begin("data")
        owner.observe(facts("control"), pending=True)
        owner.observe(facts(), pending=False)
    assert len(sink.events) <= 64
    assert owner.attempts == len(sink.events)
    later = sink.events[len(ordinary) :]
    assert sum(action == "fault" for _, action, _ in later) == 4
    assert sum(action == "recovered" for _, action, _ in later) == 4
    assert sum(action == "settled" for _, action, _ in later) == 4
    assert any(row["presentation_sampling"] == "exhausted" for _, _, row in later)
    for key in {event[0] for event in sink.events}:
        events = [event for event in sink.events if event[0] == key]
        assert events[-1][1] in {"settled", "superseded", "retired"}
        assert (
            sum(action in {"observed", "fault", "recovered"} for _, action, _ in events)
            <= 4
        )
    assert "PRIVATE" not in json.dumps(sink.events)


def test_pending_is_not_failure_and_supersession_is_ordered():
    sink = Sink()
    owner = PresentationObservations(sink, "library")
    owner.begin("entry")
    owner.observe(facts(artwork="pending"), pending=True)
    for _ in range(100):
        owner.observe(facts(artwork="pending"), pending=True)
    owner.begin("resize")
    owner.observe(facts(artwork="unavailable"), pending=False)
    assert [action for _, action, _ in sink.events] == [
        "observed",
        "superseded",
        "observed",
        "settled",
    ]
    assert sink.events[1][2]["presentation_replacement"] == "resize"
    assert sink.events[0][0] != sink.events[2][0]


def real_owner(tmp_path, permitted=True):
    installation = tmp_path / "installation.json"
    if permitted:
        _permitted_installation(installation)
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.1.9",
        d1_recorder=lambda _event: False,
        heycatch_recorder=lambda *_a, **_k: False,
    )
    return owner


def test_original_consent_binding_cannot_adopt_regrant(tmp_path):
    owner = real_owner(tmp_path)
    bound = owner.bind_operation(
        "presentation_operation", operation_key=str(uuid.uuid4())
    )
    assert bound is not None
    assert bound.record(
        "observed",
        {
            **facts(),
            "presentation_surface": "watch",
            "presentation_trigger": "entry",
            "presentation_sampling": "full",
        },
    )
    assert owner.shutdown(2)
    AnalyticsConsentOwner(tmp_path).choose(False)
    owner.set_enabled(False)
    AnalyticsConsentOwner(tmp_path).choose(True)
    owner.set_enabled(True)
    assert not bound.permitted()
    assert not bound.record("fault", facts("control"))
    assert not (tmp_path / "events.json").exists()
    fresh = owner.bind_operation(
        "presentation_operation", operation_key=str(uuid.uuid4())
    )
    assert fresh is not None
    assert fresh.record("observed", facts())
    assert owner.shutdown(2)
    persisted = json.loads((tmp_path / "events.json").read_text())
    assert "PRIVATE" not in json.dumps(persisted)


def test_denied_initial_binding_and_blocked_outbox_remain_fail_closed(
    tmp_path, monkeypatch
):
    from yt_downloader import product_telemetry

    owner = real_owner(tmp_path, permitted=False)
    assert (
        owner.bind_operation("presentation_operation", operation_key=str(uuid.uuid4()))
        is None
    )
    assert not (tmp_path / "events.json").exists()
    _permitted_installation(tmp_path / "installation.json")

    def denied(*_args):
        raise OSError("PRIVATE outbox path")

    monkeypatch.setattr(product_telemetry, "_save_outbox", denied)
    probe = PresentationObservations(owner, "watch")
    for _ in range(200):
        probe.begin("resize")
        probe.observe(facts(), pending=False)
    assert probe.attempts <= 64
    assert not (tmp_path / "events.json").exists()
    assert owner.shutdown(2)


@pytest.mark.parametrize(
    "key,value",
    [
        ("missing_image_role", "PRIVATE pyimage123"),
        ("presentation_trigger", "PRIVATE search words"),
        ("eligible_bucket", "999"),
        ("presentation_scene", "PRIVATE widget.path"),
    ],
)
def test_presentation_vocabulary_rejects_private_or_unknown_values(key, value):
    with pytest.raises(ValueError):
        validate_dimensions({key: value})


def test_recreated_surfaces_share_one_session_budget():
    sink = Sink()
    for _ in range(100):
        observer = PresentationObservations(sink, "watch")
        observer.begin("entry")
        observer.observe(facts(), pending=False)
    assert len(sink.events) <= 25
    successor = PresentationObservations(sink, "watch")
    successor.begin("data")
    successor.observe(facts("artwork"), pending=True)
    successor.observe(facts(), pending=False)
    assert any(action == "fault" for _, action, _ in sink.events)
    assert successor.attempts == len(sink.events)


def test_canvas_snapshot_includes_owned_horizontal_rail_images():
    from types import SimpleNamespace
    from unittest.mock import Mock

    from yt_downloader.presentation_diagnostics import canvas_snapshot

    interpreter = Mock()
    interpreter.call.return_value = ("rail-image",)
    interpreter.splitlist.side_effect = lambda value: value
    outer = SimpleNamespace(tk=interpreter, find_all=lambda: ())
    inner = SimpleNamespace(
        tk=interpreter,
        find_all=lambda: (1,),
        type=lambda _item: "image",
        itemcget=lambda _item, _option: "rail-image",
        gettags=lambda _item: ("presentation-artwork",),
    )
    view = SimpleNamespace(
        canvas=outer,
        _presentation_extra_canvases=(inner,),
        _artwork_wanted={"owner": {}},
        _artwork_unavailable=set(),
        _artwork_images={"owner": "rail-image"},
        winfo_ismapped=lambda: True,
    )
    dimensions, pending = canvas_snapshot(view, {})
    assert dimensions["artwork_state"] == "ready" and not pending
    assert dimensions["artwork_displayed_bucket"] == "1"
    interpreter.call.return_value = ()
    dimensions, _ = canvas_snapshot(view, {})
    assert dimensions["missing_image_role"] == "artwork"
    assert dimensions["missing_image_bucket"] == "1"


@pytest.mark.parametrize("replace_operation", [False, True])
def test_pending_presentation_audit_preserves_its_due_time_without_borrowing_owner(
    monkeypatch, replace_operation
):
    """Independent queued-clock fixture; checks emitted lag, not timer internals."""
    from types import SimpleNamespace

    from yt_downloader import presentation_diagnostics as module

    clock = [0.0]
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    class Widget:
        def __init__(self):
            self.pending = {}
            self.serial = 0

        def after(self, delay, callback):
            self.serial += 1
            token = str(self.serial)
            self.pending[token] = (clock[0] + delay / 1000, callback)
            return token

        def after_cancel(self, token):
            self.pending.pop(token, None)

        def _presentation_snapshot(self):
            return facts(), False

        def drain_due(self):
            for token, (due, callback) in list(self.pending.items()):
                if due <= clock[0] and token in self.pending:
                    self.pending.pop(token)
                    callback()

    widget, sink = Widget(), Sink()
    probe = module.PresentationProbe(widget, sink, "library")
    probe.change("resize")
    probe.schedule()
    # Native tracking/work can deliver geometry changes while audit timers wait.
    for instant in (0.1, 0.2, 0.3):
        clock[0] = instant
        probe.change("resize")
        probe.schedule()
    if replace_operation:
        probe.change("data")
        probe.schedule()
    clock[0] = 0.32
    widget.drain_due()
    observed = [row for _, action, row in sink.events if action == "observed"]
    assert len(observed) == 1
    assert observed[0]["lag_bucket"] == (
        "under_50ms" if replace_operation else "250_999ms"
    )
    assert observed[0]["presentation_trigger"] == (
        "data" if replace_operation else "resize"
    )
    assert not widget.pending
    assert sink.events[-1][1] == "settled"
