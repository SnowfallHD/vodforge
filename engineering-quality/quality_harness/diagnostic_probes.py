"""Local synthetic producers for diagnostic HTTP/D1 evidence."""

from __future__ import annotations

import time
from pathlib import Path
from types import MethodType
from unittest.mock import patch

from PIL import Image

from yt_downloader import app as app_module
from yt_downloader.analytics_startup import AnalyticsStartup
from yt_downloader.app import DownloaderApp
from yt_downloader.engagement_ui import EngagementUI
from yt_downloader.library_annotations import LibraryAnnotation
from yt_downloader.presentation_diagnostics import PresentationObservations
from yt_downloader.product_telemetry import ProductTelemetryOwner

_ORIGINAL_RECORD = ProductTelemetryOwner.record
PRESENTATION_CASES = (
    "cold_ready",
    "unavailable_artwork",
    "missing_control",
    "missing_artwork",
    "invalid_default_mode",
    "intentional_empty_search",
    "resize_pending",
    "hidden_return",
    "hidden_control_fault",
    "late_fault_after_sampling",
)
RELINK_CASES = (
    "relink_legacy_format",
    "relink_canonical_format",
    "relink_companion_identity",
    "relink_unmapped",
    "relink_matching",
)
OPENING_CASES = (
    "opening_dependency",
    "opening_initialization",
    "opening_readiness",
    "opening_load",
)
LIBRARY_CASES = (
    "accepted_queue",
    "refused_queue",
    "refused_launch",
    "duplicate_focus",
    "accepted_annotation_retained",
    "accepted_preview_callback_fault",
    "removal_refused",
    "removal_cancelled",
    "refused_queue_permission",
    "refused_queue_disk_full",
    "refused_launch_disk_full",
    "retry_queue_annotation_permission",
    "retry_launch_annotation_disk_full",
    "supersession_queue_annotation_permission",
    "supersession_launch_annotation_disk_full",
    "retry_queue_refused_permission",
    "retry_launch_refused_disk_full",
)


def pump(app, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.update()
        time.sleep(0.005)


def presentation_case(directory: Path, telemetry, case: str):
    from scripts.focus_ui_preview import isolated_preview_services

    directory.mkdir(parents=True, exist_ok=True)
    file = directory / "PRIVATE-thumbnail.jpeg"
    if case == "unavailable_artwork":
        file.write_bytes(b"PRIVATE invalid bitmap")
    else:
        Image.new("RGB", (320, 180), "#4455cc").save(file)
    rows = [
        {
            "id": f"PRIVATE-video-{index}",
            "title": f"PRIVATE title {index}",
            "channel": "PRIVATE channel",
            "playlist_id": "PRIVATE playlist",
            "vodforge_output_dir": str(directory / f"PRIVATE-{index}"),
            "vodforge_output_path": str(directory / f"PRIVATE-{index}" / "media.mp4"),
            "vodforge_output_type": "MP4",
            "description": "PRIVATE source description",
        }
        for index in range(2)
    ]
    app = None
    errors = []
    result = {"case": case, "root_destroyed": False}
    with (
        isolated_preview_services(),
        patch.object(AnalyticsStartup, "start", lambda _self: None),
        patch.object(EngagementUI, "start", lambda _self: None),
    ):
        try:
            app = DownloaderApp()
            app.report_callback_exception = lambda *error: errors.append(
                error[0].__name__
            )
            app.product_telemetry = telemetry
            telemetry.record = MethodType(_ORIGINAL_RECORD, telemetry)
            for view, surface in (
                (app.focus_watch, "watch"),
                (app.video_tree, "library"),
            ):
                view._presentation.observations = PresentationObservations(
                    telemetry, surface
                )
                view._artwork_path = lambda _record: file
            app.geometry("1100x600")
            app.deiconify()
            watch = app.focus_watch
            if case == "resize_pending":

                def delayed(_record):
                    time.sleep(0.09)
                    return file

                watch._artwork_path = delayed
            if case == "intentional_empty_search":
                for row in rows:
                    # Save actual annotations under canonical saved-media ownership.
                    from yt_downloader.history import history_annotation_owner

                    app.library_annotations.replace(
                        history_annotation_owner(row),
                        LibraryAnnotation(category="PRIVATE category"),
                    )
            if case == "invalid_default_mode":
                app._library_projection_owner().record_preview(
                    "PRIVATE-preview",
                    [
                        {
                            "id": "PRIVATE-preview",
                            "vodforge_user_category": "PRIVATE category",
                        }
                    ],
                )
            app.download_history = rows
            app._reconcile_library_projection()
            app._select_focus_view("watch")
            if case == "resize_pending":
                pump(app, 0.04)
                app.geometry("1440x900")
                pump(app, 0.04)
                app.geometry("1180x740")
            pump(app, 0.8)
            # Readiness is an owner outcome, not a fixed decode-duration guess.
            deadline = time.monotonic() + 5
            while (
                watch._presentation.observations.bound is not None
                and time.monotonic() < deadline
            ):
                pump(app, 0.025)
            assert watch._presentation.observations.bound is None, (
                "Initial presentation did not settle"
            )
            if case in {
                "missing_control",
                "missing_artwork",
                "late_fault_after_sampling",
            }:
                if case == "late_fault_after_sampling":
                    for index in range(24):
                        app.geometry("1120x600" if index % 2 else "1100x600")
                        pump(app, 0.05)
                        observations = watch._presentation.observations
                        deadline = time.monotonic() + 3
                        while (
                            observations.bound is not None
                            and (
                                observations.admitted
                                or observations.budget.ordinary < 12
                            )
                            and time.monotonic() < deadline
                        ):
                            pump(app, 0.025)
                        if observations.budget.ordinary == 12:
                            break
                    assert observations.budget.ordinary == 12, vars(observations.budget)
                    assert not observations.admitted, (
                        "Healthy operation has not settled"
                    )
                    result["actual_resize_transitions"] = index + 1
                role = "artwork" if case == "missing_artwork" else "control"
                item = watch.canvas.find_withtag("presentation-" + role)[0]
                name = watch.canvas.itemcget(item, "image")

                def trace(label):
                    if case != "late_fault_after_sampling":
                        return
                    probe = watch._presentation
                    actual, pending = watch._presentation_snapshot()
                    result.setdefault("observation_trace", []).append(
                        {
                            "boundary": label,
                            "after_pending": probe.after is not None,
                            "due_in_ms": round(
                                (probe.deadline - time.monotonic()) * 1000, 3
                            ),
                            "budget": dict(vars(probe.observations.budget)),
                            "last_missing": probe.observations.last.get(
                                "missing_image_role"
                            ),
                            "actual_missing": actual["missing_image_role"],
                            "artwork_pending": pending,
                            "bound": probe.observations.bound is not None,
                            "admitted": probe.observations.admitted,
                        }
                    )

                trace("before_delete")
                watch.canvas.tk.call("image", "delete", name)
                trace("after_delete")
                if case == "missing_artwork":
                    # Observe the hard-deleted Tcl artwork in a retained scene.
                    app._select_focus_view("library")
                    pump(app, 0.2)
                    # Controlled repair uses the real size-cache retirement owner;
                    # this probe does not claim automatic hard-deletion recovery.
                    watch._artwork_resize((0, 0))
                    app._select_focus_view("watch")
                elif case == "late_fault_after_sampling":
                    # A sustained real hidden scene reaches the ordinary Unmap
                    # producer after healthy sampling is exhausted.
                    app._select_focus_view("library")
                    pump(app, 0.2)
                    trace("sustained_hidden_fault")
                    assert watch._presentation.observations.budget.incidents >= 1
                    assert (
                        watch._presentation_snapshot()[0]["missing_image_role"]
                        == "control"
                    )
                    # Normal entry renders fresh controls automatically. This is
                    # a separate operation: do not claim same-operation recovery.
                    app._select_focus_view("watch")
                else:
                    watch._presentation_change("artwork")
                    pump(app, 0.05)
                    watch._queue_render()
                pump(app, 0.6)
                trace("after_repair")
                if case == "late_fault_after_sampling":
                    assert (
                        watch._presentation_snapshot()[0]["missing_image_role"]
                        == "none"
                    )
            elif case == "invalid_default_mode":
                # Inject the former automatic-mode defect, preserving its true
                # origin rather than representing this as a user navigation.
                watch._mode = "collections"
                watch._mode_origin = "default"
                watch._presentation_change("data")
                watch._queue_render()
                pump(app, 0.3)
            elif case == "intentional_empty_search":
                watch.search.set("PRIVATE unmatched query")
                pump(app, 0.3)
            elif case in {"hidden_return", "hidden_control_fault"}:
                if case == "hidden_control_fault":
                    item = watch.canvas.find_withtag("presentation-control")[0]
                    watch.canvas.tk.call(
                        "image", "delete", watch.canvas.itemcget(item, "image")
                    )
                # Real view switching emits Unmap, which observes the retained scene.
                # No direct diagnostic-hook dispatch occurs in this scenario.
                app._select_focus_view("library")
                pump(app, 0.2)
                rows[0]["description"] = "PRIVATE hidden refresh"
                app._reconcile_library_projection()
                pump(app, 0.2)
                app._select_focus_view("watch")
                pump(app, 0.5)
            result["surface_event_attempts"] = {
                "watch": watch._presentation.observations.attempts,
                "library": app.video_tree._presentation.observations.attempts,
            }
            assert all(
                count <= 64 for count in result["surface_event_attempts"].values()
            )
            result["callback_errors"] = errors
            assert not errors, errors
        finally:
            if app is not None:
                app._request_application_close()
                deadline = time.monotonic() + 3
                while (
                    app.tk.call("info", "commands", ".") and time.monotonic() < deadline
                ):
                    app.update()
                    time.sleep(0.01)
                result["root_destroyed"] = not bool(
                    app.tk.call("info", "commands", ".")
                )
                if not result["root_destroyed"]:
                    app.destroy()
                assert result["root_destroyed"]
    return result


def retry_case(directory: Path, telemetry, case: str):
    import pytest

    from tests.test_retry_annotation_lineage import (
        ORIGINAL,
        disk_projection,
        retry_app,
        submit_retry,
        writer_fault,
    )
    from yt_downloader import library_annotations, run_state

    directory.mkdir(parents=True, exist_ok=True)
    monkeypatch = pytest.MonkeyPatch()
    busy = "_queue_" in case
    try:
        app, previous, sibling = retry_app(directory, monkeypatch, busy=busy)
        app.product_telemetry = telemetry
        refused = "_refused_" in case
        code = 13 if case.endswith("permission") else 28
        before_notes = app.library_annotations.path.read_bytes()
        before_state = app.run_recovery.store.path.read_bytes()
        monkeypatch.setattr(
            run_state if refused else library_annotations,
            "write_private_bytes",
            writer_fault(code),
        )
        submit_retry(
            app, previous, "automatic" if case.startswith("supersession") else "retry"
        )
        if refused:
            assert app.run_recovery.store.path.read_bytes() == before_state
            assert app.library_annotations.path.read_bytes() == before_notes
            assert previous in app._terminal_jobs
            return {
                "case": case,
                "admission_refused": True,
                "previous_owner_preserved": True,
            }
        replacement, ledger, row = disk_projection(app, busy=busy)
        assert replacement.run_id != previous.run_id
        assert row["vodforge_user_note"] == ORIGINAL.note
        assert tuple(row["vodforge_user_tags"]) == ORIGINAL.tags
        assert row["vodforge_user_category"] == ORIGINAL.category
        assert ledger.annotation_for("run:" + sibling.run_id).note == "Sibling"
        assert app.library_annotations.path.read_bytes() == before_notes
        return {
            "case": case,
            "durable_replacement_admitted": True,
            "reloaded_annotations_accessible": True,
            "sibling_preserved": True,
        }
    finally:
        monkeypatch.undo()


def library_case(directory: Path, telemetry, case: str):
    if case.startswith(("retry_", "supersession_")):
        return retry_case(directory, telemetry, case)
    # Source-owned admission/persistence, with controlled UI/worker sinks. Native
    # Library menu integration is a separate maintained two-size test.
    import pytest

    from tests.test_preview_admission import prepared_app, submit
    from yt_downloader.run_state import RunRecoveryOwner

    directory.mkdir(parents=True, exist_ok=True)
    monkeypatch = pytest.MonkeyPatch()
    try:
        app = prepared_app(
            directory / "app",
            monkeypatch,
            busy=not case.startswith("refused_launch"),
            hold_worker=False,
            duplicate=case == "duplicate_focus",
        )
        app.product_telemetry = telemetry
        app._record_queue_event = MethodType(DownloaderApp._record_queue_event, app)
        app.run_recovery = RunRecoveryOwner(directory / "run-state.json")
        before = app.library_projection.snapshot

        def refuse(*_a, **_k):
            raise app_module.RunStateError("PRIVATE state write refusal")

        if case in {
            "refused_queue_permission",
            "refused_queue_disk_full",
            "refused_launch_disk_full",
        }:
            from yt_downloader import run_state

            def storage_refusal(*_a, **_k):
                raise OSError(
                    13 if case.endswith("permission") else 28,
                    "PRIVATE cause /Users/private.mp4",
                )

            monkeypatch.setattr(run_state, "write_private_bytes", storage_refusal)
        elif case == "refused_queue":
            monkeypatch.setattr(app.run_recovery, "queue_changed", refuse)
        elif case == "refused_launch":
            monkeypatch.setattr(app.run_recovery, "begin", refuse)
        elif case == "accepted_annotation_retained":

            def annotation_refusal(*_a):
                raise app_module.LibraryAnnotationsError("PRIVATE annotation location")

            monkeypatch.setattr(app.library_annotations, "transfer", annotation_refusal)
        elif case == "accepted_preview_callback_fault":

            def scheduling_fault(*_a):
                raise RuntimeError("PRIVATE scheduling content")

            app._enqueue_queue_preview = scheduling_fault
        if case in {"removal_refused", "removal_cancelled"}:
            app.pending_jobs = [app.built_job]
            app.run_recovery.queue_changed(app.pending_jobs)
            app._reconcile_library_projection()
            target = next(
                row
                for row in app.metadata_items
                if row.get("vodforge_projection_owner") == "run:" + app.built_job.run_id
            )
            before = app.library_projection.snapshot
            monkeypatch.setattr(
                app_module.messagebox,
                "askyesno",
                lambda *_a: case != "removal_cancelled",
            )
            if case == "removal_refused":
                monkeypatch.setattr(app.run_recovery, "queue_changed", refuse)
            app._remove_selected_library_item(dict(target))
        else:
            try:
                submit(app, "library")
            except RuntimeError:
                if case != "accepted_preview_callback_fault":
                    raise
        preserved = app.library_projection.snapshot == before
        if case.startswith("refused") or case in {
            "duplicate_focus",
            "removal_refused",
            "removal_cancelled",
        }:
            assert preserved
        durable = app.run_recovery.store.load_queued_jobs()
        admitted = any(job.run_id == app.built_job.run_id for job in durable)
        if case.startswith("accepted"):
            assert admitted
        return {
            "case": case,
            "projection_preserved": preserved,
            "durable_queue_contains_subject": admitted,
        }
    finally:
        monkeypatch.undo()


def opening_case(directory: Path, telemetry, case: str):
    from types import SimpleNamespace

    from tests.test_playback_opening_failures import opening_app

    directory.mkdir(parents=True, exist_ok=True)
    app, operation = opening_app(directory, telemetry)
    boundary = case.removeprefix("opening_")
    released = []

    class Backend:
        def load(self, *_a, **_k):
            raise PermissionError(13, "PRIVATE saved file /Users/private/story.mp4")

        def shutdown(self):
            released.append(True)

    app.playback_engine = (
        None
        if boundary == "dependency"
        else SimpleNamespace(
            failed=boundary == "initialization",
            ready=boundary == "load",
            create_backend=lambda: Backend(),
        )
    )
    app._open_library_player_when_ready(
        {"id": "PRIVATE saved subject", "vodforge_output_type": "MP4"},
        directory / "PRIVATE.mp4",
        ffmpeg="unused",
        launch_generation=1,
        deadline=0,
        operation=operation,
    )
    assert len(app.attention) == 1
    assert app._archive_opening_operation is None
    assert app._archive_playback_origins == {}
    assert released == ([True] if boundary == "load" else [])
    return {
        "case": case,
        "same_window_attention_selected": True,
        "opening_owner_retired": True,
        "origin_retired": True,
        "controlled_backend_released": bool(released),
    }


def relink_case(directory: Path, telemetry, case: str):
    import json
    from tkinter import ttk

    from scripts.focus_ui_preview import isolated_preview_services
    from tests.test_archive_native import native_descendants, wait_for
    from yt_downloader.archive_paths import ArchivePath
    from yt_downloader.history import (
        load_history,
        sanitize_history_record,
        save_history,
    )
    from yt_downloader.media_player import resolve_library_media_path

    directory.mkdir(parents=True, exist_ok=True)
    old = directory / "PRIVATE-old"
    chosen = (
        directory
        / "PRIVATE-selected"
        / (
            "PRIVATE.mp3"
            if case in {"relink_legacy_format", "relink_canonical_format"}
            else "PRIVATE.mp4"
        )
    )
    chosen.parent.mkdir()
    chosen.write_bytes(b"synthetic local file; no decoding claim")
    info = {"id": "PRIVATE-id", "title": "PRIVATE title", "vodforge_output_type": "MP4"}
    if case in {
        "relink_canonical_format",
        "relink_companion_identity",
        "relink_unmapped",
    }:
        info["vodforge_output_path"] = str(old / "PRIVATE.mp4")
    if case == "relink_companion_identity":
        (chosen.parent / "metadata.json").write_text(
            json.dumps({"id": "PRIVATE-other-id"})
        )
    rows = [sanitize_history_record(info, old)]
    result = {"case": case, "root_destroyed": False}
    errors, observed = [], []
    app = None
    with (
        isolated_preview_services(),
        patch.object(AnalyticsStartup, "start", lambda _self: None),
        patch.object(EngagementUI, "start", lambda _self: None),
    ):
        try:
            app = DownloaderApp()
            app.report_callback_exception = lambda *error: errors.append(
                error[0].__name__
            )
            app.product_telemetry = telemetry
            telemetry.record = MethodType(_ORIGINAL_RECORD, telemetry)
            original_observe = app._archive_observe

            def observe(feature, action, key, **dims):
                original_observe(feature, action, key, **dims)
                observed.append((feature, action))

            app._archive_observe = observe
            app.geometry("1100x600")
            app.deiconify()
            save_history(app.history_path, rows)
            app.download_history = load_history(app.history_path)
            app._reconcile_library_projection()
            app._select_focus_view("library")
            app.video_tree.selection_set("0")
            app._display_selected_metadata(0)
            wait_for(app, lambda: not app._archive_worker.busy)
            before = app.history_path.read_bytes()
            if case == "relink_unmapped":
                app._archive_begin_relink(
                    ArchivePath.parse(str(directory / "PRIVATE-unrelated")),
                    (0,),
                    destination=str(chosen.parent),
                )
            else:
                app._archive_begin_relink(None, (0,), exact=str(chosen))
            wait_for(app, lambda: ("archive_relink_operation", "verified") in observed)
            buttons = [
                w
                for w in native_descendants(app._archive_overlay)
                if isinstance(w, ttk.Button)
            ]
            apply = next(
                w for w in buttons if str(w.cget("text")).startswith("Update ")
            )
            back = next(w for w in buttons if str(w.cget("text")) == "Back to archive")
            accepted = case == "relink_matching"
            assert apply.instate(["disabled"]) == (not accepted)
            if accepted:
                apply.invoke()
                wait_for(app, lambda: not app._archive_commit_active)
                assert (
                    resolve_library_media_path(load_history(app.history_path)[0])
                    == chosen
                )
                assert ("archive_relink_operation", "committed") in observed
            else:
                apply.invoke()
                assert app.history_path.read_bytes() == before
                back.invoke()
                assert ("archive_relink_operation", "committed") not in observed
            assert app._archive_overlay is None
            result.update(
                accepted=accepted, history_outcome_verified=True, callback_errors=errors
            )
            assert not errors
        finally:
            if app is not None:
                app._request_application_close()
                deadline = time.monotonic() + 3
                while (
                    app.tk.call("info", "commands", ".") and time.monotonic() < deadline
                ):
                    app.update()
                    time.sleep(0.01)
                result["root_destroyed"] = not bool(
                    app.tk.call("info", "commands", ".")
                )
                if not result["root_destroyed"]:
                    app.destroy()
                assert result["root_destroyed"]
    return result
