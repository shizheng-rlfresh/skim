"""Shared annotation target eligibility rules."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

RawPath = Sequence[str | int]


def is_ui_aligned_annotation_target(
    raw_path: RawPath,
    *,
    synthetic: bool,
    annotation_path: RawPath | None,
) -> bool:
    """Return whether a JSON inspector item can be annotated by any surface."""
    if annotation_path is not None:
        return True
    if synthetic:
        return False
    return not is_trajectory_event_payload_descendant(raw_path)


def is_trajectory_event_payload_descendant(raw_path: RawPath) -> bool:
    """Return whether a path points below a trajectory event item."""
    for index in range(len(raw_path) - 3):
        if (
            raw_path[index] == "steps"
            and isinstance(raw_path[index + 1], int)
            and raw_path[index + 2] == "output"
            and isinstance(raw_path[index + 3], int)
        ):
            return len(raw_path) > index + 4
    return False


def annotatable_paths_from_preview(preview: dict[str, Any]) -> set[str]:
    """Return persisted annotation paths exposed by a serialized preview."""
    paths: set[str] = set()
    if preview.get("kind") == "json_inspector":
        for node in preview.get("tree", []):
            if isinstance(node, dict):
                _collect_json_inspector_paths(node, paths)
        return paths

    if preview.get("kind") == "trajectory":
        for step in preview.get("steps", []):
            if not isinstance(step, dict):
                continue
            for item in step.get("items", []):
                if isinstance(item, dict):
                    _collect_trajectory_item_paths(item, paths)
        return paths

    annotation_path = preview.get("annotation_path")
    if preview.get("annotatable") and isinstance(annotation_path, str):
        paths.add(annotation_path)
    return paths


def _collect_json_inspector_paths(node: dict[str, Any], paths: set[str]) -> None:
    annotation_path = node.get("annotation_path")
    if node.get("annotatable") and isinstance(annotation_path, str):
        paths.add(annotation_path)
    for child in node.get("children", []):
        if isinstance(child, dict):
            _collect_json_inspector_paths(child, paths)


def _collect_trajectory_item_paths(item: dict[str, Any], paths: set[str]) -> None:
    annotation_path = item.get("annotation_path")
    if isinstance(annotation_path, str):
        paths.add(annotation_path)
    for nested_key in ("input", "output"):
        nested = item.get(nested_key)
        if not isinstance(nested, dict):
            continue
        nested_path = nested.get("annotation_path")
        if isinstance(nested_path, str):
            paths.add(nested_path)
