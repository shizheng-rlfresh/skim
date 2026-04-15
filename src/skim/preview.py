"""File preview routing and non-trajectory preview widgets for skim.

This module owns file reading, generic preview fallbacks, JSON preview dispatch,
and the preview pane container used by the outer app shell. It does not own the
outer multi-pane app behavior or trajectory-specific rendering internals.
"""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any

from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Collapsible, Markdown, Static

from .scrolling import DragScrollMixin
from .trajectory import TrajectoryViewer, extract_trajectory

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
MAX_CSV_ROWS = 20
MAX_CSV_COLS = 8
MAX_CSV_CELL_WIDTH = 24
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


def _decode_nested_json(value: Any) -> Any:
    """Best-effort decode nested JSON strings inside lists and dictionaries."""
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
    """Format a decoded payload for readable fallback text output."""
    decoded = _decode_nested_json(value)
    if isinstance(decoded, dict | list):
        return json.dumps(decoded, indent=2)
    if decoded is None:
        return ""
    return str(decoded)


class SubmissionSummary(Static):
    """Structured preview for a worker submission JSON artifact."""

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize the submission summary."""
        self.data = data
        self.summary_text = _format_submission(data)
        super().__init__(self.summary_text, classes="submission-summary")


class CsvPreview(Vertical):
    """Dual CSV preview with a readable table and raw text fallback."""

    def __init__(self, content: str) -> None:
        """Initialize the CSV preview from raw file content."""
        super().__init__(classes="csv-preview")
        parsed = _parse_csv(content)
        if isinstance(parsed, str):
            self._widgets = _csv_parse_error_widgets(content, parsed)
        else:
            self._widgets = _csv_preview_widgets(content, parsed)

    def compose(self) -> ComposeResult:
        """Compose the CSV preview widgets."""
        yield from self._widgets


class PreviewPane(DragScrollMixin, VerticalScroll, can_focus=True):
    """Scrollable panel that shows file contents."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize an empty preview pane."""
        super().__init__(**kwargs)
        self._init_drag_scroll()
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
        widgets = render_file(path)
        for widget in widgets:
            self.mount(widget)
        self.scroll_home(animate=False)
        if (
            widgets
            and isinstance(widgets[0], TrajectoryViewer)
            and self.id == getattr(self.app, "active_pane_id", None)
        ):
            self.call_after_refresh(widgets[0].focus_tree_mode)

    def on_click(self) -> None:
        """Mark this pane as the active preview when clicked."""
        if self.id is not None and hasattr(self.app, "set_active_pane"):
            self.app.set_active_pane(self.id)

    def scroll_content(self, delta: int) -> None:
        """Scroll specialized inner content when present, else scroll the pane."""
        viewer = self.active_trajectory_viewer()
        if viewer is not None:
            viewer.handle_vertical_key(delta)
        else:
            self.scroll_relative(y=delta, animate=False)

    def active_trajectory_viewer(self) -> TrajectoryViewer | None:
        """Return the mounted trajectory viewer, if this pane has one."""
        try:
            viewer = self.query(TrajectoryViewer).first()
        except NoMatches:
            return None
        return viewer if isinstance(viewer, TrajectoryViewer) else None


def render_file(path: Path) -> list[Widget]:
    """Return a list of widgets for the given file."""
    if not path.is_file():
        return [Static(Text(f"Not a file: {path.name}", style="red"))]

    size = path.stat().st_size
    if size > MAX_FILE_SIZE:
        return [Static(Text(f"{path.name} is too large ({size:,} bytes)", style="red"))]

    try:
        content = path.read_text(errors="replace")
    except Exception as error:
        return [Static(Text(f"Could not read {path.name}: {error}", style="red"))]

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

    if suffix == ".csv":
        return [CsvPreview(content)]

    lexer = SYNTAX_MAP.get(suffix)
    if lexer:
        return [Static(Syntax(content, lexer, line_numbers=True, word_wrap=True))]
    return [Static(Text(content))]


def _parse_csv(content: str) -> list[list[str]] | str:
    """Parse CSV content into rows, returning an error message on failure."""
    try:
        reader = csv.reader(StringIO(content), strict=True)
        return [list(row) for row in reader]
    except csv.Error as error:
        return str(error)


def _csv_preview_widgets(content: str, rows: list[list[str]]) -> list[Widget]:
    """Build the normal CSV preview widgets."""
    if not rows:
        return [
            Static(Text("Empty CSV file", style="dim italic")),
            _raw_csv_section(content),
        ]

    header = rows[0]
    body = rows[1:]
    table = _csv_table(header, body)
    summary = Static(_csv_summary_text(header, body), classes="csv-summary")
    return [
        summary,
        Static(table, classes="csv-table"),
        _raw_csv_section(content),
    ]


def _csv_parse_error_widgets(content: str, error: str) -> list[Widget]:
    """Build the CSV preview widgets for malformed CSV input."""
    return [
        Static(
            Text(f"CSV parse error: {error}", style="bold red"),
            classes="csv-parse-error",
        ),
        _raw_csv_section(content, collapsed=False),
    ]


def _csv_summary_text(header: list[str], body: list[list[str]]) -> Text:
    """Return a short summary for the CSV preview."""
    text = Text()
    text.append("CSV Preview", style="bold")
    text.append(
        f"  {len(body):,} rows x {len(header):,} columns",
        style="dim",
    )
    if len(body) > MAX_CSV_ROWS or len(header) > MAX_CSV_COLS:
        row_count = min(len(body), MAX_CSV_ROWS)
        column_count = min(len(header), MAX_CSV_COLS)
        text.append(
            f"  showing first {row_count} rows and {column_count} columns",
            style="yellow",
        )
    return text


def _csv_table(header: list[str], rows: list[list[str]]) -> Table:
    """Return a capped rich table for a CSV preview."""
    display_header = header[:MAX_CSV_COLS]
    table = Table(expand=True)
    for column in display_header:
        table.add_column(_clip_csv_cell(column), overflow="fold")
    if len(header) > MAX_CSV_COLS:
        table.add_column("…", overflow="fold")

    for row in rows[:MAX_CSV_ROWS]:
        display_row = [
            _clip_csv_cell(row[index] if index < len(row) else "")
            for index in range(len(display_header))
        ]
        if len(header) > MAX_CSV_COLS:
            overflow_values = row[MAX_CSV_COLS:]
            display_row.append(_clip_csv_cell(" | ".join(overflow_values)))
        table.add_row(*display_row)

    return table


def _clip_csv_cell(value: str) -> str:
    """Clip one CSV cell to a conservative width for TUI readability."""
    value = " ".join(value.splitlines())
    if len(value) <= MAX_CSV_CELL_WIDTH:
        return value
    return value[: MAX_CSV_CELL_WIDTH - 1].rstrip() + "…"


def _raw_csv_section(content: str, *, collapsed: bool = True) -> Collapsible:
    """Return the raw CSV section for a CSV preview."""
    return Collapsible(
        Static(Syntax(content, "csv", line_numbers=True, word_wrap=True), classes="csv-raw"),
        title="Raw CSV",
        collapsed=collapsed,
        classes="csv-raw-section",
    )


def _specialized_json_widget(data: Any) -> Widget | None:
    """Return a specialized preview widget for supported JSON shapes."""
    trajectory = extract_trajectory(data)
    if trajectory is not None:
        return TrajectoryViewer(trajectory)
    if _is_submission(data):
        return SubmissionSummary(data)
    return None


def _is_submission(data: Any) -> bool:
    """Return whether a JSON object looks like a worker submission artifact."""
    return isinstance(data, dict) and any(key in data for key in SUBMISSION_KEYS)


def _format_submission(data: dict[str, Any]) -> Text:
    """Render the submission summary as plain text sections."""
    lines = ["Submission Summary"]
    for key, title in SUBMISSION_SECTIONS:
        value = data.get(key)
        if value in (None, ""):
            continue
        lines.extend(["", title, _format_payload(value)])
    return Text("\n".join(lines))
