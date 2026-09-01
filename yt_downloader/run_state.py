from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .history import (
    application_data_dir,
    sanitize_durable_text,
    sanitize_durable_thumbnail_record,
    sanitize_durable_url,
)
from .models import (
    DownloadJob,
    ExportMode,
    ManualAudioCodec,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)
from .private_files import write_private_bytes
from .process_lifecycle import (
    ProcessOwnershipError,
    process_command,
    terminate_recorded_children,
)
from .safe_output import (
    UnsafeOutputPathError,
    cleanup_abandoned_staging_transactions,
)

RUN_STATE_SCHEMA_VERSION = 1
MAX_RUN_STATE_BYTES = 512 * 1024
INTERRUPTED_FAILURE_MESSAGE = (
    "VODForge closed before this run finished. Its incomplete staging files were "
    "removed; retry the run to start again."
)


class RunStateError(RuntimeError):
    """Raised when durable active-run ownership cannot be maintained safely."""


def run_state_file_path(**kwargs: Any) -> Path:
    return application_data_dir(**kwargs) / "active-run.json"


def _safe_preview(info: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(info, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in ("id", "title", "uploader", "channel", "description"):
        value = sanitize_durable_text(info.get(key))[:20_000]
        if value:
            result[key] = value
    duration = info.get("duration")
    if (
        isinstance(duration, (int, float))
        and not isinstance(duration, bool)
        and 0 <= float(duration) < 10**9
    ):
        result["duration"] = duration
    tags = info.get("tags")
    if isinstance(tags, list):
        result["tags"] = [
            sanitize_durable_text(value)[:500]
            for value in tags[:500]
            if sanitize_durable_text(value).strip()
        ]
    thumbnail = sanitize_durable_url(
        info.get("thumbnail"), preserve_youtube_context=False
    )
    if thumbnail:
        result["thumbnail"] = thumbnail
    best_thumbnail = sanitize_durable_thumbnail_record(info.get("best_thumbnail"))
    if best_thumbnail:
        result["best_thumbnail"] = best_thumbnail
    result["vodforge_output_type"] = str(
        info.get("vodforge_output_type") or OutputType.MP4.value
    )
    return result


def _required_int(values: Mapping[str, Any], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise TypeError(f"invalid {key}")
    return int(value)


def _required_bool(values: Mapping[str, Any], key: str) -> bool:
    value = values.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"invalid {key}")
    return value


def serialize_download_job(job: DownloadJob) -> dict[str, Any]:
    """Persist retry authority without cookie files, browser profiles, or secrets."""

    safe_url = sanitize_durable_url(job.url, preserve_youtube_context=True)
    safe_urls = [
        safe
        for value in (job.urls or [job.url])
        if (safe := sanitize_durable_url(value, preserve_youtube_context=True))
    ]
    return {
        "url": safe_url or "",
        "urls": safe_urls,
        "output_dir": str(job.output_dir),
        "output_type": job.output_type.value,
        "quality_label": job.quality_label,
        "export_mode": job.export_mode.value,
        "manual_settings": {
            "video_bitrate_kbps": job.manual_settings.video_bitrate_kbps,
            "audio_bitrate_kbps": job.manual_settings.audio_bitrate_kbps,
            "audio_sample_rate": job.manual_settings.audio_sample_rate,
            "audio_channels": job.manual_settings.audio_channels,
            "audio_codec": job.manual_settings.audio_codec.value,
            "x264_preset": job.manual_settings.x264_preset,
        },
        "mp3_settings": {
            "bitrate_kbps": job.mp3_settings.bitrate_kbps,
            "sample_rate": job.mp3_settings.sample_rate,
            "channels": job.mp3_settings.channels,
            "embed_metadata": job.mp3_settings.embed_metadata,
            "embed_cover_art": job.mp3_settings.embed_cover_art,
        },
        "single_video_only": job.single_video_only,
        "use_nvenc": job.use_nvenc,
        "embed_thumbnail": job.embed_thumbnail,
        "write_thumbnail": job.write_thumbnail,
        "embed_metadata": job.embed_metadata,
        "write_info_json": job.write_info_json,
        "tags": [sanitize_durable_text(value)[:500] for value in job.tags[:500]],
        "batch_mode": job.batch_mode,
        "preview_info": _safe_preview(job.preview_info),
        "run_id": job.run_id,
    }


def deserialize_download_job(payload: Mapping[str, Any]) -> DownloadJob:
    try:
        manual = payload.get("manual_settings")
        mp3 = payload.get("mp3_settings")
        if not isinstance(manual, Mapping) or not isinstance(mp3, Mapping):
            raise TypeError("missing export settings")
        url = sanitize_durable_url(payload.get("url"), preserve_youtube_context=True)
        if not url:
            raise ValueError("missing safe retry URL")
        output_dir_value = payload.get("output_dir")
        if not isinstance(output_dir_value, str) or not output_dir_value.strip():
            raise ValueError("invalid output directory")
        output_dir = Path(output_dir_value).expanduser()
        if "\x00" in str(output_dir):
            raise ValueError("invalid output directory")
        job = DownloadJob(
            url=url,
            urls=[
                safe
                for value in payload.get("urls", [])
                if (safe := sanitize_durable_url(value, preserve_youtube_context=True))
            ]
            or [url],
            output_dir=output_dir,
            output_type=OutputType(str(payload.get("output_type"))),
            quality_label=str(payload.get("quality_label") or "1080p Full HD"),
            export_mode=ExportMode(str(payload.get("export_mode"))),
            manual_settings=ManualExportSettings(
                video_bitrate_kbps=_required_int(manual, "video_bitrate_kbps"),
                audio_bitrate_kbps=_required_int(manual, "audio_bitrate_kbps"),
                audio_sample_rate=str(manual.get("audio_sample_rate")),
                audio_channels=str(manual.get("audio_channels")),
                audio_codec=ManualAudioCodec(str(manual.get("audio_codec"))),
                x264_preset=str(manual.get("x264_preset")),
            ),
            mp3_settings=Mp3ExportSettings(
                bitrate_kbps=_required_int(mp3, "bitrate_kbps"),
                sample_rate=(
                    str(mp3["sample_rate"]) if mp3.get("sample_rate") else None
                ),
                channels=str(mp3["channels"]) if mp3.get("channels") else None,
                embed_metadata=_required_bool(mp3, "embed_metadata"),
                embed_cover_art=_required_bool(mp3, "embed_cover_art"),
            ),
            single_video_only=_required_bool(payload, "single_video_only"),
            use_nvenc=_required_bool(payload, "use_nvenc"),
            embed_thumbnail=_required_bool(payload, "embed_thumbnail"),
            write_thumbnail=_required_bool(payload, "write_thumbnail"),
            embed_metadata=_required_bool(payload, "embed_metadata"),
            write_info_json=_required_bool(payload, "write_info_json"),
            tags=[str(value)[:500] for value in payload.get("tags", [])[:500]],
            batch_mode=_required_bool(payload, "batch_mode"),
            preview_info=_safe_preview(payload.get("preview_info")),
            run_id=str(payload.get("run_id") or "")[:128],
        )
    except (TypeError, ValueError) as exc:
        raise RunStateError(f"The interrupted run record is invalid: {exc}") from exc
    if not job.run_id:
        raise RunStateError("The interrupted run record has no run identity.")
    return job


class ActiveRunStore:
    """One sequential-run journal shared by UI, staging, and child ownership."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def _read_unlocked(self) -> dict[str, Any] | None:
        try:
            if not self.path.exists():
                return None
            if self.path.stat().st_size > MAX_RUN_STATE_BYTES:
                raise RunStateError("The active-run record is unexpectedly large.")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RunStateError(
                f"The active-run record could not be loaded: {exc}"
            ) from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != RUN_STATE_SCHEMA_VERSION
        ):
            raise RunStateError("The active-run record has an unsupported schema.")
        return payload

    def load(self) -> dict[str, Any] | None:
        with self._lock:
            return self._read_unlocked()

    def _write_unlocked(self, payload: Mapping[str, Any]) -> None:
        encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        if len(encoded) > MAX_RUN_STATE_BYTES:
            raise RunStateError("The active-run record exceeds the safe size limit.")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_private_bytes(self.path, encoded)
        except OSError as exc:
            raise RunStateError(
                f"The active-run record could not be saved: {exc}"
            ) from exc

    def _unlink_unlocked(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise RunStateError(
                f"The active-run record could not be removed: {exc}"
            ) from exc

    @staticmethod
    def _queued_records(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        if payload is None:
            return []
        records = payload.get("queued_jobs", [])
        if not isinstance(records, list) or not all(
            isinstance(record, dict) for record in records
        ):
            raise RunStateError("The queued-run records are invalid.")
        run_ids: set[str] = set()
        result: list[dict[str, Any]] = []
        for record in records:
            run_id = str(record.get("run_id") or "")
            if not run_id:
                raise RunStateError("A queued-run record has no run identity.")
            if run_id in run_ids:
                raise RunStateError("The queued-run records contain a duplicate run.")
            run_ids.add(run_id)
            result.append(dict(record))
        return result

    def begin(
        self,
        job: DownloadJob,
        queued_jobs: Sequence[DownloadJob] = (),
        *,
        superseded_run_id: str | None = None,
    ) -> None:
        with self._lock:
            existing = self._read_unlocked()
            failures = self._failure_records(existing)
            if superseded_run_id:
                failures = [
                    record
                    for record in failures
                    if str(record["job"].get("run_id") or "") != superseded_run_id
                ]
            self._write_unlocked(
                {
                    "schema_version": RUN_STATE_SCHEMA_VERSION,
                    "state": "active",
                    "owner_pid": os.getpid(),
                    "job": serialize_download_job(job),
                    "staging_dirs": [],
                    "children": [],
                    "recovered_failures": failures,
                    "queued_jobs": [
                        serialize_download_job(queued_job) for queued_job in queued_jobs
                    ],
                }
            )

    def replace_queue(
        self,
        jobs: Sequence[DownloadJob],
        *,
        superseded_run_id: str | None = None,
    ) -> None:
        """Durably replace the ordered queue without disturbing active ownership."""

        with self._lock:
            payload = self._read_unlocked()
            failures = self._failure_records(payload)
            if superseded_run_id:
                failures = [
                    record
                    for record in failures
                    if str(record["job"].get("run_id") or "") != superseded_run_id
                ]
            if payload is None:
                payload = {
                    "schema_version": RUN_STATE_SCHEMA_VERSION,
                    "state": "idle",
                }
            payload["queued_jobs"] = [serialize_download_job(job) for job in jobs]
            if failures:
                payload["recovered_failures"] = failures
            else:
                payload.pop("recovered_failures", None)
            if not jobs and payload.get("state") == "idle" and not failures:
                self._unlink_unlocked()
                return
            self._write_unlocked(payload)

    def load_queued_jobs(self) -> list[DownloadJob]:
        with self._lock:
            payload = self._read_unlocked()
            return [
                deserialize_download_job(record)
                for record in self._queued_records(payload)
            ]

    @staticmethod
    def _failure_records(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        if payload is None:
            return []
        records = payload.get("recovered_failures", [])
        if not isinstance(records, list) or not all(
            isinstance(record, dict) and isinstance(record.get("job"), dict)
            for record in records
        ):
            raise RunStateError("The recovered-run failure records are invalid.")
        result = [dict(record) for record in records]
        if payload.get("state") == "failed" and isinstance(payload.get("job"), dict):
            result.append(
                {
                    "job": dict(payload["job"]),
                    "failure_message": str(
                        payload.get("failure_message") or INTERRUPTED_FAILURE_MESSAGE
                    ),
                }
            )
        unique: dict[str, dict[str, Any]] = {}
        for record in result:
            job = record["job"]
            run_id = str(job.get("run_id") or "")
            if not run_id:
                raise RunStateError("A recovered-run failure has no run identity.")
            unique[run_id] = record
        return list(unique.values())

    def update_preview(self, run_id: str, info: Mapping[str, Any]) -> None:
        with self._lock:
            payload = self._read_unlocked()
            if payload is None or payload.get("state") != "active":
                return
            job = payload.get("job")
            if not isinstance(job, dict) or job.get("run_id") != run_id:
                return
            job["preview_info"] = _safe_preview(info)
            self._write_unlocked(payload)

    def add_staging_dir(self, run_id: str, path: Path) -> None:
        with self._lock:
            payload = self._read_unlocked()
            if payload is None or payload.get("state") != "active":
                return
            job = payload.get("job")
            if not isinstance(job, dict) or job.get("run_id") != run_id:
                return
            paths = payload.setdefault("staging_dirs", [])
            value = str(path)
            if isinstance(paths, list) and value not in paths:
                paths.append(value)
            self._write_unlocked(payload)

    def child_started(self, pid: int, args: Any) -> None:
        with self._lock:
            payload = self._read_unlocked()
            if payload is None or payload.get("state") != "active":
                return
            argv = (
                [str(value) for value in args]
                if isinstance(args, (list, tuple))
                else [str(args)]
            )
            children = payload.setdefault("children", [])
            if isinstance(children, list):
                children[:] = [item for item in children if item.get("pid") != pid]
                children.append({"pid": int(pid), "argv": argv})
            self._write_unlocked(payload)

    def child_exited(self, pid: int) -> None:
        with self._lock:
            payload = self._read_unlocked()
            if payload is None or payload.get("state") != "active":
                return
            children = payload.get("children")
            if isinstance(children, list):
                payload["children"] = [
                    item for item in children if item.get("pid") != pid
                ]
            self._write_unlocked(payload)

    def mark_failed(self, message: str = INTERRUPTED_FAILURE_MESSAGE) -> DownloadJob:
        with self._lock:
            payload = self._read_unlocked()
            if payload is None or not isinstance(payload.get("job"), dict):
                raise RunStateError("No interrupted run is available to recover.")
            job = deserialize_download_job(payload["job"])
            job.terminal_status = "Failed"
            job.terminal_message = message
            job.activity_lines = [message]
            failures = self._failure_records(payload)
            failures = [
                record
                for record in failures
                if str(record["job"].get("run_id") or "") != job.run_id
            ]
            failures.append(
                {
                    "job": dict(payload["job"]),
                    "failure_message": message,
                }
            )
            self._write_unlocked(
                {
                    "schema_version": RUN_STATE_SCHEMA_VERSION,
                    "state": "idle",
                    "recovered_failures": failures,
                    "queued_jobs": self._queued_records(payload),
                }
            )
            return job

    def load_failed_jobs(self) -> list[DownloadJob]:
        with self._lock:
            payload = self._read_unlocked()
            jobs: list[DownloadJob] = []
            for record in self._failure_records(payload):
                job = deserialize_download_job(record["job"])
                message = str(
                    record.get("failure_message") or INTERRUPTED_FAILURE_MESSAGE
                )
                job.terminal_status = "Failed"
                job.terminal_message = message
                job.activity_lines = [message]
                jobs.append(job)
            return jobs

    def load_failed_job(self) -> DownloadJob | None:
        jobs = self.load_failed_jobs()
        return jobs[0] if jobs else None

    def clear(self, run_id: str) -> None:
        with self._lock:
            payload = self._read_unlocked()
            if payload is None:
                return
            active_job = (
                payload.get("job") if payload.get("state") == "active" else None
            )
            active_matches = (
                isinstance(active_job, dict) and active_job.get("run_id") == run_id
            )
            existing_failures = self._failure_records(payload)
            failures = [
                record
                for record in existing_failures
                if str(record["job"].get("run_id") or "") != run_id
            ]
            existing_queue = self._queued_records(payload)
            queued = [
                record
                for record in existing_queue
                if str(record.get("run_id") or "") != run_id
            ]
            if (
                not active_matches
                and len(failures) == len(existing_failures)
                and len(queued) == len(existing_queue)
            ):
                return
            if not active_matches:
                if payload.get("state") == "active":
                    payload["recovered_failures"] = failures
                    payload["queued_jobs"] = queued
                    self._write_unlocked(payload)
                    return
                if not failures and not queued:
                    self._unlink_unlocked()
                    return
                payload["recovered_failures"] = failures
                payload["queued_jobs"] = queued
                self._write_unlocked(payload)
                return
            if failures or queued:
                self._write_unlocked(
                    {
                        "schema_version": RUN_STATE_SCHEMA_VERSION,
                        "state": "idle",
                        "recovered_failures": failures,
                        "queued_jobs": queued,
                    }
                )
                return
            self._unlink_unlocked()


def recover_interrupted_run(
    store: ActiveRunStore,
    *,
    terminate_children: Callable[
        [Sequence[Mapping[str, Any]], Sequence[Path]], None
    ] = terminate_recorded_children,
    cleanup_staging: Callable[
        [Sequence[Path]], None
    ] = cleanup_abandoned_staging_transactions,
    owner_command_reader: Callable[[int], str | None] = process_command,
) -> list[DownloadJob]:
    """Fail closed unless every live child is bound to the recorded staging transaction."""

    payload = store.load()
    if payload is None:
        return []
    if payload.get("state") in {"failed", "idle"}:
        return store.load_failed_jobs()
    if payload.get("state") != "active":
        raise RunStateError("The active-run record has an unknown state.")
    owner_pid = payload.get("owner_pid")
    if not isinstance(owner_pid, int) or owner_pid <= 1:
        raise RunStateError("The active-run owner record is invalid.")
    if owner_pid != os.getpid() and owner_command_reader(owner_pid) is not None:
        raise RunStateError(
            "Another live process still owns the active VODForge run; recovery was not attempted."
        )
    job_payload = payload.get("job")
    if not isinstance(job_payload, dict):
        raise RunStateError("The active-run record has no job.")
    job = deserialize_download_job(job_payload)
    staging_values = payload.get("staging_dirs", [])
    if not isinstance(staging_values, list) or not all(
        isinstance(value, str) for value in staging_values
    ):
        raise RunStateError("The active-run staging record is invalid.")
    expected_staging_root = (
        Path(os.path.abspath(os.fspath(job.output_dir))).resolve(strict=False)
        / ".vfstage"
    )
    staging_dirs = [Path(value) for value in staging_values]
    if any(path.parent != expected_staging_root for path in staging_dirs):
        raise RunStateError(
            "The active-run staging record is outside its selected output root."
        )
    children = payload.get("children", [])
    if not isinstance(children, list) or not all(
        isinstance(child, dict) for child in children
    ):
        raise RunStateError("The active-run child record is invalid.")
    try:
        terminate_children(children, staging_dirs)
        cleanup_staging(staging_dirs)
    except (ProcessOwnershipError, UnsafeOutputPathError) as exc:
        raise RunStateError(str(exc)) from exc
    store.mark_failed()
    return store.load_failed_jobs()


class RunRecoveryOwner:
    """Own durable run state while delegating process and staging operations."""

    def __init__(self, path: Path, *, diagnostic: Any = None) -> None:
        self.store = ActiveRunStore(path)
        self._diagnostic = diagnostic or (lambda _message: None)
        self._available = True

    def recover_at_startup(self) -> list[DownloadJob]:
        try:
            return recover_interrupted_run(self.store)
        except RunStateError as exc:
            self._available = False
            self._diagnostic(f"interrupted run recovery failed closed: {exc}")
            return []

    def queued_at_startup(self) -> list[DownloadJob]:
        if not self._available:
            return []
        try:
            return self.store.load_queued_jobs()
        except RunStateError as exc:
            self._available = False
            self._diagnostic(f"queued run recovery failed closed: {exc}")
            return []

    def begin(
        self,
        job: DownloadJob,
        queued_jobs: Sequence[DownloadJob] = (),
        *,
        superseded_run_id: str | None = None,
    ) -> None:
        if not self._available:
            raise RunStateError(
                "The previous active-run record could not be recovered safely."
            )
        self.store.begin(
            job,
            queued_jobs,
            superseded_run_id=superseded_run_id,
        )

    def queue_changed(
        self,
        jobs: Sequence[DownloadJob],
        *,
        superseded_run_id: str | None = None,
    ) -> None:
        if not self._available:
            raise RunStateError(
                "The durable run queue is unavailable because recovery failed safely."
            )
        self.store.replace_queue(jobs, superseded_run_id=superseded_run_id)

    def staging_started(self, job: DownloadJob, path: Path) -> None:
        self.store.add_staging_dir(job.run_id, path)

    def metadata_observed(self, job: DownloadJob, info: Mapping[str, Any]) -> None:
        self.store.update_preview(job.run_id, info)

    def child_event(self, event: str, process: Any) -> None:
        pid = int(getattr(process, "pid", 0) or 0)
        if pid <= 1:
            raise RunStateError("A child process started without a valid PID.")
        if event == "started":
            self.store.child_started(pid, getattr(process, "args", []))
        elif event == "exited":
            self.store.child_exited(pid)

    def failed(self, message: str) -> None:
        self.store.mark_failed(message)

    def finished(self, run_id: str, *, application_closing: bool) -> None:
        if not application_closing:
            self.store.clear(run_id)

    def removed_or_retried(self, run_id: str) -> None:
        self.store.clear(run_id)
