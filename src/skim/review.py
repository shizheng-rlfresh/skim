"""Shared local review storage and triage helpers for skim.

This module owns persisted annotation records, file-level annotation support,
annotation-version reloads, and the normalized triage item contract used by the
web UI and TUI.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

FILE_ANNOTATION_KEY = "@file"
FILE_TARGET_KIND = "file"
JSON_PATH_TARGET_KIND = "json_path"
REVIEW_VERSION = 1

MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdown"}
JSON_EXTENSIONS = {".json"}
NOTEBOOK_EXTENSIONS = {".ipynb"}
CSV_EXTENSIONS = {".csv"}
XLSX_EXTENSIONS = {".xlsx"}
CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".yaml",
    ".yml",
    ".toml",
    ".sh",
    ".bash",
    ".rs",
    ".go",
    ".sql",
    ".xml",
}
TEXT_EXTENSIONS = {
    "",
    ".txt",
    ".log",
    ".rst",
    ".ini",
    ".cfg",
    ".conf",
}


@dataclass(frozen=True)
class AnnotationRecord:
    """Persisted annotation for one file target."""

    id: str
    created_at: str
    updated_at: str
    tags: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class TriageItem:
    """Normalized workspace-level review row."""

    annotation_id: str
    file_path: str
    target_kind: str
    target_label: str
    target_path: str | None
    preview_kind: str
    tags: tuple[str, ...]
    note_preview: str
    note_full: str
    created_at: str
    updated_at: str

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        payload = asdict(self)
        payload["tags"] = list(self.tags)
        return payload


class AnnotationStore:
    """Local JSON-backed annotation storage rooted at the current browse path."""

    def __init__(self, review_root: Path) -> None:
        """Initialize the annotation store for one browse root."""
        self.review_root = review_root.resolve()
        self.path = self.review_root / ".skim" / "review.json"
        self._payload = self._load()
        self._file_annotations: dict[str, dict[str, tuple[AnnotationRecord, ...]]] = {}
        self._annotation_version = self._compute_annotation_version()

    @property
    def payload(self) -> dict[str, Any]:
        """Return the current persisted payload after refreshing from disk."""
        self._ensure_fresh()
        return self._payload

    @property
    def annotation_version(self) -> str:
        """Return a stable version token for the current review payload."""
        self._ensure_fresh()
        return self._annotation_version

    def annotations_for_file(self, source_path: Path) -> dict[str, tuple[AnnotationRecord, ...]]:
        """Return stored annotations for one source file."""
        self._ensure_fresh()
        relative_path = self.relative_file_path(source_path)
        cached = self._file_annotations.get(relative_path)
        if cached is None:
            cached = self._build_annotations_for_relative_path(relative_path)
            self._file_annotations[relative_path] = cached
        return cached

    def annotations_for_path(self, source_path: Path, path: str) -> tuple[AnnotationRecord, ...]:
        """Return all annotations by file-relative target path, newest first."""
        return self.annotations_for_file(source_path).get(path, ())

    def get_annotation(self, source_path: Path, path: str) -> AnnotationRecord | None:
        """Return the newest annotation by file-relative target path."""
        records = self.annotations_for_path(source_path, path)
        return records[0] if records else None

    def add_annotation(
        self,
        source_path: Path,
        path: str,
        *,
        tags: tuple[str, ...],
        note: str,
    ) -> AnnotationRecord:
        """Append one annotation entry for a target path and persist it."""
        self._ensure_fresh()
        timestamp = _annotation_timestamp()
        record = AnnotationRecord(
            id=str(uuid4()),
            created_at=timestamp,
            updated_at=timestamp,
            tags=_normalize_annotation_tags(tags),
            note=note,
        )
        _, annotations = self._persisted_annotations_for_file(source_path)
        existing = annotations.get(path, [])
        normalized = self._normalize_annotation_entries(existing)
        updated = _sort_annotation_records([*normalized, record])
        annotations[path] = [_annotation_payload(entry) for entry in updated]
        self.annotations_for_file(source_path)[path] = tuple(updated)
        self._save()
        return record

    def update_annotation(
        self,
        source_path: Path,
        path: str,
        annotation_id: str,
        *,
        tags: tuple[str, ...],
        note: str,
    ) -> AnnotationRecord | None:
        """Update one persisted annotation entry by id."""
        self._ensure_fresh()
        _, annotations = self._persisted_annotations_for_file(source_path)
        existing = self._normalize_annotation_entries(annotations.get(path, []))
        updated_record: AnnotationRecord | None = None
        updated_entries: list[AnnotationRecord] = []
        for record in existing:
            if record.id == annotation_id:
                updated_record = AnnotationRecord(
                    id=record.id,
                    created_at=record.created_at,
                    updated_at=_annotation_timestamp(),
                    tags=_normalize_annotation_tags(tags),
                    note=note,
                )
                updated_entries.append(updated_record)
            else:
                updated_entries.append(record)
        if updated_record is None:
            return None
        sorted_entries = _sort_annotation_records(updated_entries)
        annotations[path] = [_annotation_payload(entry) for entry in sorted_entries]
        self.annotations_for_file(source_path)[path] = tuple(sorted_entries)
        self._save()
        return updated_record

    def set_annotation(
        self,
        source_path: Path,
        path: str,
        *,
        tags: tuple[str, ...],
        note: str,
    ) -> None:
        """Store one single-entry annotation, replacing existing entries."""
        self._ensure_fresh()
        timestamp = _annotation_timestamp()
        record = AnnotationRecord(
            id=str(uuid4()),
            created_at=timestamp,
            updated_at=timestamp,
            tags=_normalize_annotation_tags(tags),
            note=note,
        )
        _, annotations = self._persisted_annotations_for_file(source_path)
        annotations[path] = [_annotation_payload(record)]
        self.annotations_for_file(source_path)[path] = (record,)
        self._save()

    def delete_annotation(
        self,
        source_path: Path,
        path: str,
        annotation_id: str | None = None,
    ) -> None:
        """Delete one annotation entry by id, or all entries when no id is supplied."""
        self._ensure_fresh()
        _, annotations = self._persisted_annotations_for_file(source_path)
        if annotation_id is None:
            annotations.pop(path, None)
            self.annotations_for_file(source_path).pop(path, None)
            self._save()
            return
        existing = self._normalize_annotation_entries(annotations.get(path, []))
        remaining = [record for record in existing if record.id != annotation_id]
        if remaining:
            sorted_entries = _sort_annotation_records(remaining)
            annotations[path] = [_annotation_payload(entry) for entry in sorted_entries]
            self.annotations_for_file(source_path)[path] = tuple(sorted_entries)
        else:
            annotations.pop(path, None)
            self.annotations_for_file(source_path).pop(path, None)
        self._save()

    def relative_file_path(self, source_path: Path) -> str:
        """Return the normalized file key used in persisted review data."""
        resolved = source_path.resolve()
        try:
            return resolved.relative_to(self.review_root).as_posix()
        except ValueError:
            return resolved.name

    def triage_items(self) -> list[TriageItem]:
        """Return all annotations normalized as triage rows."""
        self._ensure_fresh()
        files = self._payload.get("files", {})
        items: list[TriageItem] = []
        if not isinstance(files, dict):
            return items
        for file_path, file_entry in files.items():
            if not isinstance(file_path, str) or not isinstance(file_entry, dict):
                continue
            annotations = file_entry.get("annotations", {})
            if not isinstance(annotations, dict):
                continue
            for target_path, payload in annotations.items():
                if not isinstance(target_path, str):
                    continue
                target_kind = (
                    FILE_TARGET_KIND
                    if target_path == FILE_ANNOTATION_KEY
                    else JSON_PATH_TARGET_KIND
                )
                target_label = "File" if target_kind == FILE_TARGET_KIND else target_path
                normalized_path = None if target_kind == FILE_TARGET_KIND else target_path
                for record in self._normalize_annotation_entries(payload):
                    items.append(
                        TriageItem(
                            annotation_id=record.id,
                            file_path=file_path,
                            target_kind=target_kind,
                            target_label=target_label,
                            target_path=normalized_path,
                            preview_kind=triage_preview_kind(file_path),
                            tags=record.tags,
                            note_preview=_note_preview(record.note),
                            note_full=record.note,
                            created_at=record.created_at,
                            updated_at=record.updated_at,
                        )
                    )
        return sorted(
            items,
            key=lambda item: (
                -_timestamp_sort_key(item.updated_at),
                item.file_path,
                item.annotation_id,
            ),
        )

    def _load(self) -> dict[str, Any]:
        """Load the persisted annotation payload with safe fallbacks."""
        if not self.path.is_file():
            return {"version": REVIEW_VERSION, "files": {}}
        try:
            payload = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return {"version": REVIEW_VERSION, "files": {}}
        if not isinstance(payload, dict):
            return {"version": REVIEW_VERSION, "files": {}}
        payload.setdefault("version", REVIEW_VERSION)
        payload.setdefault("files", {})
        files = payload.get("files", {})
        if isinstance(files, dict):
            for file_entry in files.values():
                if not isinstance(file_entry, dict):
                    continue
                annotations = file_entry.get("annotations")
                if not isinstance(annotations, dict):
                    file_entry["annotations"] = {}
                    continue
                normalized_annotations: dict[str, list[dict[str, Any]]] = {}
                for path, entry in annotations.items():
                    if not isinstance(path, str):
                        continue
                    records = self._normalize_annotation_entries(entry)
                    normalized_annotations[path] = [
                        _annotation_payload(record) for record in records
                    ]
                file_entry["annotations"] = normalized_annotations
        return payload

    def _build_annotations_for_relative_path(
        self,
        relative_path: str,
    ) -> dict[str, tuple[AnnotationRecord, ...]]:
        """Normalize stored annotations for one file path."""
        files = self._payload.get("files", {})
        file_entry = files.get(relative_path, {})
        annotations = file_entry.get("annotations", {})
        result: dict[str, tuple[AnnotationRecord, ...]] = {}
        for path, payload in annotations.items():
            if not isinstance(path, str):
                continue
            records = self._normalize_annotation_entries(payload)
            if records:
                result[path] = tuple(records)
        return result

    def _persisted_annotations_for_file(
        self,
        source_path: Path,
    ) -> tuple[str, dict[str, Any]]:
        """Return the persisted file key and mutable annotation payload for one source."""
        relative_path = self.relative_file_path(source_path)
        files = self._payload.setdefault("files", {})
        file_entry = files.setdefault(relative_path, {"annotations": {}})
        annotations = file_entry.setdefault("annotations", {})
        return relative_path, annotations

    def _normalize_annotation_entries(self, payload: Any) -> list[AnnotationRecord]:
        """Normalize legacy or list-shaped annotation payloads into sorted records."""
        entries = payload if isinstance(payload, list) else [payload]
        records: list[AnnotationRecord] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            tags = entry.get("tags", [])
            note = entry.get("note", "")
            if not isinstance(tags, list) or not isinstance(note, str):
                continue
            created_at = str(entry.get("created_at") or _annotation_timestamp())
            updated_at = str(entry.get("updated_at") or created_at)
            record_id = str(entry.get("id") or uuid4())
            records.append(
                AnnotationRecord(
                    id=record_id,
                    created_at=created_at,
                    updated_at=updated_at,
                    tags=_normalize_annotation_tags(tags),
                    note=note,
                )
            )
        return _sort_annotation_records(records)

    def _save(self) -> None:
        """Write the annotation payload to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._payload, indent=2, sort_keys=True))
        self._annotation_version = self._compute_annotation_version()

    def _ensure_fresh(self) -> None:
        """Reload the persisted payload when another process changed it on disk."""
        version = self._compute_annotation_version()
        if version == self._annotation_version:
            return
        self._payload = self._load()
        self._file_annotations = {}
        self._annotation_version = version

    def _compute_annotation_version(self) -> str:
        """Return a token that changes whenever the review file changes."""
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return "missing"
        return f"{stat.st_mtime_ns}:{stat.st_size}"


def triage_preview_kind(file_path: str) -> str:
    """Return the triage filter bucket for one relative file path."""
    suffix = Path(file_path).suffix.lower()
    if suffix in MARKDOWN_EXTENSIONS:
        return "markdown"
    if suffix in JSON_EXTENSIONS:
        return "json"
    if suffix in NOTEBOOK_EXTENSIONS:
        return "notebook"
    if suffix in CSV_EXTENSIONS:
        return "csv"
    if suffix in XLSX_EXTENSIONS:
        return "xlsx"
    if suffix in CODE_EXTENSIONS:
        return "code"
    if suffix in TEXT_EXTENSIONS:
        return "text"
    return "other"


def _annotation_timestamp() -> str:
    """Return a UTC timestamp for persisted annotations."""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _normalize_annotation_tags(tags: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Return a stable tuple of non-empty tag strings."""
    result: list[str] = []
    for tag in tags:
        value = str(tag).strip()
        if value:
            result.append(value)
    return tuple(result)


def _annotation_payload(record: AnnotationRecord) -> dict[str, Any]:
    """Return a persisted JSON payload for one annotation record."""
    return {
        "id": record.id,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "tags": list(record.tags),
        "note": record.note,
    }


def _sort_annotation_records(records: list[AnnotationRecord]) -> list[AnnotationRecord]:
    """Return annotations newest-first, then stable by id."""
    return sorted(
        records,
        key=lambda record: (-_timestamp_sort_key(record.updated_at), record.id),
    )


def _timestamp_sort_key(value: str) -> int:
    """Return a comparable integer for ISO timestamps."""
    normalized = str(value).replace("Z", "+00:00")
    try:
        from datetime import datetime

        return int(datetime.fromisoformat(normalized).timestamp() * 1_000_000)
    except ValueError:
        return 0


def _note_preview(note: str, limit: int = 96) -> str:
    """Return a compact one-line preview for a note body."""
    single_line = " ".join(note.split())
    if len(single_line) <= limit:
        return single_line
    return single_line[: limit - 1].rstrip() + "…"
