"""Web-preview serialization for skim's localhost browser UI.

This module reuses the existing preview and trajectory logic to classify local
files and emit plain JSON payloads that a thin browser client can render
without a frontend framework.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from .preview import (
    JSON_EXTENSIONS,
    MARKDOWN_EXTENSIONS,
    MAX_CSV_COLS,
    MAX_CSV_ROWS,
    MAX_FILE_SIZE,
    MAX_JSON_FILE_SIZE,
    NOTEBOOK_EXTENSIONS,
    SYNTAX_MAP,
    _clip_csv_cell,
    _parse_csv,
)
from .trajectory import (
    AnnotationRecord,
    AnnotationStore,
    JsonInspectorItem,
    _bundle_summary,
    _decode_nested_json,
    _decoded_tool_result,
    _display_label,
    _event_payload,
    _event_text,
    _format_raw_path,
    _guess_code_lexer,
    _has_human_text,
    _hermes_summary,
    _interaction_payload,
    _interaction_status,
    _is_empty_value,
    _is_scalar_metadata,
    _json_tree_label,
    _json_type_name,
    _looks_like_bundle,
    _looks_like_hermes,
    _looks_like_markdown,
    _looks_like_preformatted_text,
    _looks_like_submission,
    _message_role,
    _metadata_header,
    _metadata_lines,
    _overlay_trajectory_target,
    _promote_wrapper_value,
    _section_collapsed,
    _status_value,
    _submission_summary_payload,
    _trajectory_event_paths,
    _try_decode_json,
    extract_trajectory,
    normalize_step_overlay,
)


def serialize_preview(
    path: Path,
    *,
    browse_root: Path | None = None,
    annotation_store: AnnotationStore | None = None,
) -> dict[str, Any]:
    """Return a browser-friendly preview payload for one local file."""
    resolved = path.resolve()
    root = (browse_root or resolved.parent).resolve()
    relative_path = _relative_path(resolved, root)

    if not resolved.is_file():
        return {
            "kind": "error",
            "name": resolved.name,
            "path": relative_path,
            "message": f"Not a file: {resolved.name}",
        }

    suffix = resolved.suffix.lower()
    size = resolved.stat().st_size
    max_size = (
        MAX_JSON_FILE_SIZE
        if suffix in JSON_EXTENSIONS or suffix in NOTEBOOK_EXTENSIONS
        else MAX_FILE_SIZE
    )
    if size > max_size:
        return {
            "kind": "too_large",
            "name": resolved.name,
            "path": relative_path,
            "message": f"{resolved.name} is too large ({size:,} bytes)",
        }

    try:
        content = resolved.read_text(errors="replace")
    except OSError as error:
        return {
            "kind": "error",
            "name": resolved.name,
            "path": relative_path,
            "message": f"Could not read {resolved.name}: {error}",
        }

    if suffix in MARKDOWN_EXTENSIONS:
        return {
            "kind": "markdown",
            "name": resolved.name,
            "path": relative_path,
            "content": content,
        }

    if suffix in JSON_EXTENSIONS:
        return _serialize_json_file(
            content,
            source_path=resolved,
            review_root=root,
            annotation_store=annotation_store,
            relative_path=relative_path,
        )

    if suffix == ".csv":
        return _serialize_csv_preview(
            content,
            name=resolved.name,
            relative_path=relative_path,
        )

    return _text_payload(
        resolved.name,
        relative_path,
        content,
        language=SYNTAX_MAP.get(suffix),
    )


def _serialize_json_file(
    content: str,
    *,
    source_path: Path,
    review_root: Path,
    annotation_store: AnnotationStore | None,
    relative_path: str,
) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return _text_payload(
            source_path.name,
            relative_path,
            content,
            language="json",
        )

    store = annotation_store or AnnotationStore(review_root)
    if _is_bare_trajectory_object(parsed):
        trajectory_payload = serialize_trajectory_preview(
            parsed,
            source_path=source_path,
            review_root=review_root,
            annotation_store=store,
        )
        if trajectory_payload is not None:
            trajectory_payload["name"] = source_path.name
            trajectory_payload["path"] = relative_path
            return trajectory_payload

    return serialize_json_inspector_preview(
        parsed,
        source_path=source_path,
        review_root=review_root,
        annotation_store=store,
        relative_path=relative_path,
    )


def serialize_json_inspector_preview(
    data: Any,
    *,
    source_path: Path,
    review_root: Path,
    annotation_store: AnnotationStore | None = None,
    relative_path: str | None = None,
) -> dict[str, Any]:
    """Return a unified JSON-inspector payload for the browser client."""
    serializer = _JsonInspectorSerializer(
        data,
        source_path=source_path,
        review_root=review_root,
        annotation_store=annotation_store,
    )
    payload = serializer.build()
    payload.update(
        {
            "kind": "json_inspector",
            "name": source_path.name,
            "path": relative_path or _relative_path(source_path.resolve(), review_root.resolve()),
        }
    )
    return payload


def serialize_trajectory_preview(
    data: Any,
    *,
    source_path: Path,
    review_root: Path,
    annotation_store: AnnotationStore | None = None,
) -> dict[str, Any] | None:
    """Return a specialized trajectory preview payload, if the JSON supports it."""
    trajectory = extract_trajectory(data)
    if trajectory is None:
        return None

    store = annotation_store or AnnotationStore(review_root)
    file_annotations = store.annotations_for_file(source_path.resolve())
    resolved_trajectory, base_path = _overlay_trajectory_target(data, data, ())
    if resolved_trajectory is None:
        return None

    step_events, step_items = normalize_step_overlay(resolved_trajectory)
    raw_steps = (
        resolved_trajectory.get("steps", [])
        if isinstance(resolved_trajectory.get("steps"), list)
        else []
    )

    steps: list[dict[str, Any]] = []
    for step_index, (items, events) in enumerate(zip(step_items, step_events, strict=False)):
        step_path = base_path + ("steps", step_index)
        event_paths = _trajectory_event_paths(base_path, step_index, events)
        blocks: list[dict[str, Any]] = []
        for row_index, item in enumerate(items):
            block_id = f"step-{step_index}-item-{row_index}"
            if item.interaction is not None:
                interaction = item.interaction
                call_event = interaction.call_event
                result_event = interaction.result_event
                call_path = event_paths.get(id(call_event.raw)) if call_event is not None else None
                result_path = (
                    event_paths.get(id(result_event.raw)) if result_event is not None else None
                )
                parent_path = call_path or result_path or step_path
                blocks.append(
                    {
                        "id": block_id,
                        "kind": "tool",
                        "title": item.title.plain,
                        "annotation_path": _format_path(parent_path),
                        "annotation": _annotation_payload_for_path(
                            file_annotations,
                            parent_path,
                        ),
                        "tool_name": interaction.tool_name,
                        "call_id": interaction.call_id,
                        "status": _interaction_status(interaction),
                        "summary": _interaction_payload(interaction),
                        "input": {
                            "annotation_path": _format_path(call_path or parent_path),
                            "annotation": _annotation_payload_for_path(
                                file_annotations,
                                call_path or parent_path,
                            ),
                            "render": _render_value(
                                _decoded_tool_result(call_event.raw.get("arguments"))
                                if call_event is not None
                                else None,
                                key="arguments",
                            ),
                        },
                        "output": {
                            "annotation_path": _format_path(result_path or parent_path),
                            "annotation": _annotation_payload_for_path(
                                file_annotations,
                                result_path or parent_path,
                            ),
                            "render": _render_value(
                                _decoded_tool_result(result_event.raw.get("output"))
                                if result_event is not None
                                else None,
                                key="output",
                            ),
                        },
                    }
                )
                continue

            if item.event is None:
                continue

            event = item.event
            event_path = event_paths.get(id(event.raw)) or step_path
            render_value = _event_text(event.raw) or _event_payload(event.raw)
            blocks.append(
                {
                    "id": block_id,
                    "kind": "event",
                    "title": item.title.plain,
                    "annotation_path": _format_path(event_path),
                    "annotation": _annotation_payload_for_path(file_annotations, event_path),
                    "event_kind": event.kind,
                    "excerpt": event.excerpt,
                    "role": _message_role(event.raw) if event.kind == "message" else None,
                    "status": _status_value(event.raw),
                    "render": _render_value(render_value, key="content"),
                }
            )

        steps.append(
            {
                "id": f"step-{step_index}",
                "title": f"Step {step_index + 1}",
                "path": _format_path(step_path),
                "summary": f"{len(blocks)} item{'s' if len(blocks) != 1 else ''}",
                "raw_step": raw_steps[step_index] if step_index < len(raw_steps) else None,
                "items": blocks,
            }
        )

    initial_step_id = steps[0]["id"] if steps else None
    return {
        "kind": "trajectory",
        "header": _metadata_header(resolved_trajectory),
        "metadata_lines": _metadata_lines(resolved_trajectory),
        "final_output": _render_value(resolved_trajectory.get("final_output"), key="final_output"),
        "steps": steps,
        "initial_step_id": initial_step_id,
    }


@dataclass
class _JsonInspectorSerializer:
    """Build a JSON-inspector tree payload for the browser client."""

    data: Any
    source_path: Path
    review_root: Path
    annotation_store: AnnotationStore | None = None

    def __post_init__(self) -> None:
        self.source_path = self.source_path.resolve()
        self.review_root = self.review_root.resolve()
        self._store = self.annotation_store or AnnotationStore(self.review_root)
        self._file_annotations = self._store.annotations_for_file(self.source_path)
        self._next_id = 0

    def build(self) -> dict[str, Any]:
        """Return the payload tree plus its initial selection."""
        tree: list[dict[str, Any]] = []
        self._add_overlay_children(tree, self.data, ())
        self._add_raw_children(tree, self.data, ())
        return {
            "root_data": self.data,
            "tree": tree,
            "initial_node_id": tree[0]["id"] if tree else None,
        }

    def _make_node(
        self,
        item: JsonInspectorItem,
        *,
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        node_id = f"node-{self._next_id}"
        self._next_id += 1
        annotation_path = self._annotation_key(item)
        annotation = self._annotation_for_path(annotation_path)
        payload: dict[str, Any] = {
            "id": node_id,
            "title": item.title,
            "label": _json_tree_label(self.data, item).plain,
            "kind": item.kind,
            "path": annotation_path or _format_raw_path(item.raw_path),
            "raw_path": list(item.raw_path),
            "annotatable": annotation_path is not None,
            "annotation_path": annotation_path,
            "annotation": annotation,
            "style": _node_style(item.kind),
            "type_name": _json_type_name(item.raw_value),
            "key": item.key,
            "children": children or [],
            "detail": _detail_payload_for_item(item),
        }
        if item.synthetic:
            detail_value = item.detail if item.detail is not None else item.raw_value
            payload["render"] = _render_value(detail_value, key=item.key)
        return payload

    def _add_overlay_children(
        self,
        parent_children: list[dict[str, Any]],
        value: Any,
        raw_path: tuple[str | int, ...],
    ) -> None:
        if raw_path == () and _looks_like_bundle(value):
            item = JsonInspectorItem(
                kind="bundle_summary",
                title="Bundle Summary",
                raw_path=raw_path,
                raw_value=value,
                detail=_bundle_summary(value),
                synthetic=True,
            )
            parent_children.append(self._make_node(item))
            return

        if raw_path == () and _looks_like_submission(value):
            item = JsonInspectorItem(
                kind="submission_summary",
                title="Submission Summary",
                raw_path=raw_path,
                raw_value=value,
                detail=_submission_summary_payload(value),
                synthetic=True,
            )
            parent_children.append(self._make_node(item))
            return

        if raw_path == () and _looks_like_hermes(value):
            item = JsonInspectorItem(
                kind="transcript_summary",
                title="Transcript Summary",
                raw_path=raw_path,
                raw_value=value,
                detail=_hermes_summary(value),
                synthetic=True,
            )
            parent_children.append(self._make_node(item))
            return

        trajectory, base_path = _web_overlay_trajectory_target(self.data, value, raw_path)
        if trajectory is not None:
            self._add_trajectory_overlay(parent_children, trajectory, base_path)

    def _add_trajectory_overlay(
        self,
        parent_children: list[dict[str, Any]],
        trajectory: dict[str, Any],
        base_path: tuple[str | int, ...],
    ) -> None:
        metadata_item = JsonInspectorItem(
            kind="trajectory_metadata",
            title="Metadata",
            raw_path=base_path + ("metadata",),
            raw_value=trajectory.get("metadata"),
            synthetic=True,
        )
        parent_children.append(self._make_node(metadata_item))

        final_output_item = JsonInspectorItem(
            kind="trajectory_final_output",
            title="Final Output",
            raw_path=base_path + ("final_output",),
            raw_value=trajectory.get("final_output"),
            synthetic=True,
        )
        parent_children.append(self._make_node(final_output_item))

        step_events, step_items = normalize_step_overlay(trajectory)
        steps = trajectory.get("steps", []) if isinstance(trajectory.get("steps"), list) else []
        for step_index, (items, events) in enumerate(zip(step_items, step_events, strict=False)):
            step_path = base_path + ("steps", step_index)
            step_raw_value = steps[step_index] if step_index < len(steps) else None
            event_paths = _trajectory_event_paths(base_path, step_index, events)
            children: list[dict[str, Any]] = []
            step_item = JsonInspectorItem(
                kind="trajectory_step",
                title=f"Step {step_index + 1}",
                raw_path=step_path,
                raw_value=step_raw_value,
                synthetic=True,
            )

            for item in items:
                if item.interaction is not None:
                    interaction = item.interaction
                    call_event = interaction.call_event
                    result_event = interaction.result_event
                    call_path = (
                        event_paths.get(id(call_event.raw)) if call_event is not None else None
                    )
                    result_path = (
                        event_paths.get(id(result_event.raw)) if result_event is not None else None
                    )
                    parent_path = call_path or result_path or step_path
                    tool_children: list[dict[str, Any]] = []
                    tool_item = JsonInspectorItem(
                        kind="trajectory_tool",
                        title=item.title.plain,
                        raw_path=parent_path,
                        raw_value=_interaction_payload(interaction),
                        synthetic=True,
                        annotation_path=parent_path,
                    )
                    input_item = JsonInspectorItem(
                        kind="trajectory_tool_input",
                        title="Input",
                        raw_path=call_path or parent_path,
                        raw_value=call_event.raw if call_event is not None else None,
                        synthetic=True,
                        annotation_path=call_path or parent_path,
                    )
                    output_item = JsonInspectorItem(
                        kind="trajectory_tool_output",
                        title="Output",
                        raw_path=result_path or parent_path,
                        raw_value=result_event.raw if result_event is not None else None,
                        synthetic=True,
                        annotation_path=result_path or parent_path,
                    )
                    tool_children.append(self._make_node(input_item))
                    tool_children.append(self._make_node(output_item))
                    children.append(self._make_node(tool_item, children=tool_children))
                    continue

                if item.event is None:
                    continue

                event_path = event_paths.get(id(item.event.raw))
                event_item = JsonInspectorItem(
                    kind="trajectory_event",
                    title=item.title.plain,
                    raw_path=event_path or step_path,
                    raw_value=item.event.raw,
                    synthetic=True,
                    annotation_path=event_path or step_path,
                )
                children.append(self._make_node(event_item))

            parent_children.append(self._make_node(step_item, children=children))

    def _add_raw_children(
        self,
        parent_children: list[dict[str, Any]],
        value: Any,
        raw_path: tuple[str | int, ...],
    ) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = raw_path + (key,)
                item = JsonInspectorItem(
                    kind="raw_dict_key",
                    title=key,
                    raw_path=child_path,
                    raw_value=child,
                    key=key,
                )
                children: list[dict[str, Any]] = []
                if isinstance(child, dict | list):
                    self._add_overlay_children(children, child, child_path)
                    self._add_raw_children(children, child, child_path)
                parent_children.append(self._make_node(item, children=children))
            return

        if isinstance(value, list):
            for index, child in enumerate(value):
                child_path = raw_path + (index,)
                item = JsonInspectorItem(
                    kind="raw_list_item",
                    title=f"[{index}]",
                    raw_path=child_path,
                    raw_value=child,
                    key=str(index),
                )
                children: list[dict[str, Any]] = []
                if isinstance(child, dict | list):
                    self._add_overlay_children(children, child, child_path)
                    self._add_raw_children(children, child, child_path)
                parent_children.append(self._make_node(item, children=children))

    def _annotation_key(self, item: JsonInspectorItem) -> str | None:
        if item.annotation_path is not None:
            return _format_raw_path(item.annotation_path)
        if item.synthetic:
            return None
        return _format_raw_path(item.raw_path)

    def _annotation_for_path(self, path: str | None) -> dict[str, Any] | None:
        if path is None:
            return None
        record = self._file_annotations.get(path)
        return _annotation_payload(record)


def _serialize_csv_preview(content: str, *, name: str, relative_path: str) -> dict[str, Any]:
    parsed = _parse_csv(content)
    if isinstance(parsed, str):
        return {
            "kind": "csv",
            "name": name,
            "path": relative_path,
            "columns": [],
            "rows": [],
            "raw": content,
            "parse_error": parsed,
            "summary": "CSV parse error",
        }

    if not parsed:
        return {
            "kind": "csv",
            "name": name,
            "path": relative_path,
            "columns": [],
            "rows": [],
            "raw": content,
            "summary": "Empty CSV file",
        }

    header = parsed[0]
    body = parsed[1:]
    display_header = [_clip_csv_cell(value) for value in header[:MAX_CSV_COLS]]
    if len(header) > MAX_CSV_COLS:
        display_header.append("...")

    rows: list[list[str]] = []
    for row in body[:MAX_CSV_ROWS]:
        display_row = [
            _clip_csv_cell(row[index] if index < len(row) else "")
            for index in range(len(header[:MAX_CSV_COLS]))
        ]
        if len(header) > MAX_CSV_COLS:
            overflow = row[MAX_CSV_COLS:]
            display_row.append(_clip_csv_cell(" | ".join(overflow)))
        rows.append(display_row)

    return {
        "kind": "csv",
        "name": name,
        "path": relative_path,
        "columns": display_header,
        "rows": rows,
        "raw": content,
        "raw_render": _syntax_payload(content, language="csv", line_numbers=True),
        "parse_error": None,
        "summary": f"CSV Preview  {len(body):,} rows x {len(header):,} columns",
        "truncated_rows": len(body) > MAX_CSV_ROWS,
        "truncated_columns": len(header) > MAX_CSV_COLS,
    }


def _text_payload(
    name: str,
    relative_path: str,
    content: str,
    *,
    language: str | None,
) -> dict[str, Any]:
    return {
        "kind": "text",
        "name": name,
        "path": relative_path,
        "language": language,
        "content": content,
        "render": _syntax_payload(content, language=language, line_numbers=True),
    }


def _detail_payload_for_item(item: JsonInspectorItem) -> dict[str, Any]:
    """Serialize one JSON-inspector detail pane using the TUI's heuristics."""
    value = item.detail if item.synthetic and item.detail is not None else item.raw_value
    if item.synthetic and isinstance(value, dict | list):
        blocks = _serialize_structured_detail(value, nested=False)
    elif item.key:
        blocks = _serialize_keyed_value(item.key, value)
    else:
        blocks = _serialize_payload_detail(value)
    return {"kind": "detail", "blocks": blocks}


def _serialize_payload_detail(value: Any) -> list[dict[str, Any]]:
    """Serialize an arbitrary payload into structured browser detail blocks."""
    decoded = _decode_nested_json(value)
    if isinstance(decoded, dict | list):
        promoted = _promote_wrapper_value(decoded)
        if promoted is not None:
            return _serialize_structured_detail(promoted, nested=True)
        if _has_human_text(decoded):
            return _serialize_structured_detail(decoded, nested=True)
        return [_json_detail_block(decoded)]
    if decoded is None:
        return [_text_detail_block("")]
    return _serialize_string_detail(str(decoded))


def _serialize_string_detail(value: str) -> list[dict[str, Any]]:
    if not value:
        return [_text_detail_block("")]

    decoded = _try_decode_json(value)
    if isinstance(decoded, dict | list):
        promoted = _promote_wrapper_value(decoded)
        if promoted is not None:
            return _serialize_structured_detail(promoted, nested=True)
        if _has_human_text(decoded):
            return _serialize_structured_detail(decoded, nested=True)
        return [_json_detail_block(decoded)]

    if _looks_like_markdown(value):
        return [{"kind": "markdown", "value": value}]
    if _looks_like_preformatted_text(value):
        return [_syntax_payload(value, language="text", line_numbers=False)]
    return [_text_detail_block(value)]


def _serialize_structured_detail(
    value: Any,
    *,
    nested: bool,
) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return _serialize_dict_sections(value, nested=nested)
    if isinstance(value, list):
        return _serialize_list_sections(value, nested=nested)
    return _serialize_payload_detail(value)


def _serialize_dict_sections(
    value: dict[str, Any],
    *,
    nested: bool,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    metadata: list[dict[str, str]] = []
    if "value" in value and not _is_empty_value(_decode_nested_json(value["value"])):
        blocks.extend(_serialize_payload_detail(_decode_nested_json(value["value"])))
    for key, item in value.items():
        if key == "value":
            continue
        decoded = _decode_nested_json(item)
        if _is_empty_value(decoded):
            continue
        if _is_scalar_metadata(key, decoded):
            metadata.append({"label": _display_label(key), "value": str(decoded)})
            continue
        collapsed = _section_collapsed(key, nested=nested)
        blocks.append(
            {
                "kind": "section",
                "title": _display_label(key),
                "collapsed": collapsed,
                "secondary": collapsed,
                "blocks": _serialize_keyed_value(str(key), decoded),
            }
        )
    if metadata:
        blocks = [{"kind": "fields", "fields": metadata}] + blocks
    if blocks:
        return blocks
    return [_json_detail_block(value)]


def _serialize_list_sections(
    value: list[Any],
    *,
    nested: bool,
) -> list[dict[str, Any]]:
    if not _has_human_text(value):
        return [_json_detail_block(value)]

    blocks: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        decoded = _decode_nested_json(item)
        if _is_empty_value(decoded):
            continue
        blocks.append(
            {
                "kind": "section",
                "title": f"Item {index}",
                "collapsed": nested,
                "secondary": nested,
                "blocks": _serialize_keyed_value("", decoded),
            }
        )
    if blocks:
        return blocks
    return [_json_detail_block(value)]


def _serialize_keyed_value(key: str, value: Any) -> list[dict[str, Any]]:
    normalized_key = key.lower()
    if isinstance(value, str):
        return _serialize_keyed_string(normalized_key, value)
    if isinstance(value, dict):
        promoted = _promote_wrapper_value(value)
        if promoted is not None:
            return _serialize_structured_detail(promoted, nested=True)
        if _has_human_text(value):
            return _serialize_dict_sections(value, nested=True)
        return [_json_detail_block(value)]
    if isinstance(value, list):
        if normalized_key == "pages":
            return _serialize_pages(value)
        if _has_human_text(value):
            return _serialize_list_sections(value, nested=True)
        return [_json_detail_block(value)]
    return [_text_detail_block(str(value))]


def _serialize_keyed_string(key: str, value: str) -> list[dict[str, Any]]:
    decoded = _try_decode_json(value)
    if isinstance(decoded, dict | list):
        promoted = _promote_wrapper_value(decoded)
        if promoted is not None:
            return _serialize_structured_detail(promoted, nested=True)
        if _has_human_text(decoded):
            return _serialize_structured_detail(decoded, nested=True)
        return [_json_detail_block(decoded)]
    if key == "command":
        return [_syntax_payload(value, language="bash", line_numbers=False)]
    if key == "code":
        return [_syntax_payload(value, language=_guess_code_lexer(value), line_numbers=False)]
    return _serialize_string_detail(value)


def _serialize_pages(value: list[Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        decoded = _decode_nested_json(item)
        blocks.append(
            {
                "kind": "section",
                "title": f"Page {index}",
                "collapsed": True,
                "secondary": True,
                "blocks": _serialize_keyed_value("text", decoded),
            }
        )
    return blocks or [_json_detail_block(value)]


def _json_detail_block(value: Any) -> dict[str, Any]:
    return _syntax_payload(json.dumps(value, indent=2), language="json", line_numbers=False)


def _text_detail_block(value: str) -> dict[str, Any]:
    return {"kind": "text", "value": value}


def _render_value(value: Any, *, key: str = "") -> dict[str, Any]:
    decoded = _decode_json_value(value)
    if isinstance(decoded, dict | list):
        return _syntax_payload(json.dumps(decoded, indent=2), language="json", line_numbers=False)
    if decoded is None:
        return {"kind": "text", "value": ""}

    text = str(decoded)
    normalized_key = key.lower()
    if normalized_key == "command":
        return _syntax_payload(text, language="bash", line_numbers=False)
    if normalized_key == "code":
        return _syntax_payload(text, language=_guess_language(text), line_numbers=False)
    if _looks_like_markdown(text):
        return {"kind": "markdown", "value": text}
    if _looks_like_preformatted_text(text):
        return _syntax_payload(text, language="text", line_numbers=False)
    return {"kind": "text", "value": text}


def _guess_language(value: str) -> str:
    lowered = value.lstrip()
    if lowered.startswith("def ") or lowered.startswith("class "):
        return "python"
    if lowered.startswith("{") or lowered.startswith("["):
        return "json"
    return "text"


@lru_cache(maxsize=2)
def _syntax_formatter(*, line_numbers: bool) -> HtmlFormatter:
    """Return the shared HTML formatter used by the web client."""
    return HtmlFormatter(
        style="monokai",
        cssclass="syntax-block",
        classprefix="tok-",
        linenos="table" if line_numbers else False,
        nobackground=True,
    )


def _syntax_payload(value: str, *, language: str | None, line_numbers: bool) -> dict[str, Any]:
    """Return a syntax-highlighted HTML payload with a safe plain-text fallback."""
    text = value or ""
    if not language:
        return {"kind": "text", "value": text}
    try:
        lexer = get_lexer_by_name(language)
    except ClassNotFound:
        return {"kind": "text", "value": text}

    try:
        html = highlight(text, lexer, _syntax_formatter(line_numbers=line_numbers))
    except Exception:
        return {"kind": "text", "value": text}

    return {
        "kind": "syntax",
        "language": language,
        "line_numbers": line_numbers,
        "value": text,
        "html": html,
    }


def _decode_json_value(value: Any) -> Any:
    if isinstance(value, str):
        decoded = _try_decode_json(value)
        if isinstance(decoded, dict | list):
            return decoded
    return value


def _annotation_payload(record: AnnotationRecord | None) -> dict[str, Any] | None:
    if record is None:
        return None
    return {
        "tags": list(record.tags),
        "note": record.note,
    }


def _annotation_payload_for_path(
    annotations: dict[str, AnnotationRecord],
    path: tuple[str | int, ...] | None,
) -> dict[str, Any] | None:
    if path is None:
        return None
    return _annotation_payload(annotations.get(_format_raw_path(path)))


def _format_path(path: tuple[str | int, ...] | None) -> str | None:
    if path is None:
        return None
    return _format_raw_path(path)


def _node_style(kind: str) -> str:
    if kind in {
        "bundle_summary",
        "submission_summary",
        "transcript_summary",
        "trajectory_metadata",
        "trajectory_final_output",
    }:
        return "summary"
    if kind in {"trajectory_step", "trajectory_tool_input", "trajectory_tool_output"}:
        return "highlight"
    return "default"


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _is_bare_trajectory_object(data: Any) -> bool:
    """Return whether the file itself is a bare trajectory object."""
    trajectory = extract_trajectory(data)
    return trajectory is not None and trajectory is data


def _web_overlay_trajectory_target(
    root_data: Any,
    value: Any,
    raw_path: tuple[str | int, ...],
) -> tuple[dict[str, Any] | None, tuple[str | int, ...]]:
    """Route trajectory overlays for the browser without hiding rich wrapper keys."""
    if raw_path == ():
        if _is_bare_trajectory_object(value):
            return value, raw_path
        if isinstance(root_data, dict) and _uses_root_wrapped_overlay(root_data):
            wrapped = extract_trajectory(root_data)
            if wrapped is not None:
                return wrapped, ("trajectory",)
        return None, raw_path

    if raw_path == ("trajectory",) and isinstance(root_data, dict):
        trajectory = extract_trajectory({"trajectory": value})
        if trajectory is value and _is_bare_trajectory_object(value):
            return value, raw_path
        return None, raw_path

    if _is_bare_trajectory_object(value):
        return value, raw_path
    return None, raw_path


def _uses_root_wrapped_overlay(value: Any) -> bool:
    """Return whether a wrapped trajectory should surface summary nodes at the root."""
    return isinstance(value, dict) and set(value) == {"trajectory"}
