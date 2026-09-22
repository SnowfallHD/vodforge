"""Controlled actual backend/UI/app producers; no native or audibility claim."""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from tests.test_libvlc_backend import make_backend
from yt_downloader.app import DownloaderApp
from yt_downloader.media_player_ui import MediaPlayerWindow

CONTROL_CASES = (
    "control_fit",
    "control_fill",
    "control_captions",
    "control_fullscreen",
    "control_caption_safety",
    "control_caption_restore",
)
CONTROL_EXPECTATIONS = {
    "control_fit": ("fit", "user"),
    "control_fill": ("fill", "user"),
    "control_captions": ("captions", "user"),
    "control_fullscreen": ("fullscreen", "user"),
    "control_caption_safety": ("fit", "caption_safety"),
    "control_caption_restore": ("fill", "caption_restore"),
}

CASES = (
    "immediate_mute",
    "delayed_mute",
    "pending_at_close",
    "accepted_mismatch",
    "readback_unavailable",
    "readback_exception",
    "setter_exception",
    "superseded_request",
    "output_recreated",
    "provider_event",
    "state_read",
    "command_flood",
    *CONTROL_CASES,
)


def run_case(
    directory: Path, telemetry, case: str, *, close_before_settle: bool = False
) -> dict:
    """Exercise original producers with a controlled provider and isolated media."""
    directory.mkdir(parents=True, exist_ok=True)
    media = directory / "PRIVATE synthetic title.m4a"
    media.write_bytes(b"controlled provider; not playable media")
    backend, module = make_backend()
    backend.load(media, duration=12)
    backend.play()
    state = {
        "ready": case not in {"delayed_mute", "pending_at_close", "superseded_request"}
    }
    module.player.audio_get_volume = lambda: module.player.volume

    def setter(value):
        if case == "setter_exception":
            raise RuntimeError("PRIVATE original provider text and path")
        if not state["ready"]:
            return -1
        if case != "accepted_mismatch":
            module.player.volume = value
        return 0

    module.player.audio_set_volume = setter
    if case == "readback_unavailable":
        module.player.audio_get_volume = lambda: -1
    elif case == "readback_exception":

        def readback():
            raise ValueError("PRIVATE readback source title")

        module.player.audio_get_volume = readback
    operation = str(uuid.uuid4())
    app = SimpleNamespace(
        product_telemetry=telemetry, _archive_playback_origins={operation: "watch"}
    )
    emitted = []

    def record(action, diagnostic=None, dimensions=None):
        emitted.append(action)
        DownloaderApp._record_playback_operation(
            app, operation, action, diagnostic, dimensions=dimensions
        )

    player = object.__new__(MediaPlayerWindow)
    player.playback = backend
    player._last_snapshot = None
    player._operation_play_observed = False
    player._on_feature = lambda *_args, **_fields: None
    player._on_operation = record
    for name in ("time_var", "status_var"):
        setattr(player, name, SimpleNamespace(set=lambda value: None))
    value = {"volume": 0}
    player.volume_var = SimpleNamespace(get=lambda: value["volume"])
    player.volume_label_var = SimpleNamespace(set=lambda value: None)
    player.play_button = SimpleNamespace(configure=lambda **fields: None)
    player._update_timeline_value = lambda snapshot: None
    player._refresh_previews = lambda snapshot: None
    player._drain_previews = lambda: None
    player._closed = False
    player._shortcut_bindings = []
    player._autoplay_after_id = None
    player._poll_after_id = None
    player._stage_render_after_id = None
    player._surface_owner = None
    player._on_closed = None
    player.popup = SimpleNamespace(destroy=lambda: None)
    player.previews = SimpleNamespace(shutdown=lambda: None)
    record("requested")
    record("ready")
    player._present_snapshot(backend.snapshot)
    if case in CONTROL_CASES:
        player._presentation_mode = "embedded"
        player._video_fill = case in {"control_fit", "control_caption_safety"}
        player._display_signature = None
        player._surface_owner = SimpleNamespace(
            stage=SimpleNamespace(winfo_width=lambda: 1380, winfo_height=lambda: 418)
        )

        def reject(*args, **kwargs):
            raise OSError(5, "PRIVATE title /private/media-path and caption label")

        module.player.video_set_crop_geometry = reject
        module.player.video_get_spu_description = lambda: [
            (92, b"PRIVATE caption label")
        ]
        module.player.video_set_spu = reject
        if case == "control_caption_restore":
            track = {"value": 92}
            player._captions_active = True
            player._caption_restore_fill = True
            module.player.video_get_spu = lambda: track["value"]

            def select_caption(value):
                track["value"] = value
                return 0

            module.player.video_set_spu = select_caption
        player._open_presentation = reject
        action = {
            "control_fit": "fit",
            "control_fill": "fill",
            "control_captions": "caption:92",
            "control_fullscreen": "fullscreen",
            "control_caption_safety": "caption:92",
            "control_caption_restore": "caption:-1",
        }[case]
        player._overlay_actions = deque([(action, None)])
        player._drain_overlay_actions()
        assert emitted.count("control_failed") == 1
        assert "PRIVATE" not in player._control_notice
        assert player._video_fill == (case in {"control_fit", "control_caption_safety"})
        player._surface_owner = None
    player._schedule_volume("0")

    def poll(*, settled=True):
        if settled:
            player._volume_stable_since = time.monotonic() - 1
        player._present_snapshot(backend.snapshot)

    if case == "superseded_request":
        value["volume"] = 37
        player._schedule_volume("37")
        state["ready"] = True
        poll()
    else:
        poll()
        if case == "command_flood":
            for step in range(200):
                value["volume"] = step % 101
                player._schedule_volume(str(value["volume"]))
                poll()
            state["ready"] = False
            value["volume"] = 37
            player._schedule_volume("37")
            if not close_before_settle:
                poll()
        elif case == "delayed_mute":
            state["ready"] = True
            poll()
        elif case == "output_recreated":
            module.player.volume = 80
            state["ready"] = False
            backend._playback_started(None)
            poll()
            state["ready"] = True
            poll()
        elif case == "provider_event":
            backend._playback_failed(None)
            module.player.state = module.State.Ended
            poll()
        elif case == "state_read":

            def get_state():
                raise OSError(5, "PRIVATE provider path")

            module.player.get_state = get_state
            poll()
    before = len(emitted)
    for _ in range(0 if close_before_settle else 100):
        poll()
    assert len(emitted) == before, "Identical polling flooded operation telemetry"
    snapshot = backend.snapshot
    observation = (
        asdict(snapshot.volume_observation) if snapshot.volume_observation else None
    )
    player.close()
    player.close()
    assert module.player.release_calls == 1
    return {
        "case": case,
        "actions": emitted,
        "volume": observation,
        "failure_boundary": snapshot.failure_boundary,
        "failure_detail": snapshot.failure_detail.payload()
        if snapshot.failure_detail
        else None,
        "physical_input": False,
        "audibility_observed": False,
    }
