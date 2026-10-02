"""Generation-owned saved captions; no audio decoder or media mutation."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import Property, QLocale, QObject, Signal, Slot

from yt_downloader.subtitle_cues import (
    CueTimeline,
    extract_saved_cues,
    file_identity,
    probe_saved_subtitles,
)


class SubtitleSession(QObject):
    changed = Signal()
    completed = Signal(object)

    def __init__(self, ffmpeg: str | None, parent: QObject | None = None):
        super().__init__(parent)
        self.ffmpeg = ffmpeg
        self.generation = 0
        self.path: Path | None = None
        self.identity: tuple[int, int, int, int] | None = None
        self.catalog: dict[str, Any] = {"original": None, "translations": []}
        self.enabled = False
        self.selected = -1
        self.loading = False
        self.message = "No saved captions available"
        self.cues: dict[str, CueTimeline] = {}
        self.requests: dict[str, threading.Event] = {}
        self.completed.connect(self._accept)

    def load(self, path: Path | None, summary: Any = None) -> None:
        for event in self.requests.values():
            event.set()
        self.requests.clear()
        self.generation += 1
        self.path = path
        self.catalog = {"original": None, "translations": []}
        self.enabled = False
        self.selected = -1
        self.cues.clear()
        self.loading = bool(path and self.ffmpeg)
        self.message = (
            "Reading saved captions…" if self.loading else "No saved captions available"
        )
        try:
            self.identity = file_identity(path) if path else None
        except OSError:
            self.identity = None
            self.loading = False
            self.message = "Saved file is unavailable"
        self.changed.emit()
        if self.loading:
            self._start(
                "catalog",
                lambda cancel: probe_saved_subtitles(
                    cast(str, self.ffmpeg), cast(Path, path), cancel, summary
                ),
            )

    def _start(self, role: str, work: Callable[[threading.Event], Any]) -> None:
        previous = self.requests.get(role)
        if previous:
            previous.set()
        cancel: threading.Event = threading.Event()
        self.requests[role] = cancel
        generation, path, identity = self.generation, self.path, self.identity
        self.changed.emit()

        def run():
            try:
                if not path or file_identity(path) != identity:
                    raise ValueError("Saved file changed")
                result = work(cancel)
                if file_identity(path) != identity:
                    raise ValueError("Saved file changed")
                error = False
            except (OSError, ValueError, TypeError, RuntimeError):
                result, error = None, True
            if not cancel.is_set():
                self.completed.emit((generation, role, cancel, result, error))

        threading.Thread(target=run, daemon=True, name="saved-subtitles").start()

    @Slot(object)
    def _accept(self, payload: tuple[int, str, threading.Event, Any, bool]) -> None:
        generation, role, cancel, result, error = payload
        if (
            generation != self.generation
            or self.requests.get(role) is not cancel
            or cancel.is_set()
        ):
            return
        self.requests.pop(role)
        if role == "catalog":
            self.loading = False
            if not error:
                self.catalog = result
                for row in self.catalog["translations"]:
                    language = QLocale.languageToString(
                        QLocale(row["language"]).language()
                    )
                    if language != "C":
                        row["label"] = f"{language} · Track {row['index'] + 1}"
            self.message = (
                "Saved captions unavailable"
                if error
                else (
                    ""
                    if self.catalog["original"]
                    else "Original caption language is not identified in this file"
                )
            )
        elif error:
            if role == "original":
                self.enabled = False
            else:
                self.selected = -1
            self.cues.pop(role, None)
            self.message = "Saved subtitle text could not be read. Try again."
        else:
            self.cues[role] = CueTimeline(result)
            self.message = ""
        self.changed.emit()

    @Property(cast(type, "QVariantMap"), notify=changed)
    def state(self) -> dict[str, Any]:
        return {
            "originalAvailable": bool(self.catalog["original"]),
            "originalEnabled": self.enabled,
            "translations": self.catalog["translations"],
            "translationIndex": self.selected,
            "loading": self.loading,
            "message": self.message,
            "originalPending": "original" in self.requests,
            "translationPending": "translation" in self.requests,
        }

    @Slot()
    def toggleOriginal(self) -> None:
        original = self.catalog["original"]
        if not original:
            return
        self.enabled = not self.enabled
        if (
            self.enabled
            and "original" not in self.cues
            and "original" not in self.requests
        ):
            self._start(
                "original",
                lambda cancel: extract_saved_cues(
                    cast(str, self.ffmpeg),
                    cast(Path, self.path),
                    original["index"],
                    cancel,
                ),
            )
        self.changed.emit()

    @Slot(int)
    def selectTranslation(self, index: int) -> None:
        if index == self.selected:
            return
        row = next(
            (row for row in self.catalog["translations"] if row["index"] == index), None
        )
        if index != -1 and row is None:
            return
        previous = self.requests.pop("translation", None)
        if previous:
            previous.set()
        self.selected = index
        self.cues.pop("translation", None)
        if row:
            self._start(
                "translation",
                lambda cancel: extract_saved_cues(
                    cast(str, self.ffmpeg), cast(Path, self.path), index, cancel
                ),
            )
        self.changed.emit()

    @Slot(float, result="QVariantMap")
    def textAt(self, position_ms: float) -> dict[str, str]:
        if not math.isfinite(position_ms) or position_ms < 0:
            return {"original": "", "translation": ""}
        return {
            "original": self.cues.get("original", CueTimeline()).text_at(
                int(position_ms)
            )
            if self.enabled
            else "",
            "translation": self.cues.get("translation", CueTimeline()).text_at(
                int(position_ms)
            )
            if self.selected >= 0
            else "",
        }
