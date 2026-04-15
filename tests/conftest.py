"""Shared trajectory builders and widget-inspection helpers for skim tests.

This module provides synthetic trajectory/sample data and small helper functions
used across the seam-aligned test modules. It does not own behavioral assertions;
those stay in the individual test files for the app shell, preview routing, and
trajectory viewer.
"""

import json
from typing import Any

from rich.syntax import Syntax
from rich.text import Text
from textual.widgets import Collapsible, Static, Tree

from skim import JsonInspector, TrajectoryViewer


def sample_trajectory(
    stdout: str = "plain terminal output",
    arguments: dict | None = None,
    output: dict | None = None,
    include_call: bool = True,
    include_result: bool = True,
) -> dict[str, Any]:
    """Return a small raw trajectory fixture."""
    arguments = {"command": "ls -la"} if arguments is None else arguments
    output = (
        {"stdout": stdout, "stderr": "warning text", "returncode": 0} if output is None else output
    )
    step_output = [
        {
            "type": "reasoning",
            "content": [
                {
                    "type": "input_text",
                    "text": "Need inspect files.\n\n- Check data",
                }
            ],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": "I will inspect files.\n\n```bash\nls -la\n```",
                }
            ],
        },
    ]
    if include_call:
        step_output.append(
            {
                "type": "function_call",
                "name": "syntara__executeBash",
                "callId": "tool-1",
                "status": "completed",
                "arguments": json.dumps(arguments),
            }
        )
    if include_result:
        step_output.append(
            {
                "type": "function_call_result",
                "name": "syntara__executeBash",
                "callId": "tool-1",
                "status": "completed",
                "output": {"text": json.dumps(output)},
            }
        )
    return {
        "metadata": {
            "trajectory_id": "traj-1",
            "task_id": "task-1",
            "llm_provider": "anthropic",
            "llm_model": "claude-test",
            "input_tokens": 100,
            "output_tokens": 200,
        },
        "context_compaction_events": [{"message_index": 3}],
        "final_output": "## Final\n\nDone.",
        "steps": [{"output": step_output}],
    }


def multi_step_trajectory(step_count: int) -> dict[str, Any]:
    """Return a trajectory with repeated steps to force tree overflow."""
    trajectory = sample_trajectory()
    step = trajectory["steps"][0]
    trajectory["steps"] = [step for _ in range(step_count)]
    return trajectory


def _static_content(widget: Static) -> object:
    """Return the private Static content object for focused test inspection."""
    return widget._Static__content


def _tree_labels(tree: Tree) -> list[str]:
    """Return the root child labels from a Textual tree widget."""
    return [child.label.plain for child in tree.root.children]


def _detail_text(viewer: TrajectoryViewer | JsonInspector) -> str:
    """Collect textual content from the rendered detail pane."""
    parts = []
    for widget in viewer._detail_wrap.query(Static):
        content = _static_content(widget)
        if isinstance(content, Text):
            parts.append(content.plain)
        elif isinstance(content, Syntax):
            parts.append(content.code)
        else:
            parts.append(str(content))
    return "\n".join(parts)


def _detail_syntax_blocks(viewer: TrajectoryViewer | JsonInspector) -> list[Syntax]:
    """Return all Syntax renderables mounted inside the detail pane."""
    return [
        _static_content(widget)
        for widget in viewer._detail_wrap.query(Static)
        if isinstance(_static_content(widget), Syntax)
    ]


def _top_level_collapsible_titles(viewer: TrajectoryViewer | JsonInspector) -> list[str]:
    """Return titles for top-level collapsible sections in the detail pane."""
    return [child.title for child in viewer._detail_wrap.children if isinstance(child, Collapsible)]


def _all_collapsible_titles(viewer: TrajectoryViewer | JsonInspector) -> list[str]:
    """Return titles for all collapsible sections in the detail pane."""
    return [widget.title for widget in viewer._detail_wrap.query(Collapsible)]


def _collapsible_by_title(viewer: TrajectoryViewer | JsonInspector, title: str) -> Collapsible:
    """Return the first collapsible section with the requested title."""
    for widget in viewer._detail_wrap.query(Collapsible):
        if widget.title == title:
            return widget
    raise AssertionError(f"Collapsible with title {title!r} not found")
