"""A local conversion that finished just before quit still reaches the Library.

On quit the app cancelled the conversion and stopped handling results, so a
video already saved but not yet handled stayed out of the Library (and its
completion was never reported).
"""

from __future__ import annotations

from tests.test_qt_scene_port import saved
from tests.test_qt_telemetry_coverage import bridge_fixture
from yt_downloader.local_audio_video import LocalAudioVideoResult


def test_finished_conversion_pending_at_quit_is_saved_to_history(tmp_path, monkeypatch):
    bridge, _telemetry = bridge_fixture(tmp_path, monkeypatch)
    folder = tmp_path / "Videos"
    folder.mkdir()
    video = folder / "Converted.mp4"
    video.write_bytes(b"saved by the conversion")
    metadata = saved(folder, "Converted", "MP4")
    metadata["vodforge_output_path"] = str(video)
    result = LocalAudioVideoResult(
        output_path=video, image_path=tmp_path / "cover.png", history_metadata=metadata
    )
    bridge._local.events.put(("done", result))  # finished, not yet handled
    history_path = bridge._runtime.history_path
    bridge.close(normal_quit=True)
    # Saved to disk, in the same history the Library reads at the next launch.
    assert str(video) in history_path.read_text(encoding="utf-8")
