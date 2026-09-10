import os
import tkinter as tk

import pytest

from yt_downloader.forge_activity_ui import ForgeActivityPanel, friendly_phase


def test_phases_use_worker_status_not_arbitrary_logs():
    assert (
        friendly_phase("Video 1 of 1 — analyzing source formats")
        == "Getting video information"
    )
    assert (
        friendly_phase("Video 2 of 11 — downloading")
        == "Video 2 of 11 · Downloading media"
    )
    assert friendly_phase("Video 1 of 1 — transcoding") == "Converting media"
    assert friendly_phase("Video 1 of 1 — validating output") == "Checking the output"
    assert friendly_phase("selected format 270+251") is None
    assert friendly_phase("some filename.mp4") is None
    assert friendly_phase("Download finished; finalizing output…") is None
    assert friendly_phase("Completed").startswith("[success]")
    assert friendly_phase("Failed").startswith("ERROR:")


@pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native Tk"
)
def test_live_disclosure_geometry_identity_and_lossless_log():
    root = tk.Tk()
    root.geometry("620x260")
    panel = ForgeActivityPanel(root)
    panel.pack(fill="both", expand=True)
    try:
        panel.show("one", "")
        panel.observe("one", "Video 1 of 1 — analyzing source formats")
        panel.observe("one", "Video 1 of 1 — downloading")
        panel.observe("one", "Downloading file.mp4 — 100/s")
        assert len(panel._runs["one"]) == 2
        panel.observe("two", "Video 1 of 1 — transcoding")
        assert "Converting" not in panel.friendly.get("1.0", "end")
        raw = "\n".join(f"Real technical line {i}" for i in range(40))
        panel.technical.request(raw)
        panel.show("one", raw)
        assert panel.technical.get("1.0", "end-1c") == raw
        panel.toggle_details()
        for size in ("620x260", "400x160"):
            root.geometry(size)
            root.update()
            assert (
                panel.toggle.winfo_rooty() + panel.toggle.winfo_height()
                <= root.winfo_rooty() + root.winfo_height()
            )
            assert panel.technical.winfo_height() > 20
            assert not panel.friendly.winfo_ismapped()
            assert panel.technical.winfo_height() >= panel.winfo_height() - 2
        panel.toggle.focus_force()
        panel.toggle.apply_theme()
        assert not any(
            panel.toggle.type(item) == "rectangle" for item in panel.toggle.find_all()
        )
        root.update()
        panel.toggle.event_generate("<Up>")
        root.update()
        assert panel.friendly.winfo_ismapped()
        assert not panel.technical.winfo_ismapped()
        panel.toggle.event_generate("<Down>")
        root.update()
        assert panel.technical.winfo_ismapped()
        panel.toggle.event_generate("<Button-1>", x=15, y=13)
        root.update()
        assert panel.friendly.winfo_ismapped()
        panel.toggle.event_generate("<B1-Motion>", x=15, y=103)
        root.update()
        assert panel.technical.winfo_ismapped()
        assert panel.technical.image_names()
        from yt_downloader.app import DownloaderApp

        panel.technical._vodforge_user_scroll_locked = True
        panel.technical.yview_moveto(0)
        before = panel.technical.yview()
        panel.show("one", raw)
        assert panel.technical.yview() == before
        DownloaderApp._append_log_widget(panel.technical, "One more real event")
        assert panel.technical.yview()[0] == before[0]
        assert "One more real event" in panel.technical.get("1.0", "end")
        panel.show("one", "12:34:56 [warning] A real warning")
        assert "warning was reported" in panel.friendly.get("1.0", "end")
        panel.observe("one", "Failed")
        assert "Download failed" in panel.friendly.get("1.0", "end")
        assert "Download complete" not in panel.friendly.get("1.0", "end")
        panel.toggle_details()
        root.update()
        assert not panel.technical.winfo_ismapped()
        panel.show("older", raw)
        assert "saved activity" in panel.friendly.get("1.0", "end")
    finally:
        root.destroy()


@pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native Tk"
)
def test_worker_failure_cause_is_visible_only_in_technical(monkeypatch, tmp_path):
    from test_metadata_helpers import _worker_test_app, _worker_test_job

    import yt_downloader.app as app_module

    monkeypatch.setattr(app_module, "load_yt_dlp", lambda: object())
    monkeypatch.setattr(app_module, "write_diagnostic", lambda _message: None)
    app = _worker_test_app()
    cause = "the measured audio bitrate (unavailable kbps) does not match 160 kbps"
    app._expand_download_source = lambda *_a, **_kw: (_ for _ in ()).throw(
        RuntimeError(cause)
    )
    job = _worker_test_job(tmp_path)
    app._download_worker_single(job)
    raw = "\n".join(
        payload["line"] for kind, payload in app.events.queue if kind == "job_log"
    )
    assert cause in raw
    root = tk.Tk()
    root.geometry("620x260")
    panel = ForgeActivityPanel(root)
    panel.pack(fill="both", expand=True)
    try:
        panel.observe(job.run_id, "Failed")
        panel.technical.request(raw)
        panel.show(job.run_id, raw)
        root.update()
        friendly = panel.friendly.get("1.0", "end-1c")
        assert cause not in friendly
        assert "Download failed. Open Technical details for the cause." in friendly
        panel.set_technical(True)
        root.update()
        assert panel.technical.winfo_ismapped()
        assert cause in panel.technical.get("1.0", "end-1c")
        panel.set_technical(False)
        root.update()
        assert panel.friendly.get("1.0", "end-1c") == friendly
    finally:
        root.destroy()
