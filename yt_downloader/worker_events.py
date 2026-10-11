from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, NotRequired, Protocol, TypeAlias, TypedDict

from .models import DownloadJob
from .run_identity import annotate_job_metadata
from .updates import MacUpdatePlan, ReleaseInfo


class JobLogPayload(TypedDict):
    job: DownloadJob
    line: str


class JobInfoPayload(TypedDict):
    job: DownloadJob
    info: dict[str, Any]
    playlist_continues: NotRequired[bool]


class HistoryRecordPayload(JobInfoPayload):
    output_dir: str


class ThumbnailPreviewPayload(TypedDict, total=False):
    id: int
    url: str
    target: str
    run_id: str
    data: bytes
    error: str


class InstallationResultPayload(TypedDict):
    success: bool
    install_id: str


JobInfoEventName: TypeAlias = Literal[
    "job_metadata",
    "queued_preview",
    "item_terminal",
]

TransferUiEvent: TypeAlias = (
    tuple[Literal["log", "status"], str]
    | tuple[Literal["job_log"], JobLogPayload]
    | tuple[Literal["batch_item"], dict[str, Any]]
    | tuple[Literal["progress"], int | float]
    | tuple[Literal["progress_determinate"], int | float | None]
    | tuple[
        Literal["progress_indeterminate_start", "progress_indeterminate_stop"],
        None,
    ]
)

MetadataUiEvent: TypeAlias = (
    tuple[Literal["metadata"], dict[str, Any]]
    | tuple[Literal["job_metadata", "queued_preview", "item_terminal"], JobInfoPayload]
    | tuple[Literal["history_record"], HistoryRecordPayload]
    | tuple[Literal["thumbnail_preview_result"], ThumbnailPreviewPayload]
)

RuntimeUiEvent: TypeAlias = (
    tuple[Literal["metadata_fetch_done"], None]
    | tuple[Literal["metadata_error"], str | dict[str, str]]
    | tuple[Literal["runtime_error", "update_check_error", "update_install_error"], str]
    | tuple[Literal["download_folders"], list[Path]]
    | tuple[Literal["update_check_result"], ReleaseInfo]
    | tuple[Literal["update_ready"], Path | MacUpdatePlan]
    | tuple[
        Literal["cloud_seen_result", "first_launch_result"],
        InstallationResultPayload,
    ]
)

TerminalUiEvent: TypeAlias = tuple[
    Literal["done", "partial", "stopped", "error"],
    str,
]

UiEvent: TypeAlias = (
    TransferUiEvent | MetadataUiEvent | RuntimeUiEvent | TerminalUiEvent
)


def job_log_event(
    job: DownloadJob, line: str
) -> tuple[Literal["job_log"], JobLogPayload]:
    return "job_log", {"job": job, "line": line}


def job_info_event(
    name: JobInfoEventName,
    job: DownloadJob,
    info: dict[str, Any],
) -> tuple[JobInfoEventName, JobInfoPayload]:
    return name, {"job": job, "info": annotate_job_metadata(job, info)}


def history_record_event(
    job: DownloadJob,
    info: dict[str, Any],
    output_dir: str,
) -> tuple[Literal["history_record"], HistoryRecordPayload]:
    return "history_record", {
        "job": job,
        "info": annotate_job_metadata(job, info),
        "output_dir": output_dir,
    }


def thumbnail_preview_event(
    request_id: int,
    url: str,
    target: str,
    run_id: str,
    *,
    data: bytes | None = None,
    error: str | None = None,
) -> tuple[Literal["thumbnail_preview_result"], ThumbnailPreviewPayload]:
    payload: ThumbnailPreviewPayload = {
        "id": request_id,
        "url": url,
        "target": target,
        "run_id": run_id,
    }
    if data is not None:
        payload["data"] = data
    if error is not None:
        payload["error"] = error
    return "thumbnail_preview_result", payload


def installation_result_event(
    name: Literal["cloud_seen_result", "first_launch_result"],
    success: bool,
    install_id: str,
) -> tuple[
    Literal["cloud_seen_result", "first_launch_result"],
    InstallationResultPayload,
]:
    return name, {"success": success, "install_id": install_id}


class UiEventSink(Protocol):
    """Minimal FIFO producer contract shared by Queue and harness tracing sinks."""

    def put(self, event: UiEvent) -> None: ...
