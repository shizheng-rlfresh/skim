"""Trajectory normalization and specialized trajectory viewer widgets for skim.

This module owns the agent-trajectory-specific data model, tree/detail rendering,
and payload formatting behavior. It does not own file I/O or the outer application
shell; those stay in the preview router and app modules.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Collapsible, Input, Markdown, Static, TextArea
from textual.widgets import Tree as TextualTree

from .scrolling import DragTree, FocusableDetailWrap

HUMAN_TEXT_KEYS = {
    "arguments",
    "code",
    "command",
    "conversations",
    "content",
    "final_output",
    "markdown",
    "output",
    "pages",
    "prompt",
    "result",
    "stderr",
    "stdout",
    "task",
    "task_solution",
    "text",
    "trajectory",
}
WRAPPER_KEYS = ("arguments", "content", "output", "result", "text")
PRIMARY_CONTENT_KEYS = ("stdout", "code", "command", "text", "value")
SECONDARY_COLLAPSED_KEYS = {"stderr", "pages", "json", "metadata", "other"}


@dataclass(frozen=True)
class TrajectoryEvent:
    """Normalized low-level event from a raw trajectory."""

    index: int
    kind: str
    label: str
    excerpt: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class ToolInteraction:
    """Paired tool call and result linked by call id."""

    index: int
    tool_name: str
    short_name: str
    call_id: str
    short_call_id: str
    call_event: TrajectoryEvent | None = None
    result_event: TrajectoryEvent | None = None


@dataclass(frozen=True)
class StepTimelineItem:
    """Display row inside one trajectory step."""

    kind: str
    index: int
    title: Text
    event: TrajectoryEvent | None = None
    interaction: ToolInteraction | None = None


@dataclass(frozen=True)
class TrajectoryTreeItem:
    """Data attached to a trajectory tree node."""

    kind: str
    title: str
    detail: Any = None
    event: TrajectoryEvent | None = None
    interaction: ToolInteraction | None = None
    focus: str = "full"


@dataclass(frozen=True)
class AnnotationRecord:
    """Persisted annotation for one JSON node."""

    tags: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class AnnotationEditorResult:
    """Dismiss payload from the annotation editor modal."""

    action: str
    tags: tuple[str, ...] = ()
    note: str = ""


class AnnotationStore:
    """Local JSON-backed annotation storage rooted at the current browse path."""

    def __init__(self, review_root: Path) -> None:
        """Initialize the annotation store for one browse root."""
        self.review_root = review_root.resolve()
        self.path = self.review_root / ".skim" / "review.json"
        self._payload = self._load()

    def annotations_for_file(self, source_path: Path) -> dict[str, AnnotationRecord]:
        """Return stored annotations for one source file."""
        relative_path = self.relative_file_path(source_path)
        files = self._payload.get("files", {})
        file_entry = files.get(relative_path, {})
        annotations = file_entry.get("annotations", {})
        result: dict[str, AnnotationRecord] = {}
        for path, payload in annotations.items():
            if not isinstance(path, str) or not isinstance(payload, dict):
                continue
            tags = payload.get("tags", [])
            note = payload.get("note", "")
            if isinstance(tags, list) and isinstance(note, str):
                result[path] = AnnotationRecord(
                    tags=tuple(str(tag) for tag in tags if str(tag).strip()),
                    note=note,
                )
        return result

    def get_annotation(self, source_path: Path, path: str) -> AnnotationRecord | None:
        """Return one annotation by file-relative JSON path."""
        return self.annotations_for_file(source_path).get(path)

    def set_annotation(
        self,
        source_path: Path,
        path: str,
        *,
        tags: tuple[str, ...],
        note: str,
    ) -> None:
        """Store or replace one annotation."""
        relative_path = self.relative_file_path(source_path)
        files = self._payload.setdefault("files", {})
        file_entry = files.setdefault(relative_path, {"annotations": {}})
        annotations = file_entry.setdefault("annotations", {})
        annotations[path] = {"tags": list(tags), "note": note}
        self._save()

    def delete_annotation(self, source_path: Path, path: str) -> None:
        """Delete one annotation if present."""
        relative_path = self.relative_file_path(source_path)
        files = self._payload.setdefault("files", {})
        file_entry = files.setdefault(relative_path, {"annotations": {}})
        annotations = file_entry.setdefault("annotations", {})
        annotations.pop(path, None)
        self._save()

    def relative_file_path(self, source_path: Path) -> str:
        """Return the normalized file key used in persisted review data."""
        resolved = source_path.resolve()
        try:
            return resolved.relative_to(self.review_root).as_posix()
        except ValueError:
            return resolved.name

    def _load(self) -> dict[str, Any]:
        """Load the persisted annotation payload with safe fallbacks."""
        if not self.path.is_file():
            return {"version": 1, "files": {}}
        try:
            payload = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "files": {}}
        if not isinstance(payload, dict):
            return {"version": 1, "files": {}}
        payload.setdefault("version", 1)
        payload.setdefault("files", {})
        return payload

    def _save(self) -> None:
        """Write the annotation payload to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._payload, indent=2, sort_keys=True))


class AnnotationEditor(ModalScreen[AnnotationEditorResult | None]):
    """Small modal form for editing one annotation."""

    PREVIEW_SCROLL_STEP = 20
    BINDINGS = [
        Binding("escape", "cancel", show=False),
        Binding("pageup", "scroll_preview_up", show=False),
        Binding("pagedown", "scroll_preview_down", show=False),
    ]

    def __init__(
        self,
        path: str,
        annotation: AnnotationRecord | None,
        item: JsonInspectorItem,
        on_submit: Callable[[AnnotationEditorResult], None] | None = None,
    ) -> None:
        """Initialize the modal for one selected annotation target."""
        super().__init__()
        self.path = path
        self.annotation = annotation
        self.item = item
        self._on_submit = on_submit

    def compose(self) -> ComposeResult:
        """Compose the modal editor widgets."""
        tags = ", ".join(self.annotation.tags) if self.annotation is not None else ""
        note = self.annotation.note if self.annotation is not None else ""
        yield Horizontal(
            Vertical(
                Static(Text("Edit Annotation", style="bold"), classes="annotation-modal-title"),
                Static(Text(f"Path: {self.path}", style="dim"), classes="annotation-modal-path"),
                Input(value=tags, placeholder="tags, comma, separated", id="annotation-tags"),
                TextArea(note, id="annotation-note"),
                Horizontal(
                    Button("Save", id="annotation-save", variant="primary"),
                    Button(
                        "Delete",
                        id="annotation-delete",
                        variant="error",
                        disabled=self.annotation is None,
                    ),
                    Button("Cancel", id="annotation-cancel"),
                    classes="annotation-modal-actions",
                ),
                id="annotation-editor-panel",
                classes="annotation-modal-panel",
            ),
            Vertical(
                Static(
                    Text("Node Preview", style="bold"),
                    classes="annotation-modal-preview-title",
                ),
                FocusableDetailWrap(
                    *_json_detail_widgets(self.item),
                    id="annotation-preview",
                    classes="annotation-modal-preview",
                ),
                id="annotation-preview-panel",
                classes="annotation-modal-panel",
            ),
            id="annotation-modal",
        )

    def on_mount(self) -> None:
        """Focus the tags field when the modal opens."""
        self.query_one("#annotation-tags", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Advance from tags input to note instead of submitting the modal."""
        if event.input.id != "annotation-tags":
            return
        self.query_one("#annotation-note", TextArea).focus()
        event.stop()

    def action_scroll_preview_up(self) -> None:
        """Scroll the right preview up."""
        self.query_one("#annotation-preview", FocusableDetailWrap).scroll_relative(
            y=-self.PREVIEW_SCROLL_STEP,
            animate=False,
        )

    def action_scroll_preview_down(self) -> None:
        """Scroll the right preview down."""
        self.query_one("#annotation-preview", FocusableDetailWrap).scroll_relative(
            y=self.PREVIEW_SCROLL_STEP,
            animate=False,
        )

    def action_cancel(self) -> None:
        """Dismiss the modal without changes."""
        self.dismiss(None)

    def action_save(self) -> None:
        """Dismiss with a save payload."""
        self._submit(
            AnnotationEditorResult(
                action="save",
                tags=_parse_annotation_tags(self.query_one("#annotation-tags", Input).value),
                note=self.query_one("#annotation-note", TextArea).text.rstrip(),
            )
        )

    def action_delete(self) -> None:
        """Dismiss with a delete payload."""
        self._submit(AnnotationEditorResult(action="delete"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle modal button clicks."""
        button_id = event.button.id
        if button_id == "annotation-save":
            self.action_save()
        elif button_id == "annotation-delete":
            self.action_delete()
        else:
            self.action_cancel()
        event.stop()

    def _submit(self, result: AnnotationEditorResult) -> None:
        """Invoke the save/delete callback before dismissing the modal."""
        if self._on_submit is not None:
            self._on_submit(result)
        self.dismiss(result)


def extract_trajectory(data: Any) -> dict[str, Any] | None:
    """Return a supported trajectory object from wrapped or bare JSON."""
    if not isinstance(data, dict):
        return None
    wrapped = data.get("trajectory")
    if isinstance(wrapped, dict) and isinstance(wrapped.get("steps"), list):
        return wrapped
    if isinstance(data.get("steps"), list):
        return data
    return None


def normalize_events(trajectory: dict[str, Any]) -> list[TrajectoryEvent]:
    """Return normalized low-level events from a supported trajectory object."""
    events: list[TrajectoryEvent] = []
    steps = trajectory.get("steps")
    if not isinstance(steps, list):
        return events

    for step in steps:
        if not isinstance(step, dict):
            continue
        outputs = step.get("output")
        if not isinstance(outputs, list):
            continue
        for output in outputs:
            if not isinstance(output, dict):
                continue
            kind = str(output.get("type") or "event")
            label = _event_label(output)
            excerpt = _event_excerpt(output)
            events.append(
                TrajectoryEvent(
                    index=len(events),
                    kind=kind,
                    label=label,
                    excerpt=excerpt,
                    raw=output,
                )
            )
    return events


def normalize_step_events(trajectory: dict[str, Any]) -> list[list[TrajectoryEvent]]:
    """Return normalized events grouped by top-level step."""
    groups: list[list[TrajectoryEvent]] = []
    steps = trajectory.get("steps")
    if not isinstance(steps, list):
        return groups

    index = 0
    for step in steps:
        group: list[TrajectoryEvent] = []
        if isinstance(step, dict) and isinstance(step.get("output"), list):
            for output in step["output"]:
                if not isinstance(output, dict):
                    continue
                kind = str(output.get("type") or "event")
                event = TrajectoryEvent(
                    index=index,
                    kind=kind,
                    label=_event_label(output),
                    excerpt=_event_excerpt(output),
                    raw=output,
                )
                group.append(event)
                index += 1
        groups.append(group)
    return groups


def normalize_step_timeline(trajectory: dict[str, Any]) -> list[list[StepTimelineItem]]:
    """Return per-step display rows, pairing tool calls with matching results."""
    timeline_groups: list[list[StepTimelineItem]] = []
    for step_events in normalize_step_events(trajectory):
        group: list[StepTimelineItem] = []
        pending_calls: dict[str, int] = {}
        for event in step_events:
            if event.kind == "function_call":
                interaction = ToolInteraction(
                    index=event.index,
                    tool_name=_tool_name(event.raw),
                    short_name=_short_tool_name(_tool_name(event.raw)),
                    call_id=_call_id(event.raw),
                    short_call_id=_short_call_id(_call_id(event.raw)),
                    call_event=event,
                )
                group.append(
                    StepTimelineItem(
                        kind="tool",
                        index=event.index,
                        title=_tool_tree_label(interaction),
                        interaction=interaction,
                    )
                )
                if interaction.call_id:
                    pending_calls[interaction.call_id] = len(group) - 1
                continue

            if event.kind == "function_call_result":
                call_id = _call_id(event.raw)
                group_index = pending_calls.pop(call_id, None) if call_id else None
                if group_index is not None:
                    interaction = group[group_index].interaction
                    if interaction is None:
                        continue
                    updated = ToolInteraction(
                        index=interaction.index,
                        tool_name=interaction.tool_name,
                        short_name=interaction.short_name,
                        call_id=interaction.call_id,
                        short_call_id=interaction.short_call_id,
                        call_event=interaction.call_event,
                        result_event=event,
                    )
                    group[group_index] = StepTimelineItem(
                        kind="tool",
                        index=updated.index,
                        title=_tool_tree_label(updated),
                        interaction=updated,
                    )
                    continue

                orphan = ToolInteraction(
                    index=event.index,
                    tool_name=_tool_name(event.raw),
                    short_name=_short_tool_name(_tool_name(event.raw)),
                    call_id=call_id,
                    short_call_id=_short_call_id(call_id),
                    result_event=event,
                )
                group.append(
                    StepTimelineItem(
                        kind="tool",
                        index=event.index,
                        title=_tool_tree_label(orphan, suffix=" Output"),
                        interaction=orphan,
                    )
                )
                continue

            group.append(
                StepTimelineItem(
                    kind=event.kind,
                    index=event.index,
                    title=_standalone_tree_label(event),
                    event=event,
                )
            )
        timeline_groups.append(group)
    return timeline_groups


def _event_label(raw: dict[str, Any]) -> str:
    for key in ("role", "name", "callId", "call_id"):
        value = raw.get(key)
        if value:
            return str(value)
    return ""


def _tool_name(raw: dict[str, Any]) -> str:
    value = raw.get("name")
    return str(value) if value else "tool"


def _call_id(raw: dict[str, Any]) -> str:
    value = raw.get("callId") or raw.get("call_id")
    return str(value) if value else ""


def _short_tool_name(name: str) -> str:
    if "__" in name:
        return name.split("__")[-1]
    return name


def _short_call_id(call_id: str) -> str:
    if not call_id:
        return ""
    return call_id[-3:]


def _event_excerpt(raw: dict[str, Any]) -> str:
    text = _event_text(raw)
    if not text:
        text = _format_payload(_event_payload(raw))
    return _clip(_single_line(text), 96)


def _event_text(raw: dict[str, Any]) -> str:
    content = raw.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n\n".join(parts)
    if isinstance(content, str):
        return content
    return ""


def _event_payload(raw: dict[str, Any]) -> Any:
    if raw.get("type") == "function_call":
        return raw.get("arguments")
    if raw.get("type") == "function_call_result":
        return raw.get("output")
    return raw


def _single_line(value: str) -> str:
    return " ".join(value.split())


def _clip(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _decode_nested_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return _decode_nested_json(json.loads(value))
        except json.JSONDecodeError:
            return value
    if isinstance(value, list):
        return [_decode_nested_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _decode_nested_json(item) for key, item in value.items()}
    return value


def _format_payload(value: Any) -> str:
    decoded = _decode_nested_json(value)
    if isinstance(decoded, dict | list):
        return json.dumps(decoded, indent=2)
    if decoded is None:
        return ""
    return str(decoded)


def _metadata_lines(trajectory: dict[str, Any]) -> list[str]:
    metadata = trajectory.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    provider = metadata.get("llm_provider")
    model = metadata.get("llm_model")
    model_line = " / ".join(str(value) for value in (provider, model) if value)
    compactions = trajectory.get("context_compaction_events")
    compaction_count = len(compactions) if isinstance(compactions, list) else 0

    lines = []
    if model_line:
        lines.append(f"model: {model_line}")
    for key in ("trajectory_id", "task_id", "input_tokens", "output_tokens"):
        value = metadata.get(key)
        if value is not None:
            lines.append(f"{key}: {value}")
    lines.append(f"compactions: {compaction_count}")
    return lines


def _metadata_header(trajectory: dict[str, Any]) -> str:
    lines = _metadata_lines(trajectory)
    if not lines:
        return "Trajectory"
    return "Trajectory | " + " | ".join(lines[:3])


def _metadata_detail(trajectory: dict[str, Any]) -> Text:
    lines = ["Metadata", ""]
    lines.extend(_metadata_lines(trajectory))
    return Text("\n".join(lines))


def _final_output_detail(trajectory: dict[str, Any]) -> str:
    final_output = trajectory.get("final_output")
    if isinstance(final_output, str) and final_output.strip():
        return final_output.strip()
    return "No final output"


def _detail_widgets_for_item(item: TrajectoryTreeItem) -> list[Widget]:
    if item.interaction is not None:
        return _tool_interaction_detail_widgets(item.interaction, item.focus)
    if item.event is not None:
        return _event_detail_widgets(item.event)
    if isinstance(item.detail, Text):
        return [Static(item.detail, classes="trajectory-detail")]
    if isinstance(item.detail, str):
        return _render_string_detail(item.detail)
    return _render_payload_detail(item.detail)


def _event_detail_widgets(event: TrajectoryEvent) -> list[Widget]:
    header = Text(f"{event.index + 1:03d} ", style="dim")
    header.append(_standalone_title(event), style="bold")
    widgets: list[Widget] = [Static(header, classes="trajectory-detail-heading")]

    if event.kind == "message":
        widgets.extend(
            _metadata_fields(
                [("Role", _message_role(event.raw)), ("Status", _status_value(event.raw))]
            )
        )
        text = _event_text(event.raw)
        if text:
            widgets.extend(_render_string_detail(text))
        else:
            widgets.extend(_render_payload_detail(_event_payload(event.raw)))
    elif event.kind == "reasoning":
        text = _event_text(event.raw)
        if text:
            widgets.extend(_render_string_detail(text))
        else:
            widgets.extend(_render_payload_detail(_event_payload(event.raw)))
    else:
        widgets.extend(_render_payload_detail(_event_payload(event.raw)))
    return widgets


def _tool_interaction_detail_widgets(
    interaction: ToolInteraction, focus: str = "full"
) -> list[Widget]:
    title = Text(f"{interaction.index + 1:03d} ", style="dim")
    title.append(interaction.short_name, style="bold cyan")
    if interaction.short_call_id:
        title.append(f" #{interaction.short_call_id}", style="magenta")
    widgets: list[Widget] = [Static(title, classes="trajectory-detail-heading")]
    widgets.append(
        _section_widget(
            "Tool",
            _metadata_fields(
                [
                    ("Tool", interaction.tool_name),
                    ("Call ID", interaction.call_id),
                    ("Status", _interaction_status(interaction)),
                ]
            ),
            collapsed=False,
        )
    )
    widgets.append(
        _section_widget(
            "Input",
            _tool_section_widgets(interaction.call_event, "input"),
            collapsed=False,
            selected=focus == "input",
        )
    )
    widgets.append(
        _section_widget(
            "Output",
            _tool_section_widgets(interaction.result_event, "output"),
            collapsed=False,
            selected=focus == "output",
        )
    )
    return widgets


def _tool_section_widgets(event: TrajectoryEvent | None, focus: str) -> list[Widget]:
    if event is None:
        return [Static(Text(f"No {focus}"), classes="trajectory-detail")]
    if focus == "input":
        return _render_payload_detail(_decode_nested_json(event.raw.get("arguments")))
    return _render_payload_detail(_decoded_tool_result(event.raw.get("output")))


def _decoded_tool_result(output: Any) -> Any:
    """Decode and normalize wrapped tool-result payloads before rendering."""
    return _normalize_text_wrapper(_decode_nested_json(output))


def _normalize_text_wrapper(value: Any) -> Any:
    """Flatten nested output wrappers without losing sibling metadata."""
    decoded = _decode_nested_json(value)
    if not isinstance(decoded, dict):
        return decoded
    if set(decoded) == {"text"}:
        return _normalize_text_wrapper(decoded["text"])
    if isinstance(decoded.get("text"), dict):
        text_payload = _normalize_text_wrapper(decoded["text"])
        if isinstance(text_payload, dict) and any(
            key in text_payload for key in ("stdout", "stderr", "returncode", "pages", "code")
        ):
            siblings = {
                key: _normalize_text_wrapper(item)
                for key, item in decoded.items()
                if key != "text" and key not in text_payload
            }
            return {**text_payload, **siblings}
    return {key: _normalize_text_wrapper(item) for key, item in decoded.items()}


def _metadata_fields(fields: list[tuple[str, str | None]]) -> list[Widget]:
    widgets: list[Widget] = []
    for label, value in fields:
        if value in (None, ""):
            continue
        text = Text()
        text.append(f"{label}: ", style="bold cyan")
        text.append(str(value), style="white")
        widgets.append(Static(text, classes="trajectory-detail-field"))
    return widgets


def _render_payload_detail(value: Any) -> list[Widget]:
    """Render an arbitrary payload into detail widgets with safe fallbacks."""
    decoded = _decode_nested_json(value)
    if isinstance(decoded, dict | list):
        promoted = _promote_wrapper_value(decoded)
        if promoted is not None:
            return _render_structured_detail(promoted, nested=True)
        if _has_human_text(decoded):
            return _render_structured_detail(decoded, nested=True)
        return _render_json_block(decoded)
    if decoded is None:
        return [Static(Text(""))]
    return _render_string_detail(str(decoded))


def _render_string_detail(value: str) -> list[Widget]:
    if not value:
        return [Static(Text(""))]

    decoded = _try_decode_json(value)
    if isinstance(decoded, dict | list):
        promoted = _promote_wrapper_value(decoded)
        if promoted is not None:
            return _render_structured_detail(promoted, nested=True)
        if _has_human_text(decoded):
            return _render_structured_detail(decoded, nested=True)
        return _render_json_block(decoded)

    if _looks_like_markdown(value):
        return [Markdown(value, classes="trajectory-markdown")]
    if _looks_like_preformatted_text(value):
        return [Static(Syntax(value, "text", word_wrap=True), classes="trajectory-detail")]
    return [Static(Text(value), classes="trajectory-detail")]


def _promote_wrapper_value(value: Any) -> Any | None:
    """Lift meaningful content out of wrapper keys like output/text/result."""
    current = _decode_nested_json(value)
    while isinstance(current, dict):
        candidates = [
            key for key in WRAPPER_KEYS if key in current and _can_promote_wrapper(current, key)
        ]
        if not candidates:
            return None
        promoted_key = candidates[0]
        promoted_value = _decode_nested_json(current[promoted_key])
        siblings = {
            key: item
            for key, item in current.items()
            if key != promoted_key and not _is_empty_value(_decode_nested_json(item))
        }
        if siblings:
            current = {"value": promoted_value, **siblings}
        else:
            current = promoted_value
        current = _decode_nested_json(current)
    return current if current is not value else None


def _can_promote_wrapper(container: dict[str, Any], key: str) -> bool:
    """Return whether promoting a wrapper key improves readability without data loss."""
    value = _decode_nested_json(container.get(key))
    siblings = {
        sibling_key: _decode_nested_json(item)
        for sibling_key, item in container.items()
        if sibling_key != key and not _is_empty_value(_decode_nested_json(item))
    }
    if not _is_renderable_leaf(value):
        return False
    if not siblings:
        return True
    return all(not _has_human_text(item) for item in siblings.values())


def _is_renderable_leaf(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_is_renderable_leaf(item) for item in value)
    if isinstance(value, dict):
        return _has_human_text(value)
    return False


def _render_structured_detail(value: Any, nested: bool = False) -> list[Widget]:
    """Render dictionaries and lists as semantic sections when possible."""
    if isinstance(value, dict):
        return _render_dict_sections(value, nested=nested)
    if isinstance(value, list):
        return _render_list_sections(value, nested=nested)
    return _render_payload_detail(value)


def _render_dict_sections(value: dict[str, Any], nested: bool = True) -> list[Widget]:
    """Render a dictionary into labeled sections and metadata fields."""
    widgets: list[Widget] = []
    metadata: list[tuple[str, str | None]] = []
    if "value" in value and not _is_empty_value(_decode_nested_json(value["value"])):
        widgets.extend(_render_payload_detail(_decode_nested_json(value["value"])))
    for key, item in value.items():
        if key == "value":
            continue
        decoded = _decode_nested_json(item)
        if _is_empty_value(decoded):
            continue
        if _is_scalar_metadata(key, decoded):
            metadata.append((_display_label(key), str(decoded)))
            continue
        collapsed = _section_collapsed(key, nested=nested)
        widgets.append(
            _section_widget(
                _display_label(key),
                _render_keyed_value(str(key), decoded),
                collapsed=collapsed,
                secondary=collapsed,
            )
        )
    if metadata:
        widgets = _metadata_fields(metadata) + widgets
    if widgets:
        return widgets
    return _render_json_block(value)


def _render_list_sections(value: list[Any], nested: bool = True) -> list[Widget]:
    """Render a list as per-item sections when it contains human-facing content."""
    if not _has_human_text(value):
        return _render_json_block(value)

    widgets: list[Widget] = []
    for index, item in enumerate(value, start=1):
        decoded = _decode_nested_json(item)
        if _is_empty_value(decoded):
            continue
        widgets.append(
            _section_widget(
                f"Item {index}",
                _render_keyed_value("", decoded),
                collapsed=nested,
                secondary=nested,
            )
        )
    if widgets:
        return widgets
    return _render_json_block(value)


def _render_keyed_value(key: str, value: Any) -> list[Widget]:
    """Render one labeled value, preserving semantic handling for known keys."""
    normalized_key = key.lower()
    if isinstance(value, str):
        return _render_keyed_string(normalized_key, value)
    if isinstance(value, dict):
        promoted = _promote_wrapper_value(value)
        if promoted is not None:
            return _render_structured_detail(promoted, nested=True)
        if _has_human_text(value):
            return _render_dict_sections(value, nested=True)
        return _render_json_block(value)
    if isinstance(value, list):
        if normalized_key == "pages":
            return _render_pages(value)
        if _has_human_text(value):
            return _render_list_sections(value, nested=True)
        return _render_json_block(value)
    return [Static(Text(str(value)), classes="trajectory-detail")]


def _render_keyed_string(key: str, value: str) -> list[Widget]:
    """Render a labeled string with content-aware markdown/code/json detection."""
    decoded = _try_decode_json(value)
    if isinstance(decoded, dict | list):
        promoted = _promote_wrapper_value(decoded)
        if promoted is not None:
            return _render_structured_detail(promoted, nested=True)
        return (
            _render_structured_detail(decoded, nested=True)
            if _has_human_text(decoded)
            else _render_json_block(decoded)
        )
    if key == "command":
        return [Static(Syntax(value, "bash", word_wrap=True), classes="trajectory-detail")]
    if key == "code":
        return [
            Static(
                Syntax(value, _guess_code_lexer(value), word_wrap=True), classes="trajectory-detail"
            )
        ]
    return _render_string_detail(value)


def _render_pages(value: list[Any]) -> list[Widget]:
    """Render page arrays as individual collapsible sections."""
    widgets: list[Widget] = []
    for index, item in enumerate(value, start=1):
        decoded = _decode_nested_json(item)
        widgets.append(
            _section_widget(
                f"Page {index}",
                _render_keyed_value("text", decoded),
                collapsed=True,
                secondary=True,
            )
        )
    return widgets or _render_json_block(value)


def _render_json_block(value: Any) -> list[Widget]:
    return [
        Static(
            Syntax(json.dumps(value, indent=2), "json", word_wrap=True),
            classes="trajectory-detail",
        )
    ]


def _has_human_text(value: Any) -> bool:
    if isinstance(value, str):
        return (
            "\n" in value
            or _looks_like_markdown(value)
            or _looks_like_preformatted_text(value)
            or bool(value.strip())
        )
    if isinstance(value, dict):
        return any(
            str(key).lower() in HUMAN_TEXT_KEYS and _has_human_text(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_has_human_text(item) for item in value)
    return False


def _is_empty_value(value: Any) -> bool:
    return value is None or value == "" or value == []


def _guess_code_lexer(value: str) -> str:
    if stripped := value.lstrip():
        if stripped.startswith(("import ", "from ", "def ", "class ")):
            return "python"
        if stripped.startswith(("#!", "set -", "cd ", "ls ", "find ")):
            return "bash"
    return "text"


def _try_decode_json(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _looks_like_markdown(value: str) -> bool:
    lines = value.splitlines()
    if "```" in value:
        return True
    return any(
        line.startswith(("# ", "## ", "### ", "> ", "- ", "* "))
        or "| " in line
        or line[:3].isdigit()
        for line in lines
    )


def _looks_like_preformatted_text(value: str) -> bool:
    lines = value.splitlines()
    if len(lines) < 2:
        return False
    sample = lines[:30]
    indented = sum(1 for line in sample if line.startswith(("    ", "\t")))
    if indented / max(len(sample), 1) > 0.3:
        return True
    if value.count("/") > 5 or value.count("\t") > 3:
        return True
    return False


def _section_widget(
    title: str,
    body: list[Widget],
    *,
    collapsed: bool,
    selected: bool = False,
    secondary: bool = False,
) -> Collapsible:
    if not body:
        body = [Static(Text("(empty)"), classes="trajectory-detail")]
    classes = ["trajectory-section"]
    if selected:
        classes.append("trajectory-section-selected")
    if secondary:
        classes.append("trajectory-section-secondary")
    return Collapsible(*body, title=title, collapsed=collapsed, classes=" ".join(classes))


def _display_label(key: str) -> str:
    special = {
        "agentic_grader_guidance": "Grader Guidance",
        "call_id": "Call ID",
        "code": "code",
        "command": "command",
        "final_output": "Final Output",
        "load_trajectories_s3": "Trajectory URL",
        "pages": "pages",
        "prompt": "Prompt",
        "quick_scores": "Quick Scores",
        "quick_stats": "Quick Stats",
        "returncode": "returncode",
        "stderr": "stderr",
        "stdout": "stdout",
        "submission_type": "Submission Type",
        "task": "Task",
        "task_name": "Task Name",
        "task_solution": "Task Solution",
        "text": "text",
        "trajectory": "Trajectory",
    }
    if key in special:
        return special[key]
    return key


def _section_collapsed(key: str, *, nested: bool) -> bool:
    if key.lower() in PRIMARY_CONTENT_KEYS:
        return False
    if key.lower() in SECONDARY_COLLAPSED_KEYS:
        return True
    return nested


def _is_scalar_metadata(key: str, value: Any) -> bool:
    if isinstance(value, bool | int | float):
        return True
    if isinstance(value, str):
        if key.lower() in {"stdout", "stderr", "text", "code", "command"}:
            return False
        return "\n" not in value and len(value) <= 120
    return False


def _standalone_title(event: TrajectoryEvent) -> str:
    if event.kind == "reasoning":
        return "Reasoning"
    if event.kind == "message":
        return _message_role(event.raw)
    return event.kind.replace("_", " ").title()


def _standalone_tree_label(event: TrajectoryEvent) -> Text:
    label = Text(f"{event.index + 1:03d} ", style="dim")
    label.append(_standalone_title(event), style=_tree_kind_style(event.kind))
    if event.excerpt:
        label.append(f" {_clip(event.excerpt, 64)}", style="default")
    return label


def _tool_tree_label(interaction: ToolInteraction, suffix: str = "") -> Text:
    label = Text(f"{interaction.index + 1:03d} ", style="dim")
    label.append(interaction.short_name, style="bold cyan")
    if interaction.short_call_id:
        label.append(f" #{interaction.short_call_id}", style="magenta")
    if suffix:
        label.append(suffix, style="bold yellow")
    return label


def _message_role(raw: dict[str, Any]) -> str:
    role = raw.get("role")
    if not role:
        return "Message"
    return str(role).title()


def _status_value(raw: dict[str, Any]) -> str | None:
    value = raw.get("status")
    return str(value) if value else None


def _interaction_status(interaction: ToolInteraction) -> str | None:
    for event in (interaction.result_event, interaction.call_event):
        if event is None:
            continue
        status = _status_value(event.raw)
        if status:
            return status
    return None


def _tree_kind_style(kind: str) -> str:
    if kind == "reasoning":
        return "yellow"
    if kind == "message":
        return "green"
    return "cyan"


class TrajectoryViewer(Vertical):
    """Structured preview for a single raw trajectory."""

    def __init__(self, trajectory: dict[str, Any]) -> None:
        """Initialize the trajectory viewer."""
        super().__init__(classes="trajectory-viewer")
        self.trajectory = trajectory
        self.step_events = normalize_step_events(trajectory)
        self.step_items = normalize_step_timeline(trajectory)
        self.events = normalize_events(trajectory)
        self._input_mode = "tree"
        self._summary = Static(Text(_metadata_header(trajectory)), classes="trajectory-summary")
        self._tree: DragTree = DragTree("Trajectory", classes="trajectory-tree")
        self._build_tree()
        first_item = self._tree.root.children[0].data
        initial_widgets: list[Widget] = []
        if isinstance(first_item, TrajectoryTreeItem):
            initial_widgets = _detail_widgets_for_item(first_item)
        self._detail_wrap = FocusableDetailWrap(*initial_widgets, classes="trajectory-detail-wrap")
        self._footer = Static(self._footer_text(), classes="trajectory-footer")

    def compose(self) -> ComposeResult:
        """Compose the trajectory summary, event tree, and detail panel."""
        yield self._summary
        with Horizontal(classes="trajectory-body"):
            yield self._tree
            yield self._detail_wrap
        yield self._footer

    def on_tree_node_selected(self, event: TextualTree.NodeSelected[TrajectoryTreeItem]) -> None:
        """Update detail when a trajectory tree node is selected."""
        item = event.node.data
        if isinstance(item, TrajectoryTreeItem):
            self._show_detail(item)
        event.stop()

    def _show_detail(self, item: TrajectoryTreeItem) -> None:
        """Replace the detail pane with widgets for the selected tree item."""
        self._detail_wrap.remove_children()
        self._detail_wrap.mount(*_detail_widgets_for_item(item))
        self._detail_wrap.scroll_home(animate=False)

    def scroll_detail(self, delta: int) -> None:
        """Scroll the rendered detail panel."""
        self._detail_wrap.scroll_relative(y=delta, animate=False)

    def is_tree_mode(self) -> bool:
        """Return whether keyboard navigation is driving the left tree."""
        return self._input_mode == "tree"

    def focus_tree_mode(self) -> None:
        """Route navigation input to the tree."""
        self._input_mode = "tree"
        self._update_footer()
        self._ensure_tree_cursor()
        if self.is_attached:
            self._tree.focus(scroll_visible=False)

    def focus_detail_mode(self) -> None:
        """Route navigation input to the rendered detail pane."""
        self._input_mode = "detail"
        self._update_footer()
        if self.is_attached:
            self._detail_wrap.focus(scroll_visible=False)

    def handle_vertical_key(self, delta: int) -> bool:
        """Handle up/down keys for the active trajectory sub-view."""
        if self.is_tree_mode():
            if delta < 0:
                self._tree.action_cursor_up()
            else:
                self._tree.action_cursor_down()
            return True
        self.scroll_detail(delta)
        return True

    def handle_horizontal_key(self, key: str) -> bool:
        """Handle left/right tree navigation."""
        if not self.is_tree_mode():
            return False
        node = self._tree.cursor_node
        if node is None:
            return False
        if key == "left":
            if node.allow_expand and node.is_expanded:
                node.collapse()
            elif node.parent is not None:
                self._tree.move_cursor(node.parent, animate=False)
            return True
        if key == "right":
            if node.allow_expand and node.is_collapsed:
                node.expand()
            elif node.children:
                self._tree.move_cursor(node.children[0], animate=False)
            return True
        return False

    def handle_enter_key(self) -> bool:
        """Select the current tree item and move focus to the detail pane."""
        if not self.is_tree_mode():
            return False
        self._ensure_tree_cursor()
        self._tree.action_select_cursor()
        self.focus_detail_mode()
        return True

    def handle_escape_key(self) -> bool:
        """Return keyboard control from detail back to the tree."""
        if self.is_tree_mode():
            return False
        self.focus_tree_mode()
        return True

    def _ensure_tree_cursor(self) -> None:
        """Keep the tree cursor on the first visible child instead of the root."""
        cursor = self._tree.cursor_node
        if (cursor is None or cursor.is_root) and self._tree.root.children:
            self._tree.move_cursor(self._tree.root.children[0], animate=False)

    def _footer_text(self) -> Text:
        """Build the mode-aware local footer text."""
        text = Text()
        if self.is_tree_mode():
            text.append(" JSON ", style="reverse")
            text.append(" ")
            text.append("↑↓", style="bold")
            text.append(" Move  ")
            text.append("←→", style="bold")
            text.append(" Branch  ")
            text.append("Enter", style="bold")
            text.append(" Detail")
        else:
            text.append(" Detail ", style="reverse")
            text.append(" ")
            text.append("↑↓", style="bold")
            text.append(" Scroll  ")
            text.append("Esc", style="bold")
            text.append(" Back to JSON")
        return text

    def _update_footer(self) -> None:
        """Refresh the local footer after mode changes."""
        self._footer.update(self._footer_text())

    def _build_tree(self) -> None:
        """Populate the trajectory tree."""
        self._tree.root.expand()
        self._tree.root.add_leaf(
            "Metadata",
            data=TrajectoryTreeItem("metadata", "Metadata", _metadata_detail(self.trajectory)),
        )
        self._tree.root.add_leaf(
            "Final Output",
            data=TrajectoryTreeItem(
                "final_output", "Final Output", _final_output_detail(self.trajectory)
            ),
        )
        for step_index, items in enumerate(self.step_items, start=1):
            step = self._tree.root.add(
                f"Step {step_index}",
                data=TrajectoryTreeItem(
                    "step",
                    f"Step {step_index}",
                    Text(f"Step {step_index}\n\n{len(items)} items"),
                ),
                expand=True,
            )
            for item in items:
                if item.interaction is not None:
                    parent = step.add(
                        item.title,
                        data=TrajectoryTreeItem(
                            "tool",
                            item.title.plain,
                            interaction=item.interaction,
                            focus="full",
                        ),
                        expand=True,
                    )
                    parent.add_leaf(
                        Text("Input", style="bold yellow"),
                        data=TrajectoryTreeItem(
                            "tool_input",
                            "Input",
                            interaction=item.interaction,
                            focus="input",
                        ),
                    )
                    parent.add_leaf(
                        Text("Output", style="bold yellow"),
                        data=TrajectoryTreeItem(
                            "tool_output",
                            "Output",
                            interaction=item.interaction,
                            focus="output",
                        ),
                    )
                elif item.event is not None:
                    step.add_leaf(
                        item.title,
                        data=TrajectoryTreeItem(
                            "event",
                            item.title.plain,
                            event=item.event,
                        ),
                    )


@dataclass(frozen=True)
class JsonInspectorItem:
    """Data attached to one JSON-inspector tree node."""

    kind: str
    title: str
    raw_path: tuple[str | int, ...]
    raw_value: Any
    key: str = ""
    detail: Any = None
    trajectory_item: TrajectoryTreeItem | None = None
    synthetic: bool = False
    annotation_path: tuple[str | int, ...] | None = None


class JsonInspector(Vertical):
    """Unified structural inspector for JSON files with semantic overlays."""

    def __init__(
        self,
        data: Any,
        *,
        source_path: Path | None = None,
        review_root: Path | None = None,
        annotation_store: AnnotationStore | None = None,
    ) -> None:
        """Initialize the JSON inspector for parsed JSON content."""
        super().__init__(classes="trajectory-viewer")
        self.data = data
        self.source_path = source_path.resolve() if source_path is not None else None
        resolved_root = review_root or (self.source_path.parent if self.source_path else Path.cwd())
        self.review_root = resolved_root.resolve()
        self._annotation_store = annotation_store or AnnotationStore(self.review_root)
        self._current_item: JsonInspectorItem | None = None
        self._tree: DragTree = DragTree("JSON", classes="trajectory-tree")
        self._build_tree()
        first_item = self._tree.root.children[0].data if self._tree.root.children else None
        initial_detail_widgets: list[Widget] = []
        initial_annotation_widgets: list[Widget] = _annotation_panel_widgets(None, False)
        if isinstance(first_item, JsonInspectorItem):
            self._current_item = first_item
            initial_detail_widgets = self._detail_widgets_for_item(first_item)
            initial_annotation_widgets = self._annotation_widgets_for_item(first_item)
        self._annotation_wrap = Vertical(
            *initial_annotation_widgets,
            classes="annotation-status-panel",
        )
        self._detail_wrap = FocusableDetailWrap(
            *initial_detail_widgets,
            classes="trajectory-detail-wrap",
        )
        self._detail_column = Vertical(
            self._annotation_wrap,
            self._detail_wrap,
            classes="trajectory-detail-column",
        )
        self._footer = Static(self._footer_text(), classes="trajectory-footer")

    def compose(self) -> ComposeResult:
        """Compose the JSON tree, detail panel, and local footer."""
        with Horizontal(classes="trajectory-body"):
            yield self._tree
            yield self._detail_column
        yield self._footer

    def on_tree_node_selected(self, event: TextualTree.NodeSelected[JsonInspectorItem]) -> None:
        """Update detail when a JSON tree node is selected."""
        item = event.node.data
        if isinstance(item, JsonInspectorItem):
            self._show_detail(item)
        event.stop()

    def on_tree_node_highlighted(
        self,
        event: TextualTree.NodeHighlighted[JsonInspectorItem],
    ) -> None:
        """Update detail when the highlighted JSON tree node changes."""
        item = event.node.data
        if isinstance(item, JsonInspectorItem):
            self._show_detail(item)
        event.stop()

    def _show_detail(self, item: JsonInspectorItem) -> None:
        """Replace the detail pane with widgets for the selected tree item."""
        self._current_item = item
        self._annotation_wrap.remove_children()
        self._annotation_wrap.mount(*self._annotation_widgets_for_item(item))
        self._detail_wrap.remove_children()
        self._detail_wrap.mount(*self._detail_widgets_for_item(item))
        self._detail_wrap.scroll_home(animate=False)

    def scroll_detail(self, delta: int) -> None:
        """Scroll the rendered detail panel."""
        self._detail_wrap.scroll_relative(y=delta, animate=False)

    def is_tree_mode(self) -> bool:
        """Return whether keyboard navigation is driving the left tree."""
        return True

    def focus_tree_mode(self) -> None:
        """Route keyboard focus to the JSON tree."""
        self._ensure_tree_cursor()
        if self.is_attached:
            self._tree.focus(scroll_visible=False)

    def focus_detail_mode(self) -> None:
        """Keep compatibility with callers that expect a detail-focus method."""
        self.focus_tree_mode()

    def handle_vertical_key(self, delta: int) -> bool:
        """Handle up/down keys by moving the JSON tree cursor."""
        self._ensure_tree_cursor()
        if delta < 0:
            self._tree.action_cursor_up()
        else:
            self._tree.action_cursor_down()
        return True

    def handle_horizontal_key(self, key: str) -> bool:
        """Handle left/right tree navigation."""
        node = self._tree.cursor_node
        if node is None:
            return False
        if key == "left":
            if node.allow_expand and node.is_expanded:
                node.collapse()
            elif node.parent is not None:
                self._tree.move_cursor(node.parent, animate=False)
            return True
        if key == "right":
            if node.allow_expand and node.is_collapsed:
                node.expand()
            elif node.children:
                self._tree.move_cursor(node.children[0], animate=False)
            return True
        return False

    def handle_enter_key(self) -> bool:
        """Consume Enter without switching JSON focus modes."""
        self._ensure_tree_cursor()
        return True

    def handle_escape_key(self) -> bool:
        """Consume Escape without switching JSON focus modes."""
        return True

    def handle_annotation_key(self) -> bool:
        """Open the annotation editor for the active JSON node."""
        item = self._annotation_item()
        if item is None:
            return False
        path = self._annotation_key(item)
        if path is None:
            self.app.notify("Annotations unavailable for this node", severity="warning")
            return True
        self.app.push_screen(
            AnnotationEditor(
                path,
                self._annotation_for_item(item),
                item,
                on_submit=self._handle_annotation_result,
            )
        )
        return True

    def _ensure_tree_cursor(self) -> None:
        """Keep the tree cursor on the first visible child instead of the root."""
        cursor = self._tree.cursor_node
        if (cursor is None or cursor.is_root) and self._tree.root.children:
            self._tree.move_cursor(self._tree.root.children[0], animate=False)

    def _footer_text(self) -> Text:
        """Build the JSON-inspector footer text."""
        text = Text()
        text.append(" JSON ", style="reverse")
        text.append(" ")
        text.append("↑↓", style="bold")
        text.append(" Move  ")
        text.append("←→", style="bold")
        text.append(" Branch  ")
        text.append("PgUp/Dn", style="bold")
        text.append(" Scroll  ")
        text.append("a", style="bold")
        text.append(" Annotate")
        return text

    def _update_footer(self) -> None:
        """Refresh the local footer."""
        self._footer.update(self._footer_text())

    def _build_tree(self) -> None:
        """Populate the unified JSON tree."""
        self._tree.root.expand()
        self._add_overlay_children(self._tree.root, self.data, ())
        self._add_raw_children(self._tree.root, self.data, ())

    def _add_overlay_children(
        self,
        parent: TextualTree.Node[JsonInspectorItem],
        value: Any,
        raw_path: tuple[str | int, ...],
    ) -> None:
        """Add synthetic schema-aware nodes before the raw children."""
        if raw_path == () and _looks_like_bundle(value):
            item = JsonInspectorItem(
                kind="bundle_summary",
                title="Bundle Summary",
                raw_path=raw_path,
                raw_value=value,
                detail=_bundle_summary(value),
                synthetic=True,
            )
            parent.add_leaf(
                self._tree_label_for_item(item),
                data=item,
            )
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
            parent.add_leaf(
                self._tree_label_for_item(item),
                data=item,
            )
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
            parent.add_leaf(
                self._tree_label_for_item(item),
                data=item,
            )
            return

        trajectory, base_path = _overlay_trajectory_target(self.data, value, raw_path)
        if trajectory is not None:
            self._add_trajectory_overlay(parent, trajectory, base_path)

    def _add_trajectory_overlay(
        self,
        parent: TextualTree.Node[JsonInspectorItem],
        trajectory: dict[str, Any],
        base_path: tuple[str | int, ...],
    ) -> None:
        """Add summary and step nodes for a trajectory object."""
        metadata_item = JsonInspectorItem(
            kind="trajectory_metadata",
            title="Metadata",
            raw_path=base_path + ("metadata",),
            raw_value=trajectory.get("metadata"),
            trajectory_item=TrajectoryTreeItem(
                "metadata",
                "Metadata",
                _metadata_detail(trajectory),
            ),
            synthetic=True,
        )
        parent.add_leaf(
            self._tree_label_for_item(metadata_item),
            data=metadata_item,
        )
        final_output_item = JsonInspectorItem(
            kind="trajectory_final_output",
            title="Final Output",
            raw_path=base_path + ("final_output",),
            raw_value=trajectory.get("final_output"),
            trajectory_item=TrajectoryTreeItem(
                "final_output",
                "Final Output",
                _final_output_detail(trajectory),
            ),
            synthetic=True,
        )
        parent.add_leaf(
            self._tree_label_for_item(final_output_item),
            data=final_output_item,
        )

        step_items = normalize_step_timeline(trajectory)
        step_events = normalize_step_events(trajectory)
        steps = trajectory.get("steps", []) if isinstance(trajectory.get("steps"), list) else []
        for step_index, (items, events) in enumerate(zip(step_items, step_events, strict=False)):
            step_path = base_path + ("steps", step_index)
            step_raw_value = steps[step_index] if step_index < len(steps) else None
            step_item = JsonInspectorItem(
                kind="trajectory_step",
                title=f"Step {step_index + 1}",
                raw_path=step_path,
                raw_value=step_raw_value,
                trajectory_item=TrajectoryTreeItem(
                    "step",
                    f"Step {step_index + 1}",
                    Text(f"Step {step_index + 1}\n\n{len(items)} items"),
                ),
                synthetic=True,
            )
            step = parent.add(
                self._tree_label_for_item(step_item),
                data=step_item,
                expand=True,
            )
            for item in items:
                if item.interaction is not None:
                    call_event = item.interaction.call_event
                    result_event = item.interaction.result_event
                    call_path = _trajectory_event_path(base_path, step_index, events, call_event)
                    result_path = _trajectory_event_path(
                        base_path, step_index, events, result_event
                    )
                    parent_path = call_path or result_path or step_path
                    tool_item = JsonInspectorItem(
                        kind="trajectory_tool",
                        title=item.title.plain,
                        raw_path=parent_path,
                        raw_value=_interaction_payload(item.interaction),
                        trajectory_item=TrajectoryTreeItem(
                            "tool",
                            item.title.plain,
                            interaction=item.interaction,
                            focus="full",
                        ),
                        synthetic=True,
                        annotation_path=parent_path,
                    )
                    tool = step.add(
                        self._tree_label_for_item(tool_item),
                        data=tool_item,
                        expand=True,
                    )
                    input_item = JsonInspectorItem(
                        kind="trajectory_tool_input",
                        title="Input",
                        raw_path=call_path or parent_path,
                        raw_value=call_event.raw if call_event else None,
                        trajectory_item=TrajectoryTreeItem(
                            "tool_input",
                            "Input",
                            interaction=item.interaction,
                            focus="input",
                        ),
                        synthetic=True,
                        annotation_path=call_path or parent_path,
                    )
                    tool.add_leaf(
                        self._tree_label_for_item(input_item),
                        data=input_item,
                    )
                    output_item = JsonInspectorItem(
                        kind="trajectory_tool_output",
                        title="Output",
                        raw_path=result_path or parent_path,
                        raw_value=result_event.raw if result_event else None,
                        trajectory_item=TrajectoryTreeItem(
                            "tool_output",
                            "Output",
                            interaction=item.interaction,
                            focus="output",
                        ),
                        synthetic=True,
                        annotation_path=result_path or parent_path,
                    )
                    tool.add_leaf(
                        self._tree_label_for_item(output_item),
                        data=output_item,
                    )
                    continue

                if item.event is not None:
                    event_path = _trajectory_event_path(base_path, step_index, events, item.event)
                    event_item = JsonInspectorItem(
                        kind="trajectory_event",
                        title=item.title.plain,
                        raw_path=event_path or step_path,
                        raw_value=item.event.raw,
                        trajectory_item=TrajectoryTreeItem(
                            "event",
                            item.title.plain,
                            event=item.event,
                        ),
                        synthetic=True,
                        annotation_path=event_path or step_path,
                    )
                    step.add_leaf(
                        self._tree_label_for_item(event_item),
                        data=event_item,
                    )

    def _add_raw_children(
        self,
        parent: TextualTree.Node[JsonInspectorItem],
        value: Any,
        raw_path: tuple[str | int, ...],
    ) -> None:
        """Recursively add raw JSON structure nodes to the tree."""
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = raw_path + (key,)
                item = JsonInspectorItem(
                    kind="raw_dict_key",
                    title=_json_display_key(key),
                    raw_path=child_path,
                    raw_value=child,
                    key=key,
                )
                label = self._tree_label_for_item(item)
                if isinstance(child, dict | list):
                    node = parent.add(label, data=item)
                    self._add_overlay_children(node, child, child_path)
                    self._add_raw_children(node, child, child_path)
                else:
                    parent.add_leaf(label, data=item)
            return

        if isinstance(value, list):
            for index, child in enumerate(value):
                child_path = raw_path + (index,)
                item = JsonInspectorItem(
                    kind="raw_list_item",
                    title=_list_item_title(self.data, raw_path, index, child),
                    raw_path=child_path,
                    raw_value=child,
                    key=str(index),
                )
                label = self._tree_label_for_item(item)
                if isinstance(child, dict | list):
                    node = parent.add(label, data=item)
                    self._add_overlay_children(node, child, child_path)
                    self._add_raw_children(node, child, child_path)
                else:
                    parent.add_leaf(label, data=item)

    def _detail_widgets_for_item(self, item: JsonInspectorItem) -> list[Widget]:
        """Return detail widgets for one selected JSON node."""
        return _json_detail_widgets(item)

    def _annotation_widgets_for_item(self, item: JsonInspectorItem) -> list[Widget]:
        """Return annotation-panel widgets for one selected JSON node."""
        return _annotation_panel_widgets(
            self._annotation_for_item(item),
            self._is_annotatable(item),
        )

    def _annotation_item(self) -> JsonInspectorItem | None:
        """Return the active item for the annotation action."""
        if self.is_tree_mode():
            self._ensure_tree_cursor()
            node = self._tree.cursor_node
            if node is not None and isinstance(node.data, JsonInspectorItem):
                return node.data
        return self._current_item

    def _is_annotatable(self, item: JsonInspectorItem) -> bool:
        """Return whether the item can be annotated in the MVP."""
        return item.annotation_path is not None or not item.synthetic

    def _annotation_key(self, item: JsonInspectorItem) -> str | None:
        """Return the persisted annotation key for one item."""
        if not self._is_annotatable(item):
            return None
        return _format_raw_path(item.annotation_path or item.raw_path)

    def _annotation_for_item(self, item: JsonInspectorItem) -> AnnotationRecord | None:
        """Return the stored annotation for one item, if any."""
        if self.source_path is None:
            return None
        path = self._annotation_key(item)
        if path is None:
            return None
        return self._annotation_store.get_annotation(self.source_path, path)

    def _tree_label_for_item(self, item: JsonInspectorItem) -> Text:
        """Return the rendered tree label for one item, including annotation state."""
        label = _json_tree_label(self.data, item)
        if self._annotation_for_item(item) is None:
            return label
        marked = Text("* ", style="bold green")
        marked.append_text(label)
        return marked

    def _handle_annotation_result(self, result: AnnotationEditorResult | None) -> None:
        """Apply a modal annotation result to the current selection."""
        item = self._annotation_item()
        if item is None or result is None or self.source_path is None:
            return
        path = self._annotation_key(item)
        if path is None:
            return
        if result.action == "delete":
            self._annotation_store.delete_annotation(self.source_path, path)
        elif result.action == "save":
            self._annotation_store.set_annotation(
                self.source_path,
                path,
                tags=result.tags,
                note=result.note,
            )
        else:
            return
        self._refresh_annotation_labels(path)
        self._show_detail(item)

    def _refresh_annotation_labels(self, path: str | None = None) -> None:
        """Refresh annotation markers for all tree nodes or one target path."""
        for node in _walk_tree_nodes(self._tree.root):
            item = node.data
            if not isinstance(item, JsonInspectorItem):
                continue
            item_path = self._annotation_key(item)
            if path is not None and item_path != path:
                continue
            node.set_label(self._tree_label_for_item(item))


def _json_detail_widgets(item: JsonInspectorItem) -> list[Widget]:
    """Return detail widgets for a selected JSON-inspector node."""
    path = _format_raw_path(item.annotation_path or item.raw_path)
    title = Text(item.title or "JSON", style="bold")
    widgets: list[Widget] = [Static(title, classes="trajectory-detail-heading")]
    metadata = [("Path", path)]
    if item.trajectory_item is None:
        metadata.append(("Type", _json_type_name(item.raw_value)))
    widgets.extend(_metadata_fields(metadata))

    if item.trajectory_item is not None:
        widgets.extend(_detail_widgets_for_item(item.trajectory_item))
        return widgets

    value = item.detail if item.synthetic and item.detail is not None else item.raw_value
    if item.synthetic and isinstance(value, dict | list):
        widgets.extend(_render_structured_detail(value, nested=False))
        return widgets
    if item.key:
        widgets.extend(_render_keyed_value(item.key, value))
    else:
        widgets.extend(_render_payload_detail(value))
    return widgets


def _annotation_panel_widgets(
    annotation: AnnotationRecord | None,
    annotatable: bool,
) -> list[Widget]:
    """Return the separate annotation-status panel for one selected JSON node."""
    widgets: list[Widget] = [
        Static(Text("Annotation", style="bold"), classes="annotation-status-title")
    ]
    if not annotatable:
        widgets.extend(
            _metadata_fields([("Status", "Unavailable")])
            + [
                Static(
                    Text("Summary nodes do not map to raw JSON targets."),
                    classes="annotation-status-body",
                ),
                Static(
                    Text("Select a raw or mapped overlay node to annotate.", style="dim"),
                    classes="annotation-status-hint",
                ),
            ]
        )
        return widgets

    if annotation is None:
        widgets.extend(_metadata_fields([("Status", "No annotation"), ("Tags", "(none)")]))
        widgets.append(
            Static(Text("No annotation yet"), classes="annotation-status-body")
        )
        widgets.append(
            Static(Text("Press a to annotate", style="dim"), classes="annotation-status-hint")
        )
        return widgets

    widgets.extend(
        _metadata_fields(
            [
                ("Status", "Annotated"),
                ("Tags", ", ".join(annotation.tags) if annotation.tags else "(none)"),
            ]
        )
    )
    note = Text()
    note.append("Note: ", style="bold cyan")
    note.append(annotation.note or "(empty)")
    widgets.append(Static(note, classes="annotation-status-body"))
    widgets.append(Static(Text("Press a to edit", style="dim"), classes="annotation-status-hint"))
    return widgets


def _json_tree_label(root_data: Any, item: JsonInspectorItem) -> Text:
    """Return the base tree label for one JSON-inspector node."""
    if item.kind == "raw_dict_key":
        return _dict_tree_label(item.key, item.raw_value)
    if item.kind == "raw_list_item":
        index = item.raw_path[-1] if item.raw_path else 0
        if isinstance(index, int):
            return _list_tree_label(root_data, item.raw_path[:-1], index, item.raw_value)
    if item.kind in {
        "bundle_summary",
        "submission_summary",
        "transcript_summary",
        "trajectory_metadata",
        "trajectory_final_output",
    }:
        return Text(item.title, style="bold cyan")
    if item.kind in {"trajectory_step", "trajectory_tool_input", "trajectory_tool_output"}:
        return Text(item.title, style="bold yellow")
    return Text(item.title)


def _walk_tree_nodes(
    node: TextualTree.Node[JsonInspectorItem],
) -> list[TextualTree.Node[JsonInspectorItem]]:
    """Return the supplied node and all descendants."""
    nodes = [node]
    for child in node.children:
        nodes.extend(_walk_tree_nodes(child))
    return nodes


def _parse_annotation_tags(raw_tags: str) -> tuple[str, ...]:
    """Parse the comma-separated tag field used by the modal editor."""
    return tuple(tag.strip() for tag in raw_tags.split(",") if tag.strip())


def _json_type_name(value: Any) -> str:
    """Return a short JSON-oriented type name."""
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    return type(value).__name__


def _format_raw_path(path: tuple[str | int, ...]) -> str:
    """Format a stable raw path for display."""
    if not path:
        return "$"
    result = "$"
    for segment in path:
        if isinstance(segment, int):
            result += f"[{segment}]"
        elif segment.isidentifier():
            result += f".{segment}"
        else:
            escaped = segment.replace("\\", "\\\\").replace('"', '\\"')
            result += f'["{escaped}"]'
    return result


def _json_display_key(key: str) -> str:
    """Return a user-facing label for a raw JSON field."""
    special = {
        "agentic_grader_guidance": "Grader Guidance",
        "callId": "Call ID",
        "completed": "Completed",
        "context_files_draft": "Context Files URL",
        "conversations": "Conversations",
        "export_task_data_json": "Exported Task Data",
        "final_output": "Final Output",
        "from": "From",
        "load_trajectories_s3": "Trajectory URL",
        "model": "Model",
        "prompt": "Prompt",
        "quick_scores": "Quick Scores",
        "quick_stats": "Quick Stats",
        "setup_files_url": "Setup Files URL",
        "submission_type": "Submission Type",
        "task_data_review_report": "Task Data Review Report",
        "task_name": "Task Name",
        "task_solution": "Task Solution",
        "timestamp": "Timestamp",
        "trajectory": "Trajectory",
        "value": "Value",
    }
    if key in special:
        return special[key]
    return key.replace("_", " ").title()


def _dict_tree_label(key: str, value: Any) -> Text:
    """Return a styled tree label for a dictionary child."""
    label = Text(_json_display_key(key), style="bold cyan")
    excerpt = _raw_excerpt(value)
    if excerpt:
        label.append(f" {excerpt}", style="default")
    return label


def _list_tree_label(
    root_data: Any,
    parent_path: tuple[str | int, ...],
    index: int,
    value: Any,
) -> Text:
    """Return a styled tree label for a list child."""
    title = _list_item_title(root_data, parent_path, index, value)
    label = Text(title, style="bold cyan")
    excerpt = _raw_excerpt(value)
    if excerpt and title == f"[{index}]":
        label.append(f" {excerpt}", style="default")
    return label


def _list_item_title(
    root_data: Any,
    parent_path: tuple[str | int, ...],
    index: int,
    value: Any,
) -> str:
    """Return a human-facing title for one list item."""
    if parent_path == () and _looks_like_bundle(root_data):
        return _bundle_item_title(index, value)
    if parent_path == ("conversations",) and _looks_like_hermes(root_data):
        return _hermes_item_title(index, value)
    return f"[{index}]"


def _bundle_item_title(index: int, value: Any) -> str:
    """Return a human label for one trajectory bundle item."""
    if not isinstance(value, dict):
        return f"[{index}]"
    trajectory = _try_decode_json(str(value.get("trajectory", "")))
    if not isinstance(trajectory, dict):
        return f"[{index}] Run"
    metadata = trajectory.get("metadata", {})
    model = metadata.get("llm_model") or metadata.get("llm_provider") or "run"
    trajectory_id = str(metadata.get("trajectory_id") or "")
    suffix = trajectory_id[-6:] if trajectory_id else str(index + 1)
    return f"[{index}] {model} #{suffix}"


def _hermes_item_title(index: int, value: Any) -> str:
    """Return a human label for one Hermes conversation item."""
    if not isinstance(value, dict):
        return f"[{index}]"
    speaker = str(value.get("from") or "entry").title()
    excerpt = _clip(_single_line(str(value.get("value") or "")), 48)
    return f"[{index}] {speaker}" if not excerpt else f"[{index}] {speaker} {excerpt}"


def _raw_excerpt(value: Any) -> str:
    """Return a short inline excerpt for raw JSON tree labels."""
    if isinstance(value, str):
        return _clip(_single_line(value), 48)
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "null"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return f"[{len(value)}]"
    if isinstance(value, dict):
        return f"{{{len(value)}}}"
    return ""


def _overlay_trajectory_target(
    root_data: Any,
    value: Any,
    raw_path: tuple[str | int, ...],
) -> tuple[dict[str, Any] | None, tuple[str | int, ...]]:
    """Return a trajectory value and raw base path for synthetic overlays."""
    if raw_path == ():
        if isinstance(root_data, dict) and not _is_bare_trajectory(root_data):
            wrapped = extract_trajectory(root_data)
            if wrapped is not None:
                return wrapped, ("trajectory",)
        if _is_bare_trajectory(value):
            return value, raw_path
        return None, raw_path

    if raw_path == ("trajectory",) and isinstance(root_data, dict):
        return None, raw_path

    if _is_bare_trajectory(value):
        return value, raw_path
    return None, raw_path


def _is_bare_trajectory(value: Any) -> bool:
    """Return whether a dictionary is a bare trajectory object."""
    return isinstance(value, dict) and isinstance(value.get("steps"), list)


def _looks_like_submission(value: Any) -> bool:
    """Return whether a JSON value looks like a submission artifact."""
    keys = {
        "agentic_grader_guidance",
        "prompt",
        "quick_scores",
        "submission_type",
        "task_name",
    }
    return isinstance(value, dict) and any(key in value for key in keys)


def _looks_like_bundle(value: Any) -> bool:
    """Return whether a JSON value looks like a trajectory bundle array."""
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(item, dict)
            and isinstance(item.get("task"), str)
            and isinstance(item.get("trajectory"), str)
            for item in value
        )
    )


def _looks_like_hermes(value: Any) -> bool:
    """Return whether a JSON value looks like the Hermes transcript sample."""
    return (
        isinstance(value, dict)
        and isinstance(value.get("conversations"), list)
        and any(key in value for key in ("model", "timestamp", "completed"))
    )


def _submission_summary_payload(value: dict[str, Any]) -> dict[str, Any]:
    """Return a compact submission summary payload for detail rendering."""
    summary: dict[str, Any] = {}
    for key in (
        "task_name",
        "submission_type",
        "quick_scores",
        "quick_stats",
        "prompt",
        "agentic_grader_guidance",
        "task_solution",
        "load_trajectories_s3",
        "export_task_data_json",
    ):
        if key in value and value[key] not in (None, ""):
            summary[key] = value[key]
    return summary


def _bundle_summary(value: list[Any]) -> dict[str, Any]:
    """Return a compact summary for a trajectory bundle file."""
    models: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        trajectory = _try_decode_json(str(item.get("trajectory", "")))
        if not isinstance(trajectory, dict):
            continue
        model = trajectory.get("metadata", {}).get("llm_model")
        if model and model not in models:
            models.append(str(model))
    return {
        "runs": len(value),
        "models": ", ".join(models) if models else "(unknown)",
    }


def _hermes_summary(value: dict[str, Any]) -> dict[str, Any]:
    """Return a compact summary for a Hermes transcript."""
    return {
        "model": value.get("model"),
        "timestamp": value.get("timestamp"),
        "completed": value.get("completed"),
        "conversations": len(value.get("conversations", [])),
    }


def _trajectory_event_path(
    base_path: tuple[str | int, ...],
    step_index: int,
    events: list[TrajectoryEvent],
    event: TrajectoryEvent | None,
) -> tuple[str | int, ...] | None:
    """Return the raw path for one normalized trajectory event."""
    if event is None:
        return None
    for output_index, candidate in enumerate(events):
        if candidate.raw is event.raw:
            return base_path + ("steps", step_index, "output", output_index)
    return None


def _interaction_payload(interaction: ToolInteraction) -> dict[str, Any]:
    """Return a compact combined payload for one tool interaction."""
    return {
        "tool": interaction.tool_name,
        "call_id": interaction.call_id,
        "input": interaction.call_event.raw if interaction.call_event else None,
        "output": interaction.result_event.raw if interaction.result_event else None,
    }
