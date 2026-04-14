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
from textual.widgets import DirectoryTree, Header, Markdown, Static

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


def _metadata_summary(trajectory: dict[str, Any]) -> str:
    metadata = trajectory.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    provider = metadata.get("llm_provider")
    model = metadata.get("llm_model")
    model_line = " / ".join(str(value) for value in (provider, model) if value)
    compactions = trajectory.get("context_compaction_events")
    compaction_count = len(compactions) if isinstance(compactions, list) else 0

    lines = ["Trajectory"]
    if model_line:
        lines.append(f"model: {model_line}")
    for key in ("trajectory_id", "task_id", "input_tokens", "output_tokens"):
        value = metadata.get(key)
        if value is not None:
            lines.append(f"{key}: {value}")
    lines.append(f"compactions: {compaction_count}")

    final_output = trajectory.get("final_output")
    if isinstance(final_output, str) and final_output.strip():
        lines.extend(["", "Final Output", _clip(final_output.strip(), 4_000)])
    return "\n".join(lines)


def _event_detail(event: TrajectoryEvent) -> Text:
    lines = [
        f"{event.index + 1}. {event.kind}",
        f"label: {event.label}" if event.label else "",
        "",
    ]

    text = _event_text(event.raw)
    if text:
        lines.append(text)
    else:
        lines.append(_format_payload(_event_payload(event.raw)))
    return Text("\n".join(line for line in lines if line is not None))


def _format_submission(data: dict[str, Any]) -> Text:
    lines = ["Submission Summary"]
    for key, title in SUBMISSION_SECTIONS:
        value = data.get(key)
        if value in (None, ""):
            continue
        lines.extend(["", title, _format_payload(value)])
    return Text("\n".join(lines))


class TrajectoryEventItem(Static):
    """Clickable item for a normalized trajectory event."""

    def __init__(
        self, event: TrajectoryEvent, viewer: "TrajectoryViewer", selected: bool = False
    ) -> None:
        """Initialize an event row."""
        self.event = event
        self.viewer = viewer
        super().__init__(self._render_row(selected=selected), classes="trajectory-event")

    async def on_click(self) -> None:
        """Select this event in the parent trajectory viewer."""
        self.viewer.select_event(self.event.index)

    def _set_selected(self, selected: bool) -> None:
        self.update(self._render_row(selected=selected))

    def _render_row(self, selected: bool) -> Text:
        marker = ">" if selected else " "
        label = f" {self.event.label}" if self.event.label else ""
        return Text(
            f"{marker} {self.event.index + 1:03d} {self.event.kind}{label} {self.event.excerpt}"
        )


class TrajectoryViewer(Vertical):
    """Structured preview for a single raw trajectory."""

    def __init__(self, trajectory: dict[str, Any]) -> None:
        """Initialize the trajectory viewer."""
        super().__init__(classes="trajectory-viewer")
        self.trajectory = trajectory
        self.events = normalize_events(trajectory)
        self.selected_index = 0 if self.events else -1
        self._summary = Static(Text(_metadata_summary(trajectory)), classes="trajectory-summary")
        self.detail_text = _event_detail(self.events[0]) if self.events else Text("No events")
        self._detail = Static(self.detail_text, classes="trajectory-detail")
        self._event_items = [
            TrajectoryEventItem(event, self, selected=event.index == self.selected_index)
            for event in self.events
        ]

    def compose(self) -> ComposeResult:
        """Compose the trajectory summary, event list, and detail panel."""
        yield self._summary
        with Horizontal(classes="trajectory-body"):
            with VerticalScroll(classes="trajectory-events"):
                yield from self._event_items
            with VerticalScroll(classes="trajectory-detail-wrap"):
                yield self._detail

    def select_event(self, index: int) -> None:
        """Select an event and update the detail panel."""
        if index < 0 or index >= len(self.events):
            return
        self.selected_index = index
        for item in self._event_items:
            item._set_selected(item.event.index == index)
        self.detail_text = _event_detail(self.events[index])
        self._detail.update(self.detail_text)


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
