from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .history import application_data_dir
from .private_files import write_private_bytes

ANNOTATIONS_SCHEMA_VERSION = 1
MAX_ANNOTATIONS_FILE_BYTES = 4 * 1024 * 1024
MAX_ANNOTATIONS = 5000
MAX_NOTE_CHARS = 10_000
MAX_TAGS = 64
MAX_TAG_CHARS = 80
MAX_CATEGORY_CHARS = 120


class LibraryAnnotationsError(RuntimeError):
    """Raised when private Library annotations cannot be read or written safely."""


@dataclass(frozen=True, slots=True)
class LibraryAnnotation:
    """One immutable user-authored annotation attached to a canonical owner."""

    note: str = ""
    tags: tuple[str, ...] = ()
    category: str = ""

    @property
    def empty(self) -> bool:
        return not (self.note or self.tags or self.category)


def library_annotations_file_path(**kwargs: Any) -> Path:
    return application_data_dir(**kwargs) / "library-annotations.json"


def _bounded_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _clean_tags(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values: tuple[Any, ...] = tuple(value.split(","))
    elif isinstance(value, (list, tuple)):
        values = tuple(value)
    else:
        values = ()
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        tag = _bounded_text(raw, MAX_TAG_CHARS)
        folded = tag.casefold()
        if not tag or folded in seen:
            continue
        result.append(tag)
        seen.add(folded)
        if len(result) >= MAX_TAGS:
            break
    return tuple(result)


def sanitize_library_annotation(value: Any) -> LibraryAnnotation:
    source = value if isinstance(value, Mapping) else {}
    return LibraryAnnotation(
        note=_bounded_text(source.get("note"), MAX_NOTE_CHARS),
        tags=_clean_tags(source.get("tags")),
        category=_bounded_text(source.get("category"), MAX_CATEGORY_CHARS),
    )


def load_library_annotations(path: Path) -> dict[str, LibraryAnnotation]:
    """Load a bounded annotation ledger without rewriting malformed input."""

    try:
        if not path.exists():
            return {}
        if path.stat().st_size > MAX_ANNOTATIONS_FILE_BYTES:
            raise LibraryAnnotationsError(
                "VODForge Library annotations are unexpectedly large."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LibraryAnnotationsError(
            f"VODForge Library annotations could not be loaded: {exc}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise LibraryAnnotationsError(
            "VODForge Library annotations use an unsupported format."
        )
    raw_items = payload.get("items")
    if not isinstance(raw_items, dict):
        raise LibraryAnnotationsError(
            "VODForge Library annotations do not contain an item map."
        )
    result: dict[str, LibraryAnnotation] = {}
    for raw_owner, raw_annotation in raw_items.items():
        owner = _bounded_text(raw_owner, 512)
        if not owner:
            continue
        annotation = sanitize_library_annotation(raw_annotation)
        if not annotation.empty:
            result[owner] = annotation
        if len(result) >= MAX_ANNOTATIONS:
            break
    return result


def save_library_annotations(
    path: Path, annotations: Mapping[str, LibraryAnnotation]
) -> None:
    """Atomically persist the bounded, non-provider Library annotation ledger."""

    items = {
        _bounded_text(owner, 512): asdict(annotation)
        for owner, annotation in list(annotations.items())[:MAX_ANNOTATIONS]
        if _bounded_text(owner, 512) and not annotation.empty
    }
    payload = {"schema_version": ANNOTATIONS_SCHEMA_VERSION, "items": items}
    try:
        encoded = json.dumps(
            payload, ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")
        if len(encoded) > MAX_ANNOTATIONS_FILE_BYTES:
            raise LibraryAnnotationsError(
                "VODForge Library annotations exceed the safe size limit."
            )
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_private_bytes(path, encoded)
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, LibraryAnnotationsError):
            raise
        raise LibraryAnnotationsError(
            f"VODForge Library annotations could not be saved: {exc}"
        ) from exc


class LibraryAnnotationsOwner:
    """Own durable user annotations independently of provider metadata and UI."""

    def __init__(self, path: Path, *, diagnostic: Any = None) -> None:
        self.path = path
        self._diagnostic = diagnostic or (lambda _message: None)
        self._annotations: dict[str, LibraryAnnotation] = {}

    @property
    def snapshot(self) -> Mapping[str, LibraryAnnotation]:
        return MappingProxyType(dict(self._annotations))

    def load(self) -> Mapping[str, LibraryAnnotation]:
        try:
            self._annotations = load_library_annotations(self.path)
        except LibraryAnnotationsError as exc:
            self._diagnostic(str(exc))
            self._annotations = {}
        return self.snapshot

    def annotation_for(self, owner: str) -> LibraryAnnotation:
        return self._annotations.get(str(owner), LibraryAnnotation())

    def replace(self, owner: str, annotation: LibraryAnnotation) -> None:
        canonical_owner = _bounded_text(owner, 512)
        if not canonical_owner:
            raise LibraryAnnotationsError(
                "This Library item has no stable annotation owner."
            )
        prospective = dict(self._annotations)
        clean = sanitize_library_annotation(asdict(annotation))
        if clean.empty:
            prospective.pop(canonical_owner, None)
        else:
            prospective[canonical_owner] = clean
        save_library_annotations(self.path, prospective)
        self._annotations = prospective

    def remove(self, owner: str) -> None:
        canonical_owner = _bounded_text(owner, 512)
        if not canonical_owner or canonical_owner not in self._annotations:
            return
        prospective = dict(self._annotations)
        prospective.pop(canonical_owner, None)
        save_library_annotations(self.path, prospective)
        self._annotations = prospective

    def transfer(self, previous_owner: str, replacement_owner: str) -> None:
        """Atomically preserve one annotation when canonical run ownership changes."""

        previous = _bounded_text(previous_owner, 512)
        replacement = _bounded_text(replacement_owner, 512)
        if (
            not previous
            or not replacement
            or previous == replacement
            or previous not in self._annotations
        ):
            return
        prospective = dict(self._annotations)
        annotation = prospective.pop(previous)
        prospective.setdefault(replacement, annotation)
        save_library_annotations(self.path, prospective)
        self._annotations = prospective
