"""Control observers may never act on a successor after their worker returns."""

import threading
from types import SimpleNamespace

import pytest
from quality_harness import pipeline


@pytest.mark.parametrize("blocked_predicate", [False, True])
def test_completed_worker_retires_control_observer(
    tmp_path, monkeypatch, blocked_predicate
):
    import yt_downloader.app as production

    entered, release, terminated = (threading.Event() for _ in range(3))

    def predicate(_events, _app):
        entered.set()
        if blocked_predicate:
            release.wait(4)
        return release.is_set()

    def worker(*_args, **_kwargs):
        assert entered.wait(2)
        return "completed"

    app = SimpleNamespace(
        _progress_hook=lambda _data: None,
        _download_worker_single=worker,
        _find_ffprobe=lambda: "/fixture/ffprobe",
        _find_ffmpeg=lambda: None,
        cancel_requested=False,
        skip_video_requested=False,
    )
    monkeypatch.setattr(pipeline, "make_headless_app", lambda _events: app)
    monkeypatch.setattr(
        production, "DIAGNOSTICS_LOG_PATH", tmp_path / "diagnostics.log"
    )
    monkeypatch.setattr(production, "write_diagnostic", lambda *_: None)
    monkeypatch.setattr(
        production, "terminate_all_active_child_processes", lambda **_: terminated.set()
    )
    monkeypatch.setattr(
        pipeline,
        "ResourceSampler",
        lambda *_: SimpleNamespace(start=lambda: SimpleNamespace(stop=dict)),
    )
    try:
        result = pipeline.HeadlessPipelineRunner(tmp_path).run_job(
            case_id="observer-scope",
            url="http://127.0.0.1/fixture",
            output_type="MP4",
            validate_destination=False,
            cancel_when=predicate,
            cancel_timeout_seconds=3,
        )
        if blocked_predicate:
            assert result["control_observer_stopped"] is False
            assert result["control_observer_errors"]
            assert result["error"].startswith("Harness control observer failed:")
        else:
            assert result["control_observer_stopped"] is True
            assert not result["control_observer_errors"]
        # A late predicate result must not invoke global child termination.
        release.set()
        observers = [
            t
            for t in threading.enumerate()
            if t.name == "quality-cancel-observer-scope"
        ]
        for thread in observers:
            thread.join(2)
        assert not app.cancel_requested, "Retired observer changed completed job state"
        assert not terminated.is_set(), (
            "Retired observer could terminate successor children"
        )
        if not blocked_predicate:
            assert not observers, "Ordinary polling observer survived run completion"
    finally:
        release.set()


@pytest.mark.parametrize("predicate_error", [False, True])
def test_control_dispatch_is_observed_during_worker_or_reports_observer_failure(
    tmp_path, monkeypatch, predicate_error
):
    import yt_downloader.app as production

    dispatched = threading.Event()

    def predicate(_events, _app):
        if predicate_error:
            raise ValueError("observer fault")
        return True

    def worker(*_args, **_kwargs):
        if not predicate_error:
            assert dispatched.wait(2), "Supported active cancellation was lost"
        return "finished"

    app = SimpleNamespace(
        _progress_hook=lambda _data: None,
        _download_worker_single=worker,
        _find_ffprobe=lambda: "/fixture/ffprobe",
        _find_ffmpeg=lambda: None,
        cancel_requested=False,
        skip_video_requested=False,
    )
    monkeypatch.setattr(pipeline, "make_headless_app", lambda _: app)
    monkeypatch.setattr(
        production, "DIAGNOSTICS_LOG_PATH", tmp_path / "diagnostics.log"
    )
    monkeypatch.setattr(production, "write_diagnostic", lambda *_: None)
    monkeypatch.setattr(
        production, "terminate_all_active_child_processes", lambda **_: dispatched.set()
    )
    monkeypatch.setattr(
        pipeline,
        "ResourceSampler",
        lambda *_: SimpleNamespace(start=lambda: SimpleNamespace(stop=dict)),
    )
    result = pipeline.HeadlessPipelineRunner(tmp_path).run_job(
        case_id="active-control",
        url="http://127.0.0.1/fixture",
        output_type="MP4",
        validate_destination=False,
        cancel_when=predicate,
    )
    assert result["control_observer_stopped"]
    phases = [item["phase"] for item in result["control_trace"]]
    assert phases[0] == "worker_started" and phases.count("worker_finished") == 1
    assert {item["run_id"] for item in result["control_trace"]} == {
        result["job"]["run_id"]
    }
    if predicate_error:
        assert not dispatched.is_set() and not app.cancel_requested
        assert result["control_observer_errors"] == ["ValueError: observer fault"]
        assert result["error"].startswith("Harness control observer failed:")
    else:
        assert (
            phases.index("control_requested")
            < phases.index("control_dispatched")
            < phases.index("worker_finished")
        )
        assert app.cancel_requested and dispatched.is_set()
        assert not result["error"]


@pytest.mark.parametrize("errors,stopped", [(["observer failed"], True), ([], False)])
def test_observer_failure_cannot_be_hidden_by_successful_product_endpoint(
    errors, stopped
):
    from quality_harness.scenarios import _scenario_from_pipeline

    result = {
        "job": {"output_dir": "/isolated/case/output"},
        "control_observer_errors": errors,
        "control_observer_stopped": stopped,
        "cancel_requested": True,
        "error": "Download cancelled",
    }
    scenario = _scenario_from_pipeline(
        scenario_id="reliability.cancel_during_slow_download",
        category="reliability",
        result=result,
        passed=True,
        evidence=["Final cancellation looks clean"],
    )
    assert scenario["status"] == "error"
    assert "observer" in scenario["evidence"][-1]
