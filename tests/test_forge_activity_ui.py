import os
import tkinter as tk

import pytest

from tests.test_archive_native import application as _application
from yt_downloader.forge_activity_ui import ForgeActivityPanel, friendly_phase
from yt_downloader.product_telemetry import ProductTelemetryOwner

application = _application
_ORIGINAL_RECORD = ProductTelemetryOwner.record


@pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native Tk"
)
@pytest.mark.usefixtures("production_telemetry_contract")
def test_real_worker_queue_failure_cancel_and_private_outbox(
    application, tmp_path, monkeypatch
):
    """Real worker/event pump/storage; controlled source boundary, no network/media claim."""
    import json
    import sys
    import time
    from collections import Counter
    from pathlib import Path
    from threading import Event
    from types import MethodType

    from tests.test_archive_native import pump
    from tests.test_presentation_diagnostics import real_owner
    from tests.test_state_authority import make_job
    from yt_downloader import app as module
    from yt_downloader.platform_services import capture_own_widget

    app = application
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    owner = real_owner(tmp_path / "telemetry")
    owner.record = MethodType(_ORIGINAL_RECORD, owner)
    app.product_telemetry = owner
    entered = [Event(), Event()]
    release = Event()
    jobs = [make_job(tmp_path, video_id=f"controlled-worker-{i}") for i in range(2)]
    for i, job in enumerate(jobs):
        job.preview_info = {
            "id": f"controlled-worker-{i}",
            "title": f"PRIVATE_FIXTURE_TITLE {i}",
            "webpage_url": job.url,
            "vodforge_output_type": "MP4",
        }

    def expand(job, *_args, control_check, **_kwargs):
        index = jobs.index(job)
        app.events.put(("status", "Video 1 of 1 — downloading"))
        app.events.put(("progress", 37))
        entered[index].set()
        deadline = time.monotonic() + 15
        while not release.is_set() or index == 1:
            control_check()
            if time.monotonic() > deadline:
                raise RuntimeError("Controlled source wait expired")
            time.sleep(0.01)
        raise RuntimeError("PRIVATE_SOURCE_CAUSE requested format is not available")

    monkeypatch.setattr(module, "load_yt_dlp", lambda: object())
    monkeypatch.setattr(app, "_expand_download_source", expand)
    # Queue previews are a distinct network owner; this test exercises admission,
    # worker failure/cancel and rendering, never external preview extraction.
    monkeypatch.setattr(app, "_enqueue_queue_preview", lambda *_a: None)
    alerts = []
    # Actual native alert appearance/dismissal has separate UI evidence. Keep
    # this producer/storage case unattended at the existing dialog boundary.
    monkeypatch.setattr(
        module.messagebox, "showerror", lambda *args, **kwargs: alerts.append(args)
    )

    def until(predicate):
        deadline = time.monotonic() + 8
        while not predicate():
            assert time.monotonic() < deadline
            pump(app, 0.02)

    def capture(label):
        for size in ("1100x600", "1440x900"):
            app.geometry(size)
            pump(app, 0.12)
            friendly = app.forge_activity.friendly
            if friendly.winfo_ismapped():
                assert friendly.winfo_height() >= app.forge_activity.winfo_height() - 2
                content = friendly.get("1.0", "end-1c")
                original_view = friendly.yview()[0]
                friendly.see("end")
                pump(app, 0.03)
                assert friendly.dlineinfo("end-1c") is not None
                assert friendly.get("1.0", "end-1c") == content
                friendly.yview_moveto(original_view)
                pump(app, 0.03)
            if sys.platform != "darwin":
                continue  # This capture adapter is Mac-only; functional checks are shared.
            bitmap = capture_own_widget(app)
            assert bitmap is not None
            bitmap.save(output / f"forge-worker-{label}-{size}.png")

    try:
        app._select_focus_view("forge")
        assert app._start_or_queue_download_job(jobs[0], clear_source=False)
        until(lambda: entered[0].is_set() and app.progress_var.get() == 37)
        assert app.active_job is jobs[0] and app.worker.is_alive()
        assert app._start_or_queue_download_job(jobs[1], clear_source=False)
        assert [job.run_id for job in app.run_recovery.store.load_queued_jobs()] == [
            jobs[1].run_id
        ]
        assert app.download_button.cget("text") == "Queue run"
        capture("active-queued")
        release.set()
        until(lambda: entered[1].is_set() and app.active_job is jobs[1])
        assert app.focus_engine_var.get() == "Runs process one at a time"
        assert jobs[0].terminal_status == "Failed"
        app._focus_select_run_record(
            next(
                row
                for row in app._focus_run_records()
                if row.get("run_id") == jobs[0].run_id
            )
        )
        capture("failed-with-next-active")
        app._focus_select_run_record(
            next(
                row
                for row in app._focus_run_records()
                if row.get("run_id") == jobs[1].run_id
            )
        )
        app.cancel_button.invoke()
        until(lambda: app.active_job is None and jobs[1].terminal_status == "Stopped")
        assert not app.pending_jobs and not app.run_recovery.store.load_queued_jobs()
        stored = {
            job.run_id: job.terminal_status
            for job in app.run_recovery.store.load_terminal_jobs()
        }
        assert (
            stored[jobs[0].run_id] == "Failed" and stored[jobs[1].run_id] == "Stopped"
        )
        capture("stopped")
        assert owner.shutdown(2)
        payload = (tmp_path / "telemetry/events.json").read_text()
        counts = Counter(row["event_name"] for row in json.loads(payload)["events"])
        assert counts["run_started"] == 2 and counts["run_queued"] == 1
        assert counts["run_failed"] == 1 and counts["run_stopped"] == 1
        for private in ("PRIVATE_", "youtube.com", str(tmp_path)):
            assert private not in payload
        assert len(alerts) == 1 and "selected quality is unavailable" in alerts[0][1]
        assert "PRIVATE_" not in alerts[0][1]
        outbox = tmp_path / "telemetry/events.json"
        owner.set_enabled(False)
        for view in ("activity", "library", "forge"):
            app._select_focus_view(view)
            pump(app, 0.08)
        assert not outbox.exists() or json.loads(outbox.read_text())["events"] == []
        (output / "forge-worker-outcome.json").write_text(
            json.dumps(
                {
                    "scope": "Real worker/admission/UI/storage/local fake-transport outbox; controlled source stage and failure, no download or D1 delivery claim",
                    "events": dict(counts),
                    "terminal_states": stored,
                    "private_values_absent": True,
                    "queue_empty": True,
                    "off_navigation_leaves_empty_local_outbox": True,
                    "mac_native_captures": sys.platform == "darwin",
                },
                indent=2,
            )
        )
    finally:
        release.set()
        if app.worker is not None and app.worker.is_alive():
            app._cancel()
            until(lambda: not app.worker or not app.worker.is_alive())
        owner.shutdown(2)


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
        assert panel.friendly.winfo_height() >= panel.winfo_height() - 2
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
    import yt_downloader.app as app_module
    from tests.test_metadata_helpers import _worker_test_app, _worker_test_job

    monkeypatch.setattr(app_module, "load_yt_dlp", lambda: object())
    monkeypatch.setattr(app_module, "write_diagnostic", lambda _message: None)
    app = _worker_test_app()
    cause = "the MP4 output does not match its export plan: the measured audio bitrate (unavailable kbps) does not match 160 kbps"
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
        message = app_module.format_ytdlp_user_error(RuntimeError(cause))
        panel.observe(job.run_id, "Failed", message)
        panel.technical.request(raw)
        panel.show(job.run_id, raw)
        root.update()
        friendly = panel.friendly.get("1.0", "end-1c")
        assert cause not in friendly
        assert message in friendly
        assert "same settings" in friendly
        panel.set_technical(True)
        root.update()
        assert panel.technical.winfo_ismapped()
        assert cause in panel.technical.get("1.0", "end-1c")
        panel.set_technical(False)
        root.update()
        assert panel.friendly.get("1.0", "end-1c") == friendly
    finally:
        root.destroy()


@pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native Tk"
)
@pytest.mark.parametrize("retirement", ["released", "hidden", "callback_replaced"])
def test_activity_mode_drag_cannot_survive_its_input_owner(retirement):
    from yt_downloader.forge_activity_ui import ActivityModeSlider

    root = tk.Tk()
    root.geometry("260x200+320+180")
    original, successor = [], []
    control = ActivityModeSlider(root, original.append)
    control.pack()
    root.update()
    try:
        control.event_generate("<ButtonPress-1>", x=15, y=13)
        root.update()
        assert original == [False]
        if retirement == "released":
            control.event_generate("<ButtonRelease-1>", x=15, y=13)
        elif retirement == "hidden":
            control.pack_forget()
            root.update()
            control.pack()
            root.update()
        else:
            control.command = successor.append
        control.event_generate("<B1-Motion>", x=15, y=103)
        root.update()
        assert original == [False] and successor == [], (
            "A retired gesture changed the disclosure"
        )
        control.event_generate("<ButtonPress-1>", x=15, y=103)
        control.event_generate("<ButtonRelease-1>", x=15, y=103)
        root.update()
        assert (successor if retirement == "callback_replaced" else original)[
            -1
        ] is True
        control.focus_force()
        root.update()
        control.event_generate("<Up>")
        root.update()
        assert (successor if retirement == "callback_replaced" else original)[
            -1
        ] is False
    finally:
        root.destroy()


@pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native Tk"
)
@pytest.mark.usefixtures("production_telemetry_contract")
def test_legal_media_failure_retry_completion_and_skip_identity(
    application, tmp_path, monkeypatch
):
    import hashlib
    import json
    import subprocess
    import sys
    import time
    from dataclasses import replace
    from pathlib import Path

    from quality_harness.fault_server import CANCELLATION_ROUTE, FixtureHTTPServer
    from quality_harness.fixtures import find_ffmpeg, find_ffprobe, generate_fixtures

    from tests.test_archive_native import pump
    from tests.test_state_authority import make_job
    from yt_downloader import app as module
    from yt_downloader.platform_services import capture_own_widget

    app = application
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    fixtures = out / "legal-fixtures"
    manifest = generate_fixtures(fixtures)
    (out / "fixture-manifest.json").write_text(json.dumps(manifest, indent=2))
    alerts = []
    monkeypatch.setattr(
        module.messagebox, "showerror", lambda *a, **k: alerts.append(a)
    )

    # Native alerts were observed separately; do not let a modal block this worker/storage journey.
    def until(predicate, seconds=45):
        deadline = time.monotonic() + seconds
        while not predicate():
            assert time.monotonic() < deadline, (app.status_var.get(), alerts)
            pump(app, 0.02)

    def capture(name):
        pump(app, 0.15)
        if sys.platform != "darwin":
            return  # Functional journey is shared; this capture adapter is Mac-only.
        bitmap = capture_own_widget(app)
        assert bitmap is not None
        bitmap.save(out / (name + ".png"))

    app._select_focus_view("forge")
    app.geometry("1440x900+0+30")
    app.output_var.set(str(out / "outputs"))
    app.output_type_var.set("MP4")
    app.use_nvenc_var.set(False)
    initial = replace(make_job(out / "outputs"), url="", urls=[])
    with FixtureHTTPServer(fixtures, slow_chunk_delay=0.08) as server:
        try:
            server.state.retry_failures_remaining = 100
            failed = replace(initial, url=server.url("/fault/retry/page"))
            assert app._start_or_queue_download_job(failed, clear_source=False)
            until(lambda: app.active_job is None and failed.terminal_status == "Failed")
            capture("actual-failed")
            # Read the existing durable owner before Retry supersedes this attempt.
            failed_records = {
                j.run_id: j.terminal_status
                for j in app.run_recovery.store.load_terminal_jobs()
            }
            assert failed_records[failed.run_id] == "Failed"
            assert alerts
            app._focus_select_run_record(
                next(
                    r
                    for r in app._focus_run_records()
                    if r.get("run_id") == failed.run_id
                )
            )
            pump(app, 0.12)
            assert app.focus_preview_start_button.winfo_ismapped()
            assert app.focus_preview_start_button.cget("text") == "Retry Download"
            server.state.retry_failures_remaining = 0
            app.focus_preview_start_button.invoke()
            retried = app.active_job
            assert retried is not None and retried.run_id != failed.run_id
            assert retried.origin_run_id == failed.run_id
            until(
                lambda: (
                    app.active_job is None and retried.terminal_status == "Completed"
                ),
                120,
            )
            capture("actual-retry-completed")
            files = list((out / "outputs").rglob("*.mp4"))
            assert files
            probes = []
            for path in files:
                data = json.loads(
                    subprocess.check_output(
                        [
                            find_ffprobe(),
                            "-v",
                            "error",
                            "-show_format",
                            "-show_streams",
                            "-of",
                            "json",
                            str(path),
                        ],
                        text=True,
                    )
                )
                assert float(data["format"]["duration"]) > 0
                assert any(s["codec_type"] == "video" for s in data["streams"])
                subprocess.run(
                    [find_ffmpeg(), "-v", "error", "-i", str(path), "-f", "null", "-"],
                    check=True,
                    capture_output=True,
                    timeout=40,
                )
                probes.append(
                    {
                        "path": str(path),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "ffprobe": data,
                        "full_decode": True,
                    }
                )
            skip = replace(
                initial,
                url=server.url(CANCELLATION_ROUTE),
                run_id="legal-skip-" + str(time.time_ns()),
                output_dir=out / "skip-outputs",
            )
            assert app._start_or_queue_download_job(skip, clear_source=False)
            until(
                lambda: (
                    skip.terminal_status is not None
                    or any(
                        "/slow/" in k and v > 32768
                        for k, v in server.state.snapshot()["bytes_sent"].items()
                    )
                )
            )
            assert skip.terminal_status is None, (
                skip.terminal_status,
                skip.activity_lines,
            )
            assert app.active_job is skip and app.worker.is_alive()
            app.skip_video_button.invoke()
            until(
                lambda: (
                    app.active_job is None
                    and any(
                        j.terminal_status == "Skipped"
                        and j.execution_run_id == skip.run_id
                        for j in app.run_recovery.store.load_terminal_jobs()
                    )
                )
            )
            capture("actual-skipped")
            assert not list((out / "skip-outputs").rglob("*.mp4"))
            terminal = {
                j.run_id: j.terminal_status
                for j in app.run_recovery.store.load_terminal_jobs()
            }
            # Generic extractor items own terminal records; the submitted execution
            # is their execution_run_id, not necessarily their item run_id.
            skipped_items = [
                j
                for j in app.run_recovery.store.load_terminal_jobs()
                if j.execution_run_id == skip.run_id
            ]
            assert (
                len(skipped_items) == 1
                and skipped_items[0].terminal_status == "Skipped"
            )
            assert not app.worker or not app.worker.is_alive()
            assert not app.run_recovery.store.load_queued_jobs()
            assert not list((out / "outputs").rglob("*.part"))
            assert not list((out / "skip-outputs").rglob("*.part"))
            for root in (out / "outputs", out / "skip-outputs"):
                assert not any(".vfstage" in path.parts for path in root.rglob("*"))
            (out / "actual-forge-outcome.json").write_text(
                json.dumps(
                    {
                        "scope": "Actual yt-dlp/FFmpeg worker, maintained generated local HTTP media; native widget invocation; isolated data, no D1 or physical input claim",
                        "mac_native_captures": sys.platform == "darwin",
                        "failed": failed.run_id,
                        "failed_records_before_retry": failed_records,
                        "retry": retried.run_id,
                        "retry_origin": retried.origin_run_id,
                        "retry_status": retried.terminal_status,
                        "skipped_execution": skip.run_id,
                        "skipped_item": skipped_items[0].run_id,
                        "worker_stopped": True,
                        "durable_queue_empty": True,
                        "terminal_records": terminal,
                        "media": probes,
                        "server": server.state.snapshot(),
                        "history": app.download_history,
                    },
                    indent=2,
                )
            )
        finally:
            if app.worker and app.worker.is_alive():
                app._cancel()
                until(lambda: not app.worker or not app.worker.is_alive(), 30)
