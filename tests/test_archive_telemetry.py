from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from tests.test_archive_relink import record
from tests.test_product_telemetry import _permitted_installation
from yt_downloader.archive_observations import operation, relink_dimensions, usage
from yt_downloader.archive_relink import preview_relink, verify_relink
from yt_downloader.cloud_funnel import load_or_create_installation_state
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox
from yt_downloader.telemetry_features import FEATURE_ACTIONS, OPERATION_FEATURES

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


@pytest.mark.parametrize("permission", ["denied", "allowed", "withdrawn"])
def test_all_archive_actions_obey_consent_and_exclude_private_content(
    tmp_path, permission
):
    installation = tmp_path / "installation.json"
    if permission == "denied":
        load_or_create_installation_state(installation)
    else:
        _permitted_installation(installation)
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.3",
        d1_recorder=lambda _: False,
        heycatch_recorder=lambda *a, **k: False,
    )
    if permission == "withdrawn":
        owner.set_enabled(False)
    key = str(uuid.uuid4())
    for feature in ("archive", "watch"):
        for action in sorted(FEATURE_ACTIONS[feature]):
            assert usage(owner, feature, action) == (permission == "allowed")
            assert usage(owner, feature, action) == (permission == "allowed")
    for feature in (
        "archive_relink_operation",
        "archive_location_operation",
        "archive_history_operation",
    ):
        for action in sorted(OPERATION_FEATURES[feature]):
            assert operation(owner, feature, action, key) == (permission == "allowed")
    owner.shutdown(2)
    events = _load_outbox(tmp_path / "events.json")
    assert bool(events) == (permission == "allowed")
    for feature in ("archive", "watch"):
        relevant = [event for event in events if event.feature == feature]
        assert len(relevant) == (
            len(FEATURE_ACTIONS[feature]) if permission == "allowed" else 0
        )
    # Session dedupe may acknowledge a previously observed action without using
    # the replacement fields; no new event or private value may be persisted.
    usage(owner, "watch", "searched", {"query": "private title token"})
    assert not operation(owner, "archive_relink_operation", "requested", "private-path")
    owner.shutdown(2)
    assert "private" not in json.dumps(
        [event.public_payload() for event in _load_outbox(tmp_path / "events.json")]
    )


@pytest.mark.parametrize("legacy_mismatch", [False, True])
def test_preview_observations_contain_only_counts_and_time(tmp_path, legacy_mismatch):
    new = tmp_path / "Secret Channel" / "Private Playlist"
    new.mkdir(parents=True)
    chosen = new / ("Private title.mp3" if legacy_mismatch else "Private title.mp4")
    chosen.write_bytes(b"synthetic")
    rows = [record(tmp_path / "old" / "Private title.mp4")]
    if legacy_mismatch:
        rows[0].pop("vodforge_output_path")
        rows[0]["vodforge_encoding_summary"]["output"].pop("Output file path")
    preview = verify_relink(preview_relink(rows, exact_files={0: str(chosen)}), rows)
    dimensions = relink_dimensions(preview)
    assert dimensions["identity_mismatch_count"] == ("1" if legacy_mismatch else "0")
    assert dimensions["verified_count"] == ("0" if legacy_mismatch else "1")
    assert dimensions["unresolved_count"] == ("1" if legacy_mismatch else "0")
    assert not any(
        value in json.dumps(dimensions)
        for value in ("Private", "Secret", str(tmp_path))
    )
    _permitted_installation(tmp_path / "installation.json")
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.3",
        d1_recorder=lambda _: False,
        heycatch_recorder=lambda *a, **k: False,
    )
    assert operation(
        owner, "archive_relink_operation", "verified", str(uuid.uuid4()), dimensions
    )
    owner.shutdown(2)
    persisted = _load_outbox(tmp_path / "events.json")[0].dimensions
    assert persisted["identity_mismatch_count"] == dimensions["identity_mismatch_count"]
    assert persisted["verified_count"] == dimensions["verified_count"]
    assert persisted["unresolved_count"] == dimensions["unresolved_count"]


def test_optional_observation_failure_cannot_replace_operation_outcome():
    def broken(*args, **kwargs):
        raise OSError("private unavailable telemetry destination")

    owner = SimpleNamespace(record_feature=broken, record_operation=broken)
    assert not usage(owner, "watch", "opened")
    assert not operation(
        owner, "archive_relink_operation", "committed", str(uuid.uuid4())
    )


@pytest.mark.parametrize("boundary", ["defer", "startup", "settlement"])
def test_history_failure_producers_observe_bounded_outcome_without_private_data(
    tmp_path, monkeypatch, boundary
):
    from types import MethodType

    from tests.test_archive_ui_owners import Variable
    from yt_downloader import history
    from yt_downloader.app import DownloaderApp
    from yt_downloader.archive_library_ui import ArchiveLibraryMixin

    events = []
    app = SimpleNamespace(
        history_path=tmp_path / "private-history.json",
        product_telemetry=SimpleNamespace(
            record_operation=lambda *a, **k: events.append((a, k))
        ),
        status_var=Variable(),
        _event_write_diagnostic=lambda *a: None,
        _append_log=lambda *a: None,
    )
    app._archive_usage = MethodType(ArchiveLibraryMixin._archive_usage, app)
    if boundary == "defer":

        def failed_stage(*a, **k):
            raise history.HistoryError("private-path and private-note")

        monkeypatch.setattr(
            "yt_downloader.archive_library_ui.stage_history_mutation", failed_stage
        )
        with pytest.raises(history.HistoryError):
            ArchiveLibraryMixin._archive_defer_history(
                app, "key", lambda: None, mutation={}
            )
        assert not app.__dict__.get("_archive_deferred_history")
    else:
        history.pending_history_path(app.history_path).write_text("{invalid")
        if boundary == "startup":
            DownloaderApp._load_download_history(app)
        else:
            assert not ArchiveLibraryMixin._archive_flush_history(app)
        assert app._history_recovery_blocked
    assert [args[1] for args, kwargs in events] == ["started", "failed"]
    assert events[-1][1]["failure_detail"].stage == "history"
    assert "private" not in json.dumps(events, default=lambda value: value.payload())


@pytest.mark.parametrize("consent", [False, True])
def test_hero_observations_use_actual_consented_outbox_without_content(
    tmp_path, monkeypatch, consent
):
    import json

    from tests.test_history_diagnostics import make_app, payloads
    from yt_downloader.watch_ui import WatchView

    holder = make_app(tmp_path, monkeypatch, consent=consent)
    watch = object.__new__(WatchView)
    watch._hero_seen_key = ""
    watch._mode = "playlists"
    watch._on_usage = holder._archive_usage
    played = []
    watch._on_play = played.append
    watch._observe_hero("PRIVATE title source path")
    watch._observe_hero("PRIVATE title source path")
    watch._play_hero(4)
    assert played == [4]
    events = payloads(holder)
    assert [event["action"] for event in events] == (
        ["hero_shown", "hero_played"] if consent else []
    )
    assert all(event["dimensions"] == {"watch_mode": "playlists"} for event in events)
    assert "PRIVATE" not in json.dumps(events)


@pytest.mark.parametrize("consent", [False, True])
def test_player_disclosure_producers_obey_consent_without_panel_content(
    tmp_path, monkeypatch, consent
):
    from tests.test_history_diagnostics import make_app, payloads
    from yt_downloader.media_player_ui import MediaPlayerWindow

    holder = make_app(tmp_path, monkeypatch, consent=consent)
    player = object.__new__(MediaPlayerWindow)
    player._closed = False
    player.popup = SimpleNamespace(winfo_ismapped=lambda: True)
    player._page_surface = SimpleNamespace(
        viewport=SimpleNamespace(winfo_rooty=lambda: 0, winfo_height=lambda: 100)
    )
    player._information_seen = set()
    player._on_feature = lambda action, **fields: (
        holder.product_telemetry.record_feature("player", action, **fields)
    )
    targets = ("chapters", "info", "source", "output", "notes", "moments")
    player._detail_targets = {
        f"PRIVATE owned panel {i}": target for i, target in enumerate(targets)
    }
    positions = {key: 200 for key in player._detail_targets}
    player._information_sections = {
        key: SimpleNamespace(
            winfo_rooty=lambda key=key: positions[key], winfo_height=lambda: 40
        )
        for key in player._detail_targets
    }
    player._observe_information()
    assert not payloads(holder)
    for key in player._detail_targets:
        positions[key] = 10
        player._observe_information()
        player._observe_information()
        positions[key] = 200
    events = payloads(holder)
    assert [event["action"] for event in events] == (
        ["detail_viewed"] * 6 if consent else []
    )
    assert [event["dimensions"]["detail_target"] for event in events] == (
        list(targets) if consent else []
    )
    assert all(event["feature"] == "player" for event in events)
    assert not holder.product_telemetry.record_feature(
        "player", "detail_viewed", dimensions={"detail_target": "PRIVATE raw path"}
    )
    assert "PRIVATE" not in json.dumps(events)


@pytest.mark.parametrize("consent", [False, True])
def test_continuous_catalog_scroll_is_bounded_and_content_free(
    tmp_path, monkeypatch, consent
):
    from tests.test_history_diagnostics import make_app, payloads
    from yt_downloader.watch_ui import WatchView

    holder = make_app(tmp_path, monkeypatch, consent=consent)
    watch = object.__new__(WatchView)
    watch._on_usage = holder._archive_usage
    watch._scene_window = ("PRIVATE catalog content",)
    for _ in range(100):
        watch._scene_catalog_scroll_used()
    events = payloads(holder)
    assert [event["action"] for event in events] == (
        ["catalog_scrolled"] if consent else []
    )
    assert all(event["dimensions"] == {} for event in events)


@pytest.mark.parametrize("consent", [False, True])
def test_library_continuous_scroll_reports_route_without_search_content(
    tmp_path, monkeypatch, consent
):
    from tests.test_history_diagnostics import make_app, payloads
    from yt_downloader.library_scene_ui import LibraryScene

    holder = make_app(tmp_path, monkeypatch, consent=consent)
    view = object.__new__(LibraryScene)
    view._on_usage = holder._archive_usage
    view._catalog_window = ("PRIVATE content",)
    view._route, view._query, view._sort = "all", "PRIVATE query", "recent"
    view._filter = view._group_kind = view._group_key = view._category = ""
    for _ in range(100):
        view._catalog_scroll_used()
    events = payloads(holder)
    assert [event["action"] for event in events] == (
        ["scene_scrolled"] if consent else []
    )
    assert all(event["dimensions"] == {"scene_route": "all"} for event in events)
