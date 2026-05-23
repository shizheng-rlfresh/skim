"""Command-line annotation helpers for agents and scripts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .core.annotation_targets import annotatable_paths_from_preview
from .core.filesystem import resolve_browse_path
from .core.review import FILE_ANNOTATION_KEY, AnnotationRecord, AnnotationStore, TriageItem
from .webui.preview_serializer import serialize_preview


def main(argv: list[str] | None = None) -> int:
    """Run the ``skim annotate`` command family."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        payload = _run(args)
    except _CliError as error:
        _write_error(error.message, json_output=getattr(args, "json", False))
        return error.status

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _write_text(payload, args.command)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skim annotate", description="Manage skim annotations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", help="list annotatable targets for a file")
    _add_common_options(inspect)
    inspect.add_argument("--file", required=True, help="File path relative to the workspace root")

    add = subparsers.add_parser("add", help="create an annotation")
    _add_common_options(add)
    add.add_argument("--file", required=True, help="File path relative to the workspace root")
    add.add_argument("--path", required=True, help="Annotation target path, or @file")
    add.add_argument("--note", required=True, help="Annotation note")
    add.add_argument("--tag", action="append", default=None, help="Annotation tag; repeatable")

    list_parser = subparsers.add_parser("list", help="list annotations")
    _add_common_options(list_parser)
    list_parser.add_argument("--file", help="Optional file path relative to the workspace root")

    update = subparsers.add_parser("update", help="update an annotation")
    _add_common_options(update)
    update.add_argument("--file", required=True, help="File path relative to the workspace root")
    update.add_argument("--path", required=True, help="Annotation target path, or @file")
    update.add_argument("--id", required=True, help="Annotation id")
    update.add_argument("--note", help="Replacement note")
    update.add_argument("--tag", action="append", default=None, help="Replacement tag; repeatable")

    delete = subparsers.add_parser("delete", help="delete an annotation")
    _add_common_options(delete)
    delete.add_argument("--file", required=True, help="File path relative to the workspace root")
    delete.add_argument("--path", required=True, help="Annotation target path, or @file")
    delete.add_argument("--id", required=True, help="Annotation id")
    return parser


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=".", help="Workspace root; defaults to current directory")
    parser.add_argument("--json", action="store_true", help="Write machine-readable JSON")


def _run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise _CliError(f"root is not a directory: {root}")
    store = AnnotationStore(root)

    if args.command == "inspect":
        return _inspect(root, store, args.file)
    if args.command == "add":
        source = _resolve_existing_file(root, args.file)
        _ensure_annotatable_path(root, store, source, args.path)
        annotation = store.add_annotation(
            source,
            args.path,
            tags=tuple(args.tag or ()),
            note=args.note,
        )
        return {"ok": True, "annotation": _annotation_payload(annotation, args.file, args.path)}
    if args.command == "list":
        return _list_annotations(root, store, args.file)
    if args.command == "update":
        if args.note is None and args.tag is None:
            raise _CliError("update requires --note or --tag")
        source = _resolve_existing_file(root, args.file)
        _ensure_annotatable_path(root, store, source, args.path)
        existing = store.annotations_for_path(source, args.path)
        current = next((record for record in existing if record.id == args.id), None)
        if current is None:
            raise _CliError("annotation not found", status=1)
        annotation = store.update_annotation(
            source,
            args.path,
            args.id,
            tags=tuple(args.tag) if args.tag is not None else current.tags,
            note=args.note if args.note is not None else current.note,
        )
        if annotation is None:
            raise _CliError("annotation not found", status=1)
        return {"ok": True, "annotation": _annotation_payload(annotation, args.file, args.path)}
    if args.command == "delete":
        source = _resolve_existing_file(root, args.file)
        _ensure_annotatable_path(root, store, source, args.path)
        existing = store.annotations_for_path(source, args.path)
        if not any(record.id == args.id for record in existing):
            raise _CliError("annotation not found", status=1)
        store.delete_annotation(source, args.path, args.id)
        return {"ok": True, "deleted": {"id": args.id, "file": args.file, "path": args.path}}
    raise _CliError(f"unknown command: {args.command}")


def _inspect(root: Path, store: AnnotationStore, file_path: str) -> dict[str, Any]:
    source = _resolve_existing_file(root, file_path)
    preview = serialize_preview(source, browse_root=root, annotation_store=store)
    kind = str(preview.get("kind", ""))
    if kind in {"json_inspector", "trajectory"}:
        targets = _inspect_structured_preview(preview)
    else:
        annotations = store.annotations_for_path(source, FILE_ANNOTATION_KEY)
        targets = [
            {
                "path": FILE_ANNOTATION_KEY,
                "label": "File",
                "kind": "file",
                "annotation_count": len(annotations),
                "preview": _file_preview_text(preview),
            }
        ]
    return {"file": file_path, "kind": kind, "targets": targets}


def _inspect_structured_preview(preview: dict[str, Any]) -> list[dict[str, Any]]:
    if preview.get("kind") == "json_inspector":
        targets: list[dict[str, Any]] = []
        for node in preview.get("tree", []):
            if isinstance(node, dict):
                _collect_json_targets(node, targets)
        return targets
    if preview.get("kind") == "trajectory":
        return _trajectory_targets(preview)
    return []


def _ensure_annotatable_path(
    root: Path,
    store: AnnotationStore,
    source: Path,
    path: str,
) -> None:
    if path not in _allowed_annotation_paths(root, store, source):
        raise _CliError("path is not an annotatable target")


def _allowed_annotation_paths(root: Path, store: AnnotationStore, source: Path) -> set[str]:
    preview = serialize_preview(source, browse_root=root, annotation_store=store)
    return annotatable_paths_from_preview(preview)


def _collect_json_targets(node: dict[str, Any], targets: list[dict[str, Any]]) -> None:
    if node.get("annotatable") and isinstance(node.get("annotation_path"), str):
        targets.append(
            {
                "path": node["annotation_path"],
                "label": str(node.get("display_key") or node.get("title") or node.get("label")),
                "kind": str(node.get("kind") or "json"),
                "annotation_count": int(node.get("annotation_count") or 0),
                "preview": _node_preview(node),
            }
        )
    for child in node.get("children", []):
        if isinstance(child, dict):
            _collect_json_targets(child, targets)


def _trajectory_targets(preview: dict[str, Any]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for step in preview.get("steps", []):
        if not isinstance(step, dict):
            continue
        for item in step.get("items", []):
            if not isinstance(item, dict) or not isinstance(item.get("annotation_path"), str):
                continue
            targets.append(
                {
                    "path": item["annotation_path"],
                    "label": str(item.get("title") or item.get("kind") or "Target"),
                    "kind": str(item.get("kind") or "trajectory"),
                    "annotation_count": int(item.get("annotation_count") or 0),
                    "preview": _trajectory_item_preview(item),
                }
            )
            for nested_key in ("input", "output"):
                nested = item.get(nested_key)
                if not isinstance(nested, dict) or not isinstance(
                    nested.get("annotation_path"), str
                ):
                    continue
                targets.append(
                    {
                        "path": nested["annotation_path"],
                        "label": f"{item.get('title') or item.get('kind')} {nested_key}".strip(),
                        "kind": f"{item.get('kind') or 'trajectory'}_{nested_key}",
                        "annotation_count": int(nested.get("annotation_count") or 0),
                        "preview": _render_preview(nested.get("render")),
                    }
                )
    return targets


def _list_annotations(
    root: Path,
    store: AnnotationStore,
    file_path: str | None,
) -> dict[str, Any]:
    if file_path is not None:
        source = _resolve_file_target(root, file_path)
        relative_path = store.relative_file_path(source)
        items = [item for item in store.triage_items() if item.file_path == relative_path]
        return {"file": relative_path, "items": [_item_payload(item) for item in items]}
    return {
        "root": str(root),
        "annotation_version": store.annotation_version,
        "items": [_item_payload(item) for item in store.triage_items()],
    }


def _resolve_existing_file(root: Path, file_path: str) -> Path:
    source = _resolve_file_target(root, file_path)
    if not source.is_file():
        raise _CliError("file not found", status=1)
    return source


def _resolve_file_target(root: Path, file_path: str) -> Path:
    source = resolve_browse_path(root, file_path)
    if source is None:
        raise _CliError("file is outside root")
    return source


def _annotation_payload(record: AnnotationRecord, file_path: str, path: str) -> dict[str, Any]:
    return {
        "id": record.id,
        "file": file_path,
        "path": path,
        "tags": list(record.tags),
        "note": record.note,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _item_payload(item: TriageItem) -> dict[str, Any]:
    return {
        "id": item.annotation_id,
        "file": item.file_path,
        "path": FILE_ANNOTATION_KEY if item.target_path is None else item.target_path,
        "target_kind": item.target_kind,
        "tags": list(item.tags),
        "note": item.note_full,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _node_preview(node: dict[str, Any]) -> str:
    display_value = node.get("display_value")
    if isinstance(display_value, str) and display_value:
        return display_value
    return _detail_preview(node.get("detail")) or str(node.get("label") or "")


def _detail_preview(detail: Any) -> str:
    if not isinstance(detail, dict):
        return ""
    blocks = detail.get("blocks")
    if not isinstance(blocks, list):
        return ""
    for block in blocks:
        if isinstance(block, dict):
            text = _block_preview(block)
            if text:
                return text
    return ""


def _block_preview(block: dict[str, Any]) -> str:
    if isinstance(block.get("value"), str):
        return _one_line(block["value"])
    fields = block.get("fields")
    if isinstance(fields, dict) and fields:
        key, value = next(iter(fields.items()))
        return _one_line(f"{key}: {value}")
    if isinstance(fields, list) and fields:
        first = fields[0]
        if isinstance(first, dict):
            return _one_line(", ".join(f"{key}: {value}" for key, value in first.items()))
    return ""


def _trajectory_item_preview(item: dict[str, Any]) -> str:
    for key in ("render", "summary"):
        text = _render_preview(item.get(key))
        if text:
            return text
    return str(item.get("title") or "")


def _render_preview(render: Any) -> str:
    if isinstance(render, dict):
        if isinstance(render.get("value"), str):
            return _one_line(render["value"])
        if isinstance(render.get("text"), str):
            return _one_line(render["text"])
    if isinstance(render, str):
        return _one_line(render)
    return ""


def _file_preview_text(preview: dict[str, Any]) -> str:
    for key in ("content", "raw"):
        if isinstance(preview.get(key), str):
            return _first_nonempty_line(preview[key])
    render = preview.get("render")
    if isinstance(render, dict) and isinstance(render.get("value"), str):
        return _first_nonempty_line(render["value"])
    return str(preview.get("name") or preview.get("path") or "")


def _first_nonempty_line(value: str) -> str:
    for line in value.splitlines():
        text = line.strip()
        if text:
            return _one_line(text)
    return ""


def _one_line(value: str, *, limit: int = 160) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _write_error(message: str, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps({"error": message}, sort_keys=True), file=sys.stderr)
    else:
        print(f"error: {message}", file=sys.stderr)


def _write_text(payload: dict[str, Any], command: str) -> None:
    if command == "list":
        items = payload.get("items", [])
        if not items:
            print("No annotations.")
            return
        for item in items:
            print(f"{item['id']} {item['file']} {item['path']} :: {item['note']}")
        return
    if command == "inspect":
        targets = payload.get("targets", [])
        for target in targets:
            print(f"{target['path']} {target['label']} ({target['kind']})")
        return
    if "annotation" in payload:
        annotation = payload["annotation"]
        print(f"Saved annotation {annotation['id']} on {annotation['file']} {annotation['path']}")
        return
    if "deleted" in payload:
        deleted = payload["deleted"]
        print(f"Deleted annotation {deleted['id']} from {deleted['file']} {deleted['path']}")


class _CliError(Exception):
    """Expected command-line validation error."""

    def __init__(self, message: str, *, status: int = 2) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
