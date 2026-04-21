"""Tests for skim's shared review storage and triage helpers."""

from __future__ import annotations

import json

from skim.review import (
    FILE_ANNOTATION_KEY,
    AnnotationStore,
    triage_preview_kind,
)


def test_annotation_store_supports_file_level_annotation_round_trip(tmp_path):
    """File-level annotations should persist under the reserved @file target key."""
    source = tmp_path / "notes.md"
    source.write_text("# Note\n")
    store = AnnotationStore(tmp_path)

    created = store.add_annotation(
        source,
        FILE_ANNOTATION_KEY,
        tags=("important", "follow-up"),
        note="Review the rollout wording.",
    )

    persisted = json.loads((tmp_path / ".skim" / "review.json").read_text())
    saved = persisted["files"]["notes.md"]["annotations"][FILE_ANNOTATION_KEY]

    assert len(saved) == 1
    assert saved[0]["id"] == created.id
    assert saved[0]["tags"] == ["important", "follow-up"]
    assert store.get_annotation(source, FILE_ANNOTATION_KEY) is not None
    assert store.get_annotation(source, FILE_ANNOTATION_KEY).note == "Review the rollout wording."


def test_annotation_store_supports_multiple_file_level_annotations_by_id(tmp_path):
    """File-level annotations should support multi-entry update/delete like JSON nodes."""
    source = tmp_path / "notes.md"
    source.write_text("# Note\n")
    store = AnnotationStore(tmp_path)

    first = store.add_annotation(
        source,
        FILE_ANNOTATION_KEY,
        tags=("important",),
        note="Older file note.",
    )
    second = store.add_annotation(
        source,
        FILE_ANNOTATION_KEY,
        tags=("follow-up",),
        note="Newest file note.",
    )

    records = store.annotations_for_path(source, FILE_ANNOTATION_KEY)
    assert [record.id for record in records] == [second.id, first.id]

    updated = store.update_annotation(
        source,
        FILE_ANNOTATION_KEY,
        first.id,
        tags=("important", "edited"),
        note="Older file note updated.",
    )
    assert updated is not None

    after_update = store.annotations_for_path(source, FILE_ANNOTATION_KEY)
    assert after_update[0].id == updated.id
    assert after_update[0].note == "Older file note updated."

    store.delete_annotation(source, FILE_ANNOTATION_KEY, second.id)
    after_delete = store.annotations_for_path(source, FILE_ANNOTATION_KEY)
    assert [record.id for record in after_delete] == [updated.id]


def test_triage_items_normalize_and_sort_workspace_annotations(tmp_path):
    """Triage rows should flatten per-file annotations into a stable review queue."""
    review_file = tmp_path / ".skim" / "review.json"
    review_file.parent.mkdir()
    review_file.write_text(
        json.dumps(
            {
                "version": 1,
                "files": {
                    "docs/spec.md": {
                        "annotations": {
                            FILE_ANNOTATION_KEY: [
                                {
                                    "id": "file-ann",
                                    "created_at": "2026-04-21T14:20:00Z",
                                    "updated_at": "2026-04-21T14:25:00Z",
                                    "tags": ["important"],
                                    "note": (
                                        "Need to revisit rollout wording and clarify "
                                        "stop conditions."
                                    ),
                                }
                            ]
                        }
                    },
                    "output.json": {
                        "annotations": {
                            "$.task": [
                                {
                                    "id": "json-ann",
                                    "created_at": "2026-04-21T14:10:00Z",
                                    "updated_at": "2026-04-21T14:15:00Z",
                                    "tags": ["bug"],
                                    "note": "The task node needs a better summary.",
                                }
                            ]
                        }
                    },
                },
            }
        )
    )

    items = AnnotationStore(tmp_path).triage_items()

    assert [item.annotation_id for item in items] == ["file-ann", "json-ann"]
    assert items[0].file_path == "docs/spec.md"
    assert items[0].target_kind == "file"
    assert items[0].target_label == "File"
    assert items[0].target_path is None
    assert items[0].preview_kind == "markdown"
    assert items[0].note_preview.startswith("Need to revisit rollout wording")
    assert items[1].target_kind == "json_path"
    assert items[1].target_label == "$.task"
    assert items[1].target_path == "$.task"
    assert items[1].preview_kind == "json"


def test_annotation_store_reloads_when_review_file_changes_on_disk(tmp_path):
    """Long-lived stores should invalidate caches when another process edits review.json."""
    source = tmp_path / "plain.json"
    source.write_text(json.dumps({"hello": "world"}))
    first = AnnotationStore(tmp_path)
    second = AnnotationStore(tmp_path)

    created = second.add_annotation(
        source,
        "$.hello",
        tags=("external",),
        note="Saved from another surface.",
    )

    annotation = first.get_annotation(source, "$.hello")

    assert annotation is not None
    assert annotation.id == created.id
    assert annotation.note == "Saved from another surface."


def test_triage_preview_kind_uses_shared_bucket_mapping():
    """Triage filter buckets should be derived from local file kinds in Python."""
    assert triage_preview_kind("docs/spec.md") == "markdown"
    assert triage_preview_kind("output.json") == "json"
    assert triage_preview_kind("notebook.ipynb") == "notebook"
    assert triage_preview_kind("table.csv") == "csv"
    assert triage_preview_kind("workbook.xlsx") == "xlsx"
    assert triage_preview_kind("src/app.py") == "code"
    assert triage_preview_kind("README") == "text"
    assert triage_preview_kind("artifact.foo") == "other"
