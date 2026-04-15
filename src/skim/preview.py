"""File preview routing and non-trajectory preview widgets for skim.

This module owns file reading, generic preview fallbacks, JSON preview dispatch,
and the preview pane container used by the outer app shell. It does not own the
outer multi-pane app behavior or trajectory-specific rendering internals.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.syntax import Syntax
from rich.text import Text
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Markdown, Static

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

    lexer = SYNTAX_MAP.get(suffix)
    if lexer:
        return [Static(Syntax(content, lexer, line_numbers=True, word_wrap=True))]
    return [Static(Text(content))]


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
