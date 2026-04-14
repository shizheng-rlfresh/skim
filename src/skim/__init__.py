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
class TrajectoryTreeItem:
    """Data attached to a trajectory tree node."""

    kind: str
    title: str
    detail: Any
    event: TrajectoryEvent | None = None


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
    if item.event is not None:
        return _event_detail_widgets(item.event)
    if isinstance(item.detail, Text):
        return [Static(item.detail, classes="trajectory-detail")]
    if isinstance(item.detail, str):
        return _render_string_detail(item.detail)
    return _render_payload_detail(item.detail)


def _event_detail_widgets(event: TrajectoryEvent) -> list[Widget]:
    header = Text(f"{event.index + 1}. {event.kind}")
    if event.label:
        header.append(f"\nlabel: {event.label}")
    widgets: list[Widget] = [Static(header, classes="trajectory-detail-heading")]

    if event.kind == "function_call":
        widgets.extend(_function_call_detail_widgets(event.raw))
    elif event.kind == "function_call_result":
        widgets.extend(_function_call_result_detail_widgets(event.raw))
    else:
        text = _event_text(event.raw)
        if text:
            widgets.extend(_render_string_detail(text))
        else:
            widgets.extend(_render_payload_detail(_event_payload(event.raw)))
    return widgets


def _function_call_detail_widgets(raw: dict[str, Any]) -> list[Widget]:
    widgets = _tool_identity_widgets(raw)
    decoded = _decode_nested_json(raw.get("arguments"))

    if isinstance(decoded, dict):
        command = decoded.get("command")
        rest = {key: value for key, value in decoded.items() if key != "command"}
        if isinstance(command, str) and command.strip():
            widgets.append(_detail_heading("Command"))
            widgets.append(
                Static(Syntax(command, "bash", word_wrap=True), classes="trajectory-detail")
            )
        if rest:
            widgets.append(_detail_heading("Arguments"))
            widgets.extend(_render_payload_detail(rest))
        elif not isinstance(command, str):
            widgets.extend(_render_payload_detail(decoded))
    else:
        widgets.extend(_render_payload_detail(decoded))
    return widgets


def _function_call_result_detail_widgets(raw: dict[str, Any]) -> list[Widget]:
    widgets = _tool_identity_widgets(raw)
    decoded = _decoded_tool_result(raw.get("output"))

    if isinstance(decoded, dict):
        handled = False
        for key in ("returncode", "stdout", "stderr"):
            if key not in decoded:
                continue
            handled = True
            widgets.append(_detail_heading(key))
            value = decoded[key]
            if isinstance(value, str):
                widgets.extend(_render_string_detail(value))
            else:
                widgets.extend(_render_payload_detail(value))
        rest = {
            key: value
            for key, value in decoded.items()
            if key not in {"returncode", "stdout", "stderr"}
        }
        if rest:
            widgets.append(_detail_heading("Output"))
            widgets.extend(_render_payload_detail(rest))
        if handled:
            return widgets

    widgets.extend(_render_payload_detail(decoded))
    return widgets


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


def _render_payload_detail(value: Any) -> list[Widget]:
    decoded = _decode_nested_json(value)
    if isinstance(decoded, dict | list):
        return [
            Static(
                Syntax(json.dumps(decoded, indent=2), "json", word_wrap=True),
                classes="trajectory-detail",
            )
        ]
    if decoded is None:
        return [Static(Text(""))]
    return _render_string_detail(str(decoded))


def _render_string_detail(value: str) -> list[Widget]:
    if not value:
        return [Static(Text(""))]

    decoded = _try_decode_json(value)
    if isinstance(decoded, dict | list):
        return [
            Static(
                Syntax(json.dumps(decoded, indent=2), "json", word_wrap=True),
                classes="trajectory-detail",
            )
        ]

    if _looks_like_markdown(value):
        return [Markdown(value, classes="trajectory-markdown")]
    return [Static(Text(value), classes="trajectory-detail")]


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


def _detail_heading(label: str) -> Static:
    return Static(Text(label, style="bold"), classes="trajectory-detail-heading")


def _event_tree_label(event: TrajectoryEvent) -> str:
    label = f" {event.label}" if event.label else ""
    return f"{event.index + 1:03d} {event.kind}{label} {event.excerpt}"


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
        for step_index, events in enumerate(self.step_events, start=1):
            step = self._tree.root.add(
                f"Step {step_index}",
                data=TrajectoryTreeItem(
                    "step",
                    f"Step {step_index}",
                    Text(f"Step {step_index}\n\n{len(events)} events"),
                ),
                expand=True,
            )
            for event in events:
                step.add_leaf(
                    _event_tree_label(event),
                    data=TrajectoryTreeItem(
                        "event",
                        _event_tree_label(event),
                        None,
                        event=event,
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
