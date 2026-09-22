from __future__ import annotations

import queue
import tkinter as tk
from types import SimpleNamespace

import pytest

import yt_downloader.app as app_module
from tests.test_library_media_recovery import _job, _missing_record
from yt_downloader.app import DownloaderApp
from yt_downloader.history import RETRY_JOB_METADATA_KEY
from yt_downloader.library_media_recovery import LibraryMediaRecoveryOwner
from yt_downloader.models import ExportMode, ManualExportSettings, OutputType
from yt_downloader.run_identity import OUTPUT_PROFILE_KEY


@pytest.mark.parametrize(
    ("label", "migrated"),
    [
        ("Auto CBR", True),
        ("Auto CBR (Recommended)", True),
        ("Strict Compliance", True),
        ("CTV (legacy fixed bitrate)", True),
        ("CTV", False),
        ("Custom", False),
        ("Manual Override", False),
        ("Everyday", False),
        ("Streaming", False),
        ("Editing", False),
        ("Sharing", False),
        ("Unknown", False),
        ("", False),
    ],
)
def test_incomplete_profile_only_recognized_legacy_presets_start_everyday(
    tmp_path, label, migrated
):
    original = _job(tmp_path)
    original.output_type = OutputType.MP4
    row = _missing_record(original)
    row.pop(RETRY_JOB_METADATA_KEY)
    row[OUTPUT_PROFILE_KEY] = f"MP4 • 1080p Full HD • {label}"
    plan = LibraryMediaRecoveryOwner().plan(row)
    assert plan.kind == "legacy" and plan.job is None
    assert getattr(plan, "preset_migrated", False) is migrated


def _draft_app(tmp_path, monkeypatch):
    # Tcl-only variables exercise actual traces without opening a native window.
    interpreter = tk.Tcl()
    app = DownloaderApp.__new__(DownloaderApp)
    app.tk = interpreter.tk
    app.library_media_recovery = LibraryMediaRecoveryOwner()
    app.batch_urls = []
    values = {
        "url": "",
        "url_list_file": "No URL list loaded",
        "output": str(tmp_path / "default"),
        "export_mode": ExportMode.AUTO_CBR.value,
        "export_mode_choice": "CTV",
        "export_mode_description": "",
        "focus_output_display": "",
        "output_type": "MP4",
        "quality": "1080p Full HD",
        "tags": "",
        "status": "",
        "manual_audio_codec": "AAC",
        "focus_command_hint": "",
        "focus_active_profile": "",
        "focus_active_detail": "Ready",
        "focus_transfer": "",
    }
    for name, value in values.items():
        setattr(app, name + "_var", tk.StringVar(interpreter, value))
    for name in (
        "use_nvenc",
        "embed_thumbnail",
        "write_thumbnail",
        "embed_metadata",
        "write_info_json",
    ):
        setattr(app, name + "_var", tk.BooleanVar(interpreter, False))
    app._refresh_manual_settings_visibility = lambda: None
    app._focus_shows_next_run_defaults = lambda: True
    app._select_focus_view = lambda name: None
    app._selected_cookie_source = lambda: app_module.CookieSource.PUBLIC
    app._cookie_inputs = lambda: (False, None, None)
    app._manual_export_settings = lambda: ManualExportSettings(video_bitrate_kbps=12000)
    app.export_mode_var.trace_add(
        "write", lambda *_: app._sync_focus_settings_summary()
    )
    app.url_var.trace_add("write", lambda *_: app._sync_focus_destination())
    app.export_mode_choice_var.trace_add(
        "write", lambda *_: app._on_export_mode_choice_changed()
    )
    monkeypatch.setattr(app_module, "validate_output_directory_access", lambda _: None)
    monkeypatch.setattr(app_module, "write_diagnostic", lambda _: None)
    return app


@pytest.mark.parametrize("end", ["send", "source_change", "clear"])
def test_legacy_draft_visible_choice_submission_and_lifetime_match_without_saving_defaults(
    tmp_path, monkeypatch, end
):
    app = _draft_app(tmp_path, monkeypatch)
    original = _job(tmp_path)
    original.output_type = OutputType.MP4
    row = _missing_record(original)
    row.pop(RETRY_JOB_METADATA_KEY)
    row[OUTPUT_PROFILE_KEY] = "MP4 • 1080p Full HD • Auto CBR"
    plan = app.library_media_recovery.plan(row)
    chosen = tmp_path / "chosen"
    app._pick_output_directory = lambda: str(chosen)
    app._open_missing_media_in_forge(row, plan)
    assert app.export_mode_choice_var.get() == "Everyday"
    assert app.focus_active_profile_var.get().endswith("Everyday")
    assert app.focus_command_hint_var.get().endswith("Everyday")
    assert app._submission_export_mode() is ExportMode.EVERYDAY
    assert "Everyday" in app._focus_profile_text(OutputType.MP4)
    assert "Output mode   Everyday" in app._focus_next_run_summary(OutputType.MP4)
    assert app.export_mode_var.get() == ExportMode.AUTO_CBR.value
    assert app.output_var.get() == str(tmp_path / "default")
    source = app.url_var.get()
    job = app._build_download_job_from_current_settings(
        [source],
        output_type=OutputType.MP4,
        single_video_only=False,
        batch_mode=True,
    )
    assert job.export_mode is ExportMode.EVERYDAY
    assert job.output_dir == chosen and job.single_video_only and not job.batch_mode

    # A deliberate edit applies to this reviewed draft, not the user's default.
    app.export_mode_choice_var.set("Custom")
    edited = app._build_download_job_from_current_settings(
        [source],
        output_type=OutputType.MP4,
        single_video_only=False,
        batch_mode=False,
    )
    assert edited.export_mode is ExportMode.MANUAL_OVERRIDE
    assert edited.manual_settings.video_bitrate_kbps == 12000
    assert app.export_mode_var.get() == ExportMode.AUTO_CBR.value

    if end == "send":
        app._reset_source_input_after_send()
    else:
        app.url_var.set(
            "" if end == "clear" else "https://www.youtube.com/watch?v=other"
        )
    assert app.export_mode_choice_var.get() == "CTV"
    assert app.focus_active_profile_var.get().endswith("CTV")
    assert app.focus_command_hint_var.get().endswith("CTV")
    assert app._submission_export_mode() is ExportMode.AUTO_CBR
    assert app._submission_output_text() == str(tmp_path / "default")
    app.url_var.set(source)
    assert app.export_mode_choice_var.get() == "CTV"
    assert not app.library_media_recovery.is_draft_for(source)


@pytest.mark.parametrize("output", list(OutputType))
@pytest.mark.parametrize("playlist", [False, True])
def test_actual_recovery_expansion_uses_one_saved_item_without_playlist_provider_work(
    tmp_path, monkeypatch, output, playlist
):
    job = _job(tmp_path)
    job.output_type = output
    if playlist:
        job.url += "&list=PL_saved"
        job.urls = [job.url]
    row = _missing_record(job)
    if playlist:
        row.update(
            playlist_id="PL_saved", playlist_title="Saved playlist", playlist_index=7
        )
    plan = LibraryMediaRecoveryOwner().plan(row)
    recovered = plan.job
    recovered.recovery_reason = "missing_media"
    monkeypatch.setattr(app_module, "write_diagnostic", lambda _: None)
    monkeypatch.setattr(app_module, "log_options", lambda *args: None)
    app = SimpleNamespace(
        events=queue.Queue(),
        _emit_job_log=lambda *args: None,
        _find_deno=lambda: None,
    )
    provider_calls = []

    class UnexpectedPlaylistLookup(Exception):
        pass

    def provider_started(_):
        provider_calls.append("playlist lookup")
        raise UnexpectedPlaylistLookup

    result = None
    try:
        result = DownloaderApp._expand_download_source(
            app,
            recovered,
            None,
            SimpleNamespace(begin_primary=provider_started),
            control_check=lambda: None,
            blocking_step_cancelled=lambda: False,
        )
    except UnexpectedPlaylistLookup:
        pass
    assert provider_calls == [], "Selected recovery must not reread its saved playlist"
    assert result is not None
    assert len(result.entries) == 1
    assert result.entries[0]["webpage_url"] == recovered.url
    assert result.playlist_info.get("playlist_title") == (
        "Saved playlist" if playlist else None
    )
    if playlist:
        assert result.entries[0]["playlist_index"] == 7
    assert (
        result.cookie_source_loaded is False
    )  # Item preflight still loads credentials.
    assert app.events.empty()


@pytest.mark.parametrize(
    "invalid",
    ["ordinary", "different_video", "different_playlist", "batch", "multiple_urls"],
)
def test_recovery_fast_path_cannot_bypass_ordinary_or_mismatched_playlist_lookup(
    tmp_path, monkeypatch, invalid
):
    job = _job(tmp_path)
    job.url += "&list=PL_saved"
    job.urls = [job.url]
    job.preview_info = {
        "id": "missing",
        "playlist_id": "PL_saved",
        "playlist_title": "Saved",
    }
    job.recovery_reason = "missing_media"
    if invalid == "ordinary":
        job.recovery_reason = None
    elif invalid == "different_video":
        job.preview_info["id"] = "other"
    elif invalid == "different_playlist":
        job.preview_info["playlist_id"] = "PL_other"
    elif invalid == "batch":
        job.batch_mode = True
    else:
        job.urls.append("https://www.youtube.com/watch?v=other")
    monkeypatch.setattr(app_module, "write_diagnostic", lambda _: None)
    monkeypatch.setattr(app_module, "log_options", lambda *args: None)
    app = SimpleNamespace(
        events=queue.Queue(),
        _emit_job_log=lambda *args: None,
        _find_deno=lambda: None,
    )

    class LookupReached(Exception):
        pass

    def reached(_):
        raise LookupReached

    with pytest.raises(LookupReached):
        DownloaderApp._expand_download_source(
            app,
            job,
            None,
            SimpleNamespace(begin_primary=reached),
            control_check=lambda: None,
            blocking_step_cancelled=lambda: False,
        )


@pytest.mark.parametrize("accepted", [False, True])
@pytest.mark.parametrize("migrated", [False, True])
def test_recovery_admission_controls_history_retirement_and_bounded_migration_telemetry(
    tmp_path, monkeypatch, accepted, migrated
):
    original = _job(tmp_path)
    original.output_type = OutputType.MP4
    row = _missing_record(original)
    if migrated:
        row[OUTPUT_PROFILE_KEY] = "MP4 • 1080p Full HD • Auto CBR"
    owner = LibraryMediaRecoveryOwner()
    plan = owner.plan(row)
    other = {**row, "id": "other", "vodforge_output_path": str(tmp_path / "other.mp4")}
    writes, features, admitted, status = [], [], [], []
    monkeypatch.setattr(
        app_module, "save_history", lambda path, rows: writes.append(rows)
    )
    app = SimpleNamespace(
        library_media_recovery=owner,
        download_history=[row, other],
        history_path=tmp_path / "private-history.json",
        _start_or_queue_download_job=lambda job, **kw: admitted.append(job) or accepted,
        _record_feature=lambda *args, **kwargs: features.append((args, kwargs)),
        _reconcile_library_projection=lambda: None,
        _select_focus_view=lambda _: None,
        status_var=SimpleNamespace(set=status.append),
    )
    DownloaderApp._accept_library_redownload(app, plan)
    assert len(admitted) == 1 and admitted[0].recovery_reason == "missing_media"
    if not accepted:
        assert not writes and not features and not status
        assert app.download_history == [row, other]
    else:
        assert writes == [[other]] and app.download_history == [other]
        expected = [
            (("missing_media", "accepted"), {"dimensions": {"input_kind": "single"}})
        ]
        if migrated:
            expected.append(
                (
                    ("missing_media", "preset_migrated"),
                    {
                        "dimensions": {"preset": "everyday", "input_kind": "single"},
                    },
                )
            )
        assert features == expected
        assert "private-history" not in repr(features) and "missing" not in repr(
            features
        ).replace("missing_media", "")


@pytest.mark.parametrize(
    "path",
    [
        "/Volumes/An external archive/Finished films",
        r"C:\\Media archive\\Finished films",
        "/Volumes/旅行記/完成した動画",
    ],
)
def test_destination_updates_read_canonical_facts_and_never_reingest_rendered_projection(
    path,
):
    from yt_downloader.detail_ui import FactsText, detail_lines

    class ProjectedFacts(FactsText):
        # Controlled display projection only; actual updater/type/formatter are production.
        def __init__(self):
            self._snapshot = "Format        MP4\nOutput mode   Everyday"

        def get(self, *args):
            return "\n".join(
                line.label + "\n" + line.value if line.label else line.raw
                for line in detail_lines(self.raw_snapshot)
            )

    document = ProjectedFacts()
    app = SimpleNamespace(
        focus_summary_text=document,
        focus_output_display_var=SimpleNamespace(set=lambda _: None),
        _focus_shows_next_run_defaults=lambda: True,
        _submission_output_text=lambda: path,
        _set_text=lambda widget, text, **kwargs: setattr(widget, "_snapshot", text),
    )
    for _ in range(8):
        DownloaderApp._sync_focus_destination(app)
        assert document.raw_snapshot.count(path) == 1
        assert document.get().count(path) == 1
        facts = detail_lines(document.raw_snapshot)
        assert all(line.label for line in facts)
        assert [line.value for line in facts if line.label == "Save to"] == [path]
        assert [line.value for line in facts if line.label == "Output mode"] == [
            "Everyday"
        ]
    replacement = path + " 2"
    app._submission_output_text = lambda: replacement
    DownloaderApp._sync_focus_destination(app)
    assert [
        line.value
        for line in detail_lines(document.raw_snapshot)
        if line.label == "Save to"
    ] == [replacement]
