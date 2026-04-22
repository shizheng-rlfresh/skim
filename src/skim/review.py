"""Compatibility exports for the shared review module."""

from .core.previewing import (
    CODE_EXTENSIONS,
    CSV_EXTENSIONS,
    JSON_EXTENSIONS,
    MARKDOWN_EXTENSIONS,
    NOTEBOOK_EXTENSIONS,
    TEXT_EXTENSIONS,
    XLSX_EXTENSIONS,
)
from .core.review import (
    FILE_ANNOTATION_KEY,
    FILE_TARGET_KIND,
    JSON_PATH_TARGET_KIND,
    REVIEW_VERSION,
    AnnotationRecord,
    AnnotationStore,
    TriageItem,
    triage_preview_kind,
)

__all__ = [
    "AnnotationRecord",
    "AnnotationStore",
    "CODE_EXTENSIONS",
    "CSV_EXTENSIONS",
    "FILE_ANNOTATION_KEY",
    "FILE_TARGET_KIND",
    "JSON_EXTENSIONS",
    "JSON_PATH_TARGET_KIND",
    "MARKDOWN_EXTENSIONS",
    "NOTEBOOK_EXTENSIONS",
    "REVIEW_VERSION",
    "TEXT_EXTENSIONS",
    "TriageItem",
    "XLSX_EXTENSIONS",
    "triage_preview_kind",
]
