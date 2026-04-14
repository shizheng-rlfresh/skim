"""skim: A TUI for browsing folders and previewing files."""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.syntax import Syntax
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Key
from textual.widget import Widget
from textual.widgets import DirectoryTree, Header, Markdown, Static, Tree

SYNTAX_MAP = {
    ".py": "python",
    ".json": "json",
    ".js": "javascript",
    ".ts": "typescript",
    ".html": "html",
    ".css": "css",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".sh": "bash",
    ".bash": "bash",
    ".rs": "rust",
    ".go": "go",
    ".sql": "sql",
    ".xml": "xml",
    ".csv": "csv",
}

MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdown"}
MAX_FILE_SIZE = 1_000_000
MAX_ROWS = 2
MAX_COLS = 3
SCROLL_STEP = 3
HUMAN_TEXT_KEYS = {
    "arguments",
    "code",
    "command",
    "content",
    "markdown",
    "output",
    "pages",
    "result",
    "stderr",
    "stdout",
    "text",
}
WRAPPER_KEYS = ("arguments", "content", "output", "result", "text")
SUBMISSION_KEYS = {
    "agentic_grader_guidance",
    "prompt",
    "quick_scores",
    "submission_type",
    "task_name",
}
SUBMISSION_SECTIONS = [
    ("task_name", "Task"),
    ("submission_type", "Submission"),
    ("quick_scores", "Quick Scores"),
    ("quick_stats", "Quick Stats"),
    ("task_data_review", "Task Data Review"),
    ("prompt", "Prompt"),
    ("agentic_grader_guidance", "Grader Guidance"),
    ("task_solution", "Task Solution"),
    ("task_performance", "Task Performance"),
    ("grader_reliability", "Grader Reliability"),
    ("grader_reliability_explanation", "Grader Reliability Explanation"),
    ("load_trajectories_s3", "Trajectory URL"),
    ("setup_files_url", "Setup Files URL"),
    ("load_trajectories_s3_agentic_grader_results", "Grader Results URL"),
    ("evaluation_files_url", "Evaluation Files URL"),
    ("context_files_draft", "Context Files URL"),
]


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


def render_file(path: Path) -> list[Widget]:
    """Return a list of widgets for the given file."""
    if not path.is_file():
        return [Static(Text(f"Not a file: {path.name}", style="red"))]

    size = path.stat().st_size
    if size > MAX_FILE_SIZE:
        return [Static(Text(f"{path.name} is too large ({size:,} bytes)", style="red"))]

    try:
        content = path.read_text(errors="replace")
    except Exception as e:
        return [Static(Text(f"Could not read {path.name}: {e}", style="red"))]

    suffix = path.suffix.lower()

    if suffix in MARKDOWN_EXTENSIONS:
        return [Markdown(content)]

    if suffix == ".json":
        try:
            parsed = json.loads(content)
            widget = _specialized_json_widget(parsed)
            if widget is not None:
                return [widget]
            content = json.dumps(parsed, indent=2)
        except json.JSONDecodeError:
            pass

    lexer = SYNTAX_MAP.get(suffix)
    if lexer:
        return [Static(Syntax(content, lexer, line_numbers=True, word_wrap=True))]
    return [Static(Text(content))]


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
    """Return step items with paired tool interactions."""
    timeline_groups: list[list[StepTimelineItem]] = []
    for events in normalize_step_events(trajectory):
        group: list[StepTimelineItem] = []
        pending_calls: dict[str, int] = {}
        for event in events:
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


def _specialized_json_widget(data: Any) -> Widget | None:
    trajectory = _extract_trajectory(data)
    if trajectory is not None:
        return TrajectoryViewer(trajectory)
    if _is_submission(data):
        return SubmissionSummary(data)
    return None


def _extract_trajectory(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    wrapped = data.get("trajectory")
    if isinstance(wrapped, dict) and isinstance(wrapped.get("steps"), list):
        return wrapped
    if isinstance(data.get("steps"), list):
        return data
    return None


def _is_submission(data: Any) -> bool:
    return isinstance(data, dict) and any(key in data for key in SUBMISSION_KEYS)


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
    widgets.extend(
        _metadata_fields(
            [
                ("Tool", interaction.tool_name),
                ("Call ID", interaction.call_id),
                ("Status", _interaction_status(interaction)),
            ]
        )
    )

    if focus == "output":
        sections = [("Output", interaction.result_event), ("Input", interaction.call_event)]
    elif focus == "input":
        sections = [("Input", interaction.call_event), ("Output", interaction.result_event)]
    else:
        sections = [("Input", interaction.call_event), ("Output", interaction.result_event)]

    for section_title, event in sections:
        widgets.append(_detail_heading(section_title))
        widgets.extend(_tool_section_widgets(event, section_title.lower()))
    return widgets


def _tool_section_widgets(event: TrajectoryEvent | None, focus: str) -> list[Widget]:
    if event is None:
        return [Static(Text(f"No {focus}"), classes="trajectory-detail")]
    if focus == "input":
        return _render_payload_detail(_decode_nested_json(event.raw.get("arguments")))
    return _render_payload_detail(_decoded_tool_result(event.raw.get("output")))


def _decoded_tool_result(output: Any) -> Any:
    decoded = _decode_nested_json(output)
    if isinstance(decoded, dict) and set(decoded) == {"text"}:
        return decoded["text"]
    if (
        isinstance(decoded, dict)
        and isinstance(decoded.get("text"), dict)
        and any(key in decoded["text"] for key in ("stdout", "stderr", "returncode"))
    ):
        return {**decoded, **decoded["text"]}
    return decoded


def _tool_identity_widgets(raw: dict[str, Any]) -> list[Widget]:
    lines = []
    for key in ("name", "callId", "call_id"):
        value = raw.get(key)
        if value:
            lines.append(f"{key}: {value}")
    if not lines:
        return []
    return [Static(Text("\n".join(lines)), classes="trajectory-detail")]


def _metadata_fields(fields: list[tuple[str, str | None]]) -> list[Widget]:
    lines = [f"{label}: {value}" for label, value in fields if value not in (None, "")]
    if not lines:
        return []
    return [Static(Text("\n".join(lines)), classes="trajectory-detail")]


def _render_payload_detail(value: Any) -> list[Widget]:
    decoded = _decode_nested_json(value)
    if isinstance(decoded, dict | list):
        promoted = _promote_wrapper_value(decoded)
        if promoted is not None:
            return _render_structured_detail(promoted)
        if _has_human_text(decoded):
            return _render_structured_detail(decoded)
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
            return _render_structured_detail(promoted)
        if _has_human_text(decoded):
            return _render_structured_detail(decoded)
        return _render_json_block(decoded)

    if _looks_like_markdown(value):
        return [Markdown(value, classes="trajectory-markdown")]
    if _looks_like_preformatted_text(value):
        return [Static(Syntax(value, "text", word_wrap=True), classes="trajectory-detail")]
    return [Static(Text(value), classes="trajectory-detail")]


def _promote_wrapper_value(value: Any) -> Any | None:
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


def _render_structured_detail(value: Any) -> list[Widget]:
    if isinstance(value, dict):
        return _render_dict_sections(value)
    if isinstance(value, list):
        return _render_list_sections(value)
    return _render_payload_detail(value)


def _render_dict_sections(value: dict[str, Any]) -> list[Widget]:
    widgets: list[Widget] = []
    for key, item in value.items():
        decoded = _decode_nested_json(item)
        if _is_empty_value(decoded):
            continue
        widgets.append(_detail_heading(str(key)))
        widgets.extend(_render_keyed_value(str(key), decoded))
    if widgets:
        return widgets
    return _render_json_block(value)


def _render_list_sections(value: list[Any]) -> list[Widget]:
    if not _has_human_text(value):
        return _render_json_block(value)

    widgets: list[Widget] = []
    for index, item in enumerate(value, start=1):
        decoded = _decode_nested_json(item)
        if _is_empty_value(decoded):
            continue
        widgets.append(_detail_heading(f"Item {index}"))
        widgets.extend(_render_keyed_value("", decoded))
    if widgets:
        return widgets
    return _render_json_block(value)


def _render_keyed_value(key: str, value: Any) -> list[Widget]:
    normalized_key = key.lower()
    if isinstance(value, str):
        return _render_keyed_string(normalized_key, value)
    if isinstance(value, dict):
        promoted = _promote_wrapper_value(value)
        if promoted is not None:
            return _render_structured_detail(promoted)
        if _has_human_text(value):
            return _render_dict_sections(value)
        return _render_json_block(value)
    if isinstance(value, list):
        if normalized_key == "pages":
            return _render_pages(value)
        if _has_human_text(value):
            return _render_list_sections(value)
        return _render_json_block(value)
    return [Static(Text(str(value)), classes="trajectory-detail")]


def _render_keyed_string(key: str, value: str) -> list[Widget]:
    decoded = _try_decode_json(value)
    if isinstance(decoded, dict | list):
        promoted = _promote_wrapper_value(decoded)
        if promoted is not None:
            return _render_structured_detail(promoted)
        return (
            _render_structured_detail(decoded)
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
    widgets: list[Widget] = []
    for index, item in enumerate(value, start=1):
        decoded = _decode_nested_json(item)
        widgets.append(_detail_heading(f"Page {index}"))
        widgets.extend(_render_keyed_value("text", decoded))
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
    stripped = value.lstrip()
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


def _detail_heading(label: str) -> Static:
    return Static(Text(label, style="bold"), classes="trajectory-detail-heading")


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


def _format_submission(data: dict[str, Any]) -> Text:
    lines = ["Submission Summary"]
    for key, title in SUBMISSION_SECTIONS:
        value = data.get(key)
        if value in (None, ""):
            continue
        lines.extend(["", title, _format_payload(value)])
    return Text("\n".join(lines))


class TrajectoryViewer(Vertical):
    """Structured preview for a single raw trajectory."""

    def __init__(self, trajectory: dict[str, Any]) -> None:
        """Initialize the trajectory viewer."""
        super().__init__(classes="trajectory-viewer")
        self.trajectory = trajectory
        self.step_events = normalize_step_events(trajectory)
        self.step_items = normalize_step_timeline(trajectory)
        self.events = normalize_events(trajectory)
        self._summary = Static(Text(_metadata_header(trajectory)), classes="trajectory-summary")
        self._tree: Tree[TrajectoryTreeItem] = Tree("Trajectory", classes="trajectory-tree")
        self._build_tree()
        first_item = self._tree.root.children[0].data
        initial_widgets: list[Widget] = []
        if isinstance(first_item, TrajectoryTreeItem):
            initial_widgets = _detail_widgets_for_item(first_item)
        self._detail_wrap = VerticalScroll(*initial_widgets, classes="trajectory-detail-wrap")

    def compose(self) -> ComposeResult:
        """Compose the trajectory summary, event tree, and detail panel."""
        yield self._summary
        with Horizontal(classes="trajectory-body"):
            yield self._tree
            yield self._detail_wrap

    def on_tree_node_selected(self, event: Tree.NodeSelected[TrajectoryTreeItem]) -> None:
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


class SubmissionSummary(Static):
    """Structured preview for a worker submission JSON artifact."""

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize the submission summary."""
        self.data = data
        self.summary_text = _format_submission(data)
        super().__init__(self.summary_text, classes="submission-summary")


class PreviewPane(VerticalScroll, can_focus=True):
    """Scrollable panel that shows file contents."""

    def __init__(self, **kwargs) -> None:
        """Initialize an empty preview pane."""
        super().__init__(**kwargs)
        self.current_path: Path | None = None

    def show_placeholder(self, message: str = "Select a file") -> None:
        """Show placeholder text when no file is selected."""
        self.current_path = None
        self.remove_children()
        self.mount(Static(Text(message, style="dim italic")))

    def show_file(self, path: Path) -> None:
        """Render a file into the pane."""
        self.current_path = path
        self.remove_children()
        for widget in render_file(path):
            self.mount(widget)
        self.scroll_home(animate=False)

    def on_click(self) -> None:
        """Mark this pane as the active preview when clicked."""
        app = self.app
        if isinstance(app, SkimApp) and self.id is not None:
            app.set_active_pane(self.id)


class SkimApp(App):
    """Main application."""

    TITLE = "skim"
    CSS = """
    #outer {
        height: 1fr;
    }
    DirectoryTree {
        width: 1fr;
        max-width: 40;
        border-right: solid $primary-background;
    }
    #preview-area {
        width: 3fr;
    }
    .pane-row {
        height: 1fr;
    }
    PreviewPane {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
        border: round $background;
    }
    PreviewPane.active-pane {
        border: round $accent;
    }
    TrajectoryViewer {
        width: 1fr;
    }
    .trajectory-body {
        height: 1fr;
    }
    .trajectory-tree {
        width: 1fr;
        min-width: 28;
        height: 1fr;
    }
    .trajectory-detail-wrap {
        width: 2fr;
        height: 1fr;
        padding: 0 1;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    .key {
        background: $primary-background;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", show=False),
        Binding("up", "scroll_up", show=False, priority=True),
        Binding("down", "scroll_down", show=False, priority=True),
        Binding("j", "scroll_down", show=False, priority=True),
        Binding("k", "scroll_up", show=False, priority=True),
        Binding("s", "enter_split", show=False),
        Binding("d", "close_pane", show=False),
        Binding("w", "cycle_pane", show=False),
    ]

    STATUS_TEXT = (
        " [bold]q[/] Quit  "
        "[bold]↑↓[/] Scroll  "
        "[bold]⇧↑↓[/] Tree  "
        "[bold]Enter[/] Open  "
        "[bold]s[/]+arrow Split  "
        "[bold]d[/] Close  "
        "[bold]w[/] Next pane"
    )

    def __init__(self, path: str | Path = "."):
        """Initialize the app for a directory path."""
        super().__init__()
        self.browse_path = Path(path).expanduser().resolve()
        self.pane_counter = 0
        self.active_pane_id: str = ""
        self.grid: list[list[str]] = []
        self.pane_files: dict[str, Path | None] = {}
        self.split_mode = False

    def _new_pane_id(self) -> str:
        pid = f"pane-{self.pane_counter}"
        self.pane_counter += 1
        return pid

    def _total_panes(self) -> int:
        return sum(len(row) for row in self.grid)

    def _find_pane(self, pane_id: str) -> tuple[int | None, int | None]:
        for r, row in enumerate(self.grid):
            for c, pid in enumerate(row):
                if pid == pane_id:
                    return r, c
        return None, None

    def compose(self) -> ComposeResult:
        """Compose the directory tree and preview area."""
        yield Header()
        with Horizontal(id="outer"):
            yield DirectoryTree(str(self.browse_path))
            yield Vertical(id="preview-area")
        yield Static(self.STATUS_TEXT, id="status-bar")

    def on_mount(self) -> None:
        """Create the first preview pane and focus the tree."""
        pid = self._new_pane_id()
        self.grid = [[pid]]
        self.pane_files[pid] = None
        self.active_pane_id = pid
        self._rebuild_layout()
        self.query_one(DirectoryTree).focus()

    def _rebuild_layout(self) -> None:
        """Rebuild the preview pane grid from current state."""
        area = self.query_one("#preview-area")
        area.remove_children()
        for row in self.grid:
            h = Horizontal(classes="pane-row")
            area.mount(h)
            for pid in row:
                pane = PreviewPane(id=pid)
                h.mount(pane)
                path = self.pane_files.get(pid)
                if path:
                    pane.show_file(path)
                else:
                    pane.show_placeholder()
        self._update_active_indicator()

    def set_active_pane(self, pane_id: str) -> None:
        """Set the active preview pane by id."""
        self.active_pane_id = pane_id
        self._update_active_indicator()

    def _update_active_indicator(self) -> None:
        for pane in self.query(PreviewPane):
            pane.remove_class("active-pane")
        try:
            self.query_one(f"#{self.active_pane_id}", PreviewPane).add_class("active-pane")
        except Exception:
            pass

    # --- scrolling the active pane ---

    def action_scroll_down(self) -> None:
        """Scroll down in the active pane or confirm a downward split."""
        if self.split_mode:
            self.split_mode = False
            self._split("down")
            return
        try:
            pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
            pane.scroll_relative(y=SCROLL_STEP, animate=False)
        except Exception:
            pass

    def action_scroll_up(self) -> None:
        """Scroll up in the active pane or confirm an upward split."""
        if self.split_mode:
            self.split_mode = False
            self._split("up")
            return
        try:
            pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
            pane.scroll_relative(y=-SCROLL_STEP, animate=False)
        except Exception:
            pass

    # --- tree navigation ---

    def action_tree_up(self) -> None:
        """Move the directory tree cursor up."""
        self.query_one(DirectoryTree).action_cursor_up()

    def action_tree_down(self) -> None:
        """Move the directory tree cursor down."""
        self.query_one(DirectoryTree).action_cursor_down()

    def action_tree_select(self) -> None:
        """Open the currently selected tree item."""
        self.query_one(DirectoryTree).action_select_cursor()

    # --- split mode and tree nav key handler ---

    def on_key(self, event: Key) -> None:
        """Handle split-mode keys and tree navigation shortcuts."""
        if self.split_mode:
            direction_map = {
                "left": "left",
                "right": "right",
                "up": "up",
                "down": "down",
                "h": "left",
                "l": "right",
                "k": "up",
                "j": "down",
            }
            direction = direction_map.get(event.key)
            self.split_mode = False
            if direction:
                self._split(direction)
            event.prevent_default()
            event.stop()
            return

        # shift+arrows navigate the file tree, enter opens
        if event.key == "shift+down":
            self.action_tree_down()
            event.prevent_default()
            event.stop()
        elif event.key == "shift+up":
            self.action_tree_up()
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            self.action_tree_select()
            event.prevent_default()
            event.stop()

    # --- file selection ---

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Open a selected file in the active preview pane."""
        path = Path(event.path)
        pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
        pane.show_file(path)
        self.pane_files[self.active_pane_id] = path

    # --- split ---

    def action_enter_split(self) -> None:
        """Enter split mode for the next direction key."""
        if self._total_panes() >= MAX_ROWS * MAX_COLS:
            self.notify("Maximum 6 panes reached", severity="warning")
            return
        self.split_mode = True
        self.notify("Split: arrow or h/j/k/l, Esc cancel", timeout=2)

    def _split(self, direction: str) -> None:
        r, c = self._find_pane(self.active_pane_id)
        if r is None or c is None:
            return

        new_id = self._new_pane_id()
        self.pane_files[new_id] = None

        if direction in ("left", "right"):
            if len(self.grid[r]) < MAX_COLS:
                pos = c + 1 if direction == "right" else c
                self.grid[r].insert(pos, new_id)
            elif not self._try_overflow(new_id):
                return

        elif direction in ("up", "down"):
            target = 0 if direction == "up" else 1
            if target >= len(self.grid):
                self.grid.append([])
            if len(self.grid[target]) < MAX_COLS:
                insert_at = min(c, len(self.grid[target]))
                self.grid[target].insert(insert_at, new_id)
            elif not self._try_overflow(new_id):
                return

        self.active_pane_id = new_id
        self._rebuild_layout()

    def _try_overflow(self, new_id: str) -> bool:
        for i in range(MAX_ROWS):
            if i < len(self.grid) and len(self.grid[i]) < MAX_COLS:
                self.grid[i].append(new_id)
                return True
            if i >= len(self.grid):
                self.grid.append([new_id])
                return True
        self.notify("No room for new pane", severity="warning")
        return False

    # --- close pane ---

    def action_close_pane(self) -> None:
        """Close the active pane unless it is the last one."""
        if self._total_panes() <= 1:
            self.notify("Cannot close last pane", severity="warning")
            return

        r, c = self._find_pane(self.active_pane_id)
        if r is None or c is None:
            return

        self.pane_files.pop(self.active_pane_id, None)
        self.grid[r].pop(c)
        if not self.grid[r]:
            self.grid.pop(r)

        row_idx = min(r, len(self.grid) - 1)
        col_idx = min(c, len(self.grid[row_idx]) - 1)
        self.active_pane_id = self.grid[row_idx][col_idx]
        self._rebuild_layout()
        try:
            self.query_one(f"#{self.active_pane_id}", PreviewPane).focus()
        except Exception:
            pass

    # --- cycle panes ---

    def action_cycle_pane(self) -> None:
        """Cycle the active pane through the current grid order."""
        all_panes = [pid for row in self.grid for pid in row]
        if len(all_panes) <= 1:
            return
        idx = all_panes.index(self.active_pane_id)
        self.active_pane_id = all_panes[(idx + 1) % len(all_panes)]
        self._update_active_indicator()


def main():
    """Run the app from the command line."""
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    app = SkimApp(path)
    app.run()


def dev():
    """Run the app through Textual's dev server."""
    import subprocess

    subprocess.run(["textual", "run", "--dev", "skim:SkimApp"])
