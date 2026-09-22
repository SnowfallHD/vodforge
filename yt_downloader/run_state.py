from __future__ import annotations

import json
import os
import threading
import urllib.parse
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .history import (
    application_data_dir,
    sanitize_durable_text,
    sanitize_durable_thumbnail_record,
    sanitize_durable_url,
    sanitize_run_activity,
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
PERSISTED_TERMINAL_STATUSES = frozenset({"Failed", "Stopped", "Skipped"})


class RunStateError(RuntimeError):
    """Raised when durable active-run ownership cannot be maintained safely."""

    def __init__(
        self,
        message: str,
        *,
        cause: str = "invalid_record",
        stage: str = "journal_validation",
        attempt_key: str | None = None,
    ) -> None:
        super().__init__(message)
        self.cause = cause
        self.stage = stage
        self.attempt_key = attempt_key


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


RETRY_SOURCE_STATES = frozenset(
    {
        "retained",
        "sanitized",
        "missing_original",
        "unsupported_scheme",
        "invalid_source",
        "legacy_unknown",
    }
)


def retry_source_state(value: Any) -> str:
    """Explain durable source handling without retaining rejected input."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return "missing_original"
    text = str(value).strip()
    safe = sanitize_durable_url(value, preserve_youtube_context=True)
    if safe:
        return "retained" if safe == text else "sanitized"
    try:
        scheme = urllib.parse.urlsplit(text).scheme.casefold()
    except ValueError:
        return "invalid_source"
    if scheme and scheme not in {"http", "https"}:
        return "unsupported_scheme"
    return "invalid_source"


def saved_retry_source_state(payload: Mapping[str, Any]) -> str:
    """Older records cannot establish why a source was absent."""
    value = payload.get("retry_source_state")
    return (
        value
        if isinstance(value, str) and value in RETRY_SOURCE_STATES
        else "legacy_unknown"
    )


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
        "retry_source_state": retry_source_state(job.url),
        "retry_source_states": [
            retry_source_state(value) for value in (job.urls or [job.url])
        ],
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
            "video_crf": job.manual_settings.video_crf,
        },
        "mp3_settings": {
            "bitrate_kbps": job.mp3_settings.bitrate_kbps,
            "sample_rate": job.mp3_settings.sample_rate,
            "channels": job.mp3_settings.channels,
            "embed_metadata": job.mp3_settings.embed_metadata,
            "embed_cover_art": job.mp3_settings.embed_cover_art,
            "custom_cover_art_path": (
                str(job.mp3_settings.custom_cover_art_path)
                if job.mp3_settings.custom_cover_art_path is not None
                else None
            ),
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
        "origin_run_id": job.origin_run_id,
        "recovery_reason": job.recovery_reason,
        "execution_run_id": job.execution_run_id,
        "retry_of_run_id": job.retry_of_run_id,
        "annotation_source_owner": (job.annotation_source_owner or "").strip()[:512]
        or None,
    }


def deserialize_download_job(
    payload: Mapping[str, Any], *, allow_missing_retry_url: bool = False
) -> DownloadJob:
    try:
        manual = payload.get("manual_settings")
        mp3 = payload.get("mp3_settings")
        if not isinstance(manual, Mapping) or not isinstance(mp3, Mapping):
            raise TypeError("missing export settings")
        url = sanitize_durable_url(payload.get("url"), preserve_youtube_context=True)
        if not url and not allow_missing_retry_url:
            raise RunStateError(
                "The interrupted run record is invalid: missing safe retry URL",
                cause="missing_retry_url",
            )
        url = url or ""
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
            or ([url] if url else []),
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
                video_crf=_required_int(manual, "video_crf")
                if manual.get("video_crf") is not None
                else None,
            ),
            mp3_settings=Mp3ExportSettings(
                bitrate_kbps=_required_int(mp3, "bitrate_kbps"),
                sample_rate=(
                    str(mp3["sample_rate"]) if mp3.get("sample_rate") else None
                ),
                channels=str(mp3["channels"]) if mp3.get("channels") else None,
                embed_metadata=_required_bool(mp3, "embed_metadata"),
                embed_cover_art=_required_bool(mp3, "embed_cover_art"),
                custom_cover_art_path=(
                    Path(str(mp3["custom_cover_art_path"])).expanduser()
                    if mp3.get("custom_cover_art_path")
                    and "\x00" not in str(mp3["custom_cover_art_path"])
                    and len(str(mp3["custom_cover_art_path"])) <= 4096
                    else None
                ),
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
            execution_run_id=str(payload.get("execution_run_id") or "")[:128] or None,
            retry_of_run_id=str(payload.get("retry_of_run_id") or "")[:128] or None,
            annotation_source_owner=(
                str(payload.get("annotation_source_owner") or "").strip()[:512] or None
            ),
            recovery_reason="missing_media"
            if payload.get("recovery_reason") == "missing_media"
            else None,
            origin_run_id=(
                str(payload.get("origin_run_id") or "").strip()[:128] or None
            ),
        )
    except (TypeError, ValueError) as exc:
        raise RunStateError(f"The interrupted run record is invalid: {exc}") from exc
    if not job.run_id:
        raise RunStateError("The interrupted run record has no run identity.")
    return job


def _terminal_activity(activity_lines: list[str] | None, message: str) -> list[str]:
    """Keep the latest bounded cause with the terminal summary, not the whole log."""
    details = [
        line
        for line in (activity_lines or [])
        if line.startswith(("Failure category:", "Failure details:"))
    ]
    return sanitize_run_activity(details[-1:] + [message])


def _serialize_executable_job(job: DownloadJob) -> dict[str, Any]:
    payload = serialize_download_job(job)
    original_sources = job.urls or [job.url]
    if not payload["url"] or len(payload["urls"]) != len(original_sources):
        raise RunStateError(
            "The source link cannot be saved safely for this download. Paste a valid web link.",
            cause="missing_retry_url",
            stage="journal_validation",
            attempt_key=job.run_id,
        )
    # Admission and the next cold reader share a class contract; terminal/history
    # serialization deliberately remains tolerant for old nonretryable attempts.
    deserialize_download_job(payload)
    return payload


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
                raise RunStateError(
                    "The active-run record is unexpectedly large.",
                    cause="size_limit",
                    stage="journal_read",
                )
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RunStateError(
                f"The active-run record could not be loaded: {exc}",
                cause="malformed_json"
                if isinstance(exc, json.JSONDecodeError)
                else "invalid_encoding"
                if isinstance(exc, UnicodeError)
                else "read_failed",
                stage="journal_read",
            ) from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != RUN_STATE_SCHEMA_VERSION
        ):
            raise RunStateError(
                "The active-run record has an unsupported schema.",
                cause="unsupported_schema",
            )
        return payload

    def load(self) -> dict[str, Any] | None:
        with self._lock:
            return self._read_unlocked()

    def _write_unlocked(self, payload: Mapping[str, Any]) -> None:
        encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        if len(encoded) > MAX_RUN_STATE_BYTES:
            raise RunStateError(
                "The active-run record exceeds the safe size limit.",
                cause="size_limit",
                stage="journal_write",
            )
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_private_bytes(self.path, encoded)
        except OSError as exc:
            raise RunStateError(
                f"The active-run record could not be saved: {exc}",
                cause="write_failed",
                stage="journal_write",
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
                    "job": _serialize_executable_job(job),
                    "staging_dirs": [],
                    "children": [],
                    "recovered_failures": failures,
                    "queued_jobs": [
                        _serialize_executable_job(queued_job)
                        for queued_job in queued_jobs
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
            payload["queued_jobs"] = [_serialize_executable_job(job) for job in jobs]
            if failures:
                payload["recovered_failures"] = failures
            else:
                payload.pop("recovered_failures", None)
            if not jobs and payload.get("state") == "idle" and not failures:
                self._unlink_unlocked()
                return
            self._write_unlocked(payload)

    def load_queued_jobs(
        self, *, retire_missing_sources: bool = False
    ) -> list[DownloadJob]:
        with self._lock:
            payload = self._read_unlocked()
            records = self._queued_records(payload)
            jobs: list[DownloadJob] = []
            retained: list[dict[str, Any]] = []
            unavailable: list[dict[str, Any]] = []
            for record in records:
                try:
                    job = deserialize_download_job(record)
                except RunStateError as exc:
                    if not retire_missing_sources or exc.cause != "missing_retry_url":
                        raise
                    # Validate every other field before retaining this as history.
                    deserialize_download_job(record, allow_missing_retry_url=True)
                    unavailable.append(
                        {
                            "job": dict(record),
                            "terminal_status": "Failed",
                            "terminal_message": "The queued download has no saved source link. Paste the link to start it again.",
                        }
                    )
                else:
                    jobs.append(job)
                    retained.append(record)
            if unavailable:
                if payload is None or payload.get("state") == "active":
                    raise RunStateError(
                        "Active ownership must be recovered before queue repair."
                    )
                payload["queued_jobs"] = retained
                payload["recovered_failures"] = (
                    self._failure_records(payload) + unavailable
                )
                # Keep the original job/metadata under terminal history; do not
                # erase records, invent URLs, or launch incomplete jobs.
                self._write_unlocked(payload)
            return jobs

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

    def mark_terminal(
        self, status: str, message: str, *, activity_lines: list[str] | None = None
    ) -> DownloadJob:
        if status not in PERSISTED_TERMINAL_STATUSES:
            raise RunStateError(f"Unsupported durable terminal status: {status}")
        with self._lock:
            payload = self._read_unlocked()
            if payload is None or not isinstance(payload.get("job"), dict):
                raise RunStateError("No active run is available to terminalize.")
            job = deserialize_download_job(payload["job"], allow_missing_retry_url=True)
            job.terminal_status = status
            job.terminal_message = message
            job.activity_lines = _terminal_activity(activity_lines, message)
            failures = self._failure_records(payload)
            failures = [
                record
                for record in failures
                if str(record["job"].get("run_id") or "") != job.run_id
            ]
            failures.append(
                {
                    "job": dict(payload["job"]),
                    "terminal_status": status,
                    "terminal_message": message,
                    "failure_message": message,
                    "activity_lines": _terminal_activity(job.activity_lines, message),
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

    def mark_failed(self, message: str = INTERRUPTED_FAILURE_MESSAGE) -> DownloadJob:
        return self.mark_terminal("Failed", message)

    def record_terminal_attempt(
        self, job: DownloadJob, status: str, message: str
    ) -> None:
        """Durably upsert a terminal child/item attempt without changing active ownership."""

        if status not in PERSISTED_TERMINAL_STATUSES:
            raise RunStateError(f"Unsupported durable terminal status: {status}")
        with self._lock:
            payload = self._read_unlocked()
            if payload is None:
                payload = {
                    "schema_version": RUN_STATE_SCHEMA_VERSION,
                    "state": "idle",
                    "queued_jobs": [],
                }
            failures = [
                record
                for record in self._failure_records(payload)
                if str(record["job"].get("run_id") or "") != job.run_id
            ]
            failures.append(
                {
                    "job": serialize_download_job(job),
                    "terminal_status": status,
                    "terminal_message": message,
                    "failure_message": message,
                    "activity_lines": _terminal_activity(job.activity_lines, message),
                }
            )
            payload["recovered_failures"] = failures
            self._write_unlocked(payload)

    def load_terminal_jobs(self) -> list[DownloadJob]:
        with self._lock:
            payload = self._read_unlocked()
            jobs: list[DownloadJob] = []
            for record in self._failure_records(payload):
                job = deserialize_download_job(
                    record["job"], allow_missing_retry_url=True
                )
                status = str(record.get("terminal_status") or "Failed")
                if status not in PERSISTED_TERMINAL_STATUSES:
                    raise RunStateError(
                        f"Unsupported recovered terminal status: {status}"
                    )
                message = str(
                    record.get("terminal_message")
                    or record.get("failure_message")
                    or INTERRUPTED_FAILURE_MESSAGE
                )
                job.terminal_status = status
                if not job.url:
                    message += "\nThe saved source link is unavailable. Paste the source link to start a new download."
                job.terminal_message = message
                job.activity_lines = sanitize_run_activity(
                    record.get("activity_lines")
                ) or [
                    message,
                    "No additional technical detail was saved for this older run.",
                ]
                jobs.append(job)
            return jobs

    def load_failed_jobs(self) -> list[DownloadJob]:
        """Backward-compatible name for all durable terminal attempts."""

        return self.load_terminal_jobs()

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
        return store.load_terminal_jobs()
    if payload.get("state") != "active":
        raise RunStateError("The active-run record has an unknown state.")
    owner_pid = payload.get("owner_pid")
    if not isinstance(owner_pid, int) or owner_pid <= 1:
        raise RunStateError("The active-run owner record is invalid.")
    if owner_pid != os.getpid() and owner_command_reader(owner_pid) is not None:
        raise RunStateError(
            "Another live process still owns the active VODForge run; recovery was not attempted.",
            cause="live_owner",
            stage="owner_check",
        )
    job_payload = payload.get("job")
    if not isinstance(job_payload, dict):
        raise RunStateError("The active-run record has no job.")
    job = deserialize_download_job(job_payload, allow_missing_retry_url=True)
    staging_values = payload.get("staging_dirs", [])
    if not isinstance(staging_values, list) or not all(
        isinstance(value, str) for value in staging_values
    ):
        raise RunStateError(
            "The active-run staging record is invalid.",
            cause="invalid_staging",
            stage="staging_validation",
            attempt_key=job.run_id,
        )
    expected_staging_root = (
        Path(os.path.abspath(os.fspath(job.output_dir))).resolve(strict=False)
        / ".vfstage"
    )
    staging_dirs = [Path(value) for value in staging_values]
    if any(path.parent != expected_staging_root for path in staging_dirs):
        raise RunStateError(
            "The active-run staging record is outside its selected output root.",
            cause="invalid_staging",
            stage="staging_validation",
            attempt_key=job.run_id,
        )
    children = payload.get("children", [])
    if not isinstance(children, list) or not all(
        isinstance(child, dict) for child in children
    ):
        raise RunStateError("The active-run child record is invalid.")
    try:
        terminate_children(children, staging_dirs)
    except (ProcessOwnershipError, OSError) as exc:
        raise RunStateError(
            str(exc),
            cause="child_ownership",
            stage="child_cleanup",
            attempt_key=job.run_id,
        ) from exc
    try:
        cleanup_staging(staging_dirs)
    except (UnsafeOutputPathError, OSError) as exc:
        raise RunStateError(
            str(exc),
            cause="cleanup_failed",
            stage="staging_cleanup",
            attempt_key=job.run_id,
        ) from exc
    store.mark_failed()
    return store.load_terminal_jobs()


class RunRecoveryOwner:
    """Own durable run state while delegating process and staging operations."""

    def __init__(self, path: Path, *, diagnostic: Any = None) -> None:
        self.store = ActiveRunStore(path)
        self._diagnostic = diagnostic or (lambda _message: None)
        self._available = True
        self._failure: RunStateError | None = None
        self._failure_facts: Any = None
        self._failure_dimensions: dict[str, str] = {}
        self._operation_key = str(uuid.uuid4())
        self._observer: Any = None
        self._startup_pending = False
        self._startup_action = "failed"

    def _failed_startup(self, exc: RunStateError, *, queue: bool = False) -> None:
        from .failure_diagnostics import capture_failure

        self._available = False
        self._startup_action = "failed"
        # Retain bounded typed facts, not exception text/traceback, for telemetry.
        self._failure = RunStateError(
            "Recovery needs attention.",
            cause=exc.cause,
            stage=exc.stage,
            attempt_key=exc.attempt_key,
        )
        self._failure_facts = capture_failure(
            exc, stage="preparation", inspect_text=False
        )
        self._failure_dimensions = {
            "recovery_cause": exc.cause,
            "recovery_entry": "startup",
            "recovery_stage": "queue_loading" if queue else exc.stage,
            "recovery_schema": str(RUN_STATE_SCHEMA_VERSION),
            "recovery_disposition": "blocked_preserved",
        }
        self._startup_pending = True

    @property
    def recovery_notice(self) -> str | None:
        if self._available or self._failure is None:
            return None
        cause = self._failure.cause
        if cause == "live_owner":
            guidance = (
                "Another process may still own a previous download. Close other "
                "VODForge windows, then reopen VODForge and try again."
            )
        elif cause in {"read_failed", "write_failed"}:
            guidance = (
                "VODForge cannot read or save its download recovery data. Check "
                "available disk space and access to the app data folder, then reopen VODForge."
            )
        else:
            guidance = (
                "VODForge could not safely restore a previous download. Open "
                "Help & feedback → Send feedback and include diagnostics so the "
                "recovery data can be reviewed."
            )
        return (
            "Downloads need attention. "
            + guidance
            + "\n\nSaved media has not been removed. Local MP3-to-video conversion "
            "uses separate recovery data and remains available."
        )

    def bind_observer(self, observer: Any, *, report_startup: bool) -> None:
        self._observer = observer
        pending, self._startup_pending = self._startup_pending, False
        if pending and report_startup:
            self._observe(self._startup_action)

    def _observe(self, action: str, attempt_key: str | None = None) -> None:
        if self._observer is None or self._failure is None:
            return
        try:
            self._observer(
                "run_recovery_operation",
                action,
                operation_key=self._operation_key,
                attempt_key=attempt_key or self._failure.attempt_key,
                dimensions=dict(self._failure_dimensions),
                failure_detail=self._failure_facts if action == "failed" else None,
            )
        except Exception:  # noqa: BLE001 - optional diagnostics never change recovery
            self._diagnostic("Recovery observation could not be recorded.")

    def _observe_write_failure(
        self, exc: RunStateError, attempt_key: str | None = None, *, entry: str
    ) -> None:
        """Observe a refused intent without turning it into a startup lockout."""
        if self._observer is None:
            return
        try:
            from .failure_diagnostics import capture_failure

            self._observer(
                "run_recovery_operation",
                "failed",
                operation_key=str(uuid.uuid4()),
                attempt_key=exc.attempt_key or attempt_key,
                dimensions={
                    "recovery_cause": exc.cause,
                    "recovery_entry": entry,
                    "recovery_stage": exc.stage,
                    "recovery_schema": str(RUN_STATE_SCHEMA_VERSION),
                    "recovery_disposition": "blocked_preserved",
                },
                failure_detail=capture_failure(
                    exc, stage="preparation", inspect_text=False
                ),
            )
        except Exception:  # noqa: BLE001 - optional observation cannot replace the refusal
            try:
                self._diagnostic("Recovery observation could not be recorded.")
            except Exception:  # noqa: BLE001 - preserve the original journal failure
                return

    def startup_recovery(self) -> tuple[list[DownloadJob], list[DownloadJob]]:
        terminal = self.recover_at_startup()
        queued = self.queued_at_startup()
        if self._available:
            try:
                terminal = self.store.load_terminal_jobs()
            except RunStateError as exc:
                self._failed_startup(exc)
                self._diagnostic(f"terminal run recovery failed closed: {exc}")
                return [], []
        missing = sum(not job.url for job in terminal)
        if self._available and missing:
            self._failure = RunStateError(
                "Retained without retry authority.", cause="missing_retry_url"
            )
            self._failure_facts = None
            self._failure_dimensions = {
                "recovery_cause": "missing_retry_url",
                "recovery_entry": "startup",
                "recovery_stage": "terminal_restore",
                "recovery_schema": str(RUN_STATE_SCHEMA_VERSION),
                "recovery_disposition": "restored_without_retry",
                "item_count_bucket": (
                    "1"
                    if missing == 1
                    else "2_5"
                    if missing <= 5
                    else "6_20"
                    if missing <= 20
                    else "21_100"
                    if missing <= 100
                    else "101_plus"
                ),
            }
            self._startup_action = "restored_without_retry"
            self._startup_pending = True
        return terminal, queued

    def recover_at_startup(self) -> list[DownloadJob]:
        try:
            return recover_interrupted_run(self.store)
        except RunStateError as exc:
            self._failed_startup(exc)
            self._diagnostic(f"interrupted run recovery failed closed: {exc}")
            return []

    def queued_at_startup(self) -> list[DownloadJob]:
        if not self._available:
            return []
        try:
            return self.store.load_queued_jobs(retire_missing_sources=True)
        except RunStateError as exc:
            self._failed_startup(exc, queue=True)
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
            self._observe("start_blocked", job.run_id)
            raise RunStateError(
                "The previous active-run record could not be recovered safely."
            )
        try:
            self.store.begin(
                job,
                queued_jobs,
                superseded_run_id=superseded_run_id,
            )
        except RunStateError as exc:
            self._observe_write_failure(exc, job.run_id, entry="run_admission")
            raise

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
        try:
            self.store.replace_queue(jobs, superseded_run_id=superseded_run_id)
        except RunStateError as exc:
            self._observe_write_failure(
                exc, jobs[0].run_id if len(jobs) == 1 else None, entry="queue_update"
            )
            raise

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

    def terminal(
        self, status: str, message: str, *, activity_lines: list[str] | None = None
    ) -> None:
        self.store.mark_terminal(status, message, activity_lines=activity_lines)

    def terminal_attempt(self, job: DownloadJob, status: str, message: str) -> None:
        self.store.record_terminal_attempt(job, status, message)

    def finished(self, run_id: str, *, application_closing: bool) -> None:
        if not application_closing:
            self.store.clear(run_id)

    def removed_or_retried(self, run_id: str) -> None:
        self.store.clear(run_id)
