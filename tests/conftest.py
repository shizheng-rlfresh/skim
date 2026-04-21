"""Shared trajectory builders and widget-inspection helpers for skim tests.

This module provides synthetic trajectory/sample data and small helper functions
used across the seam-aligned test modules. It does not own behavioral assertions;
those stay in the individual test files for the app shell, preview routing, and
trajectory viewer.
"""

import json
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

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


def sample_submission() -> dict[str, Any]:
    """Return a small worker-submission fixture for the JSON inspector."""
    return {
        "task_name": "Factors affecting WHPs",
        "submission_type": "Complete task",
        "prompt": "Compare spray diary information.",
        "quick_scores": "Model A: 32%",
        "quick_stats": "2 strong signals",
        "agentic_grader_guidance": "Identify Chlorpyrifos.",
        "task_solution": "Chlorpyrifos appears slower to decay than expected.",
        "load_trajectories_s3": "https://example.invalid/trajectory.json",
        "export_task_data_json": json.dumps(
            {
                "task_name": "Factors affecting WHPs",
                "notes": ["Look for repeated residue issues."],
            }
        ),
    }


def sample_bundle() -> list[dict[str, str]]:
    """Return a small bundle fixture with embedded task and trajectory JSON strings."""
    trajectory = sample_trajectory()
    trajectory["metadata"]["trajectory_id"] = "bundle-traj-c98cf3"
    trajectory["metadata"]["llm_model"] = "claude-opus-4-6"
    return [
        {
            "version": "1.0.0",
            "task": json.dumps(
                {
                    "task_id": "bundle-task-1",
                    "prompt": "Compare industry spray diary information.",
                }
            ),
            "trajectory": json.dumps(trajectory),
            "setup_files_url": "https://example.invalid/setup.zip",
        }
    ]


def sample_hermes_transcript() -> dict[str, Any]:
    """Return a small Hermes-style transcript fixture."""
    return {
        "model": "anthropic/claude-sonnet-4.6",
        "timestamp": "2026-04-14T22:00:00Z",
        "completed": True,
        "conversations": [
            {"from": "system", "value": "You are a structured reviewer."},
            {"from": "human", "value": "Please inspect the trajectories."},
            {"from": "assistant", "value": "I will start with the summary."},
            {"from": "tool", "value": '{"stdout": "Report line 1\\nReport line 2"}'},
            {"from": "assistant", "value": "The key issue is Chlorpyrifos."},
        ],
    }


def write_test_xlsx(path: Path, sheets: list[tuple[str, list[list[object | None]]]]) -> None:
    """Write a minimal `.xlsx` workbook fixture with inline-string cells."""
    workbook_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
{sheets}
  </sheets>
</workbook>
"""
    rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="xl/workbook.xml"/>
</Relationships>
"""
    workbook_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{relationships}
</Relationships>
"""
    content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml"
    ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
{overrides}
</Types>
"""

    def column_name(index: int) -> str:
        label = ""
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            label = chr(65 + remainder) + label
        return label

    def cell_xml(cell_ref: str, value: object | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return f'<c r="{cell_ref}" t="b"><v>{1 if value else 0}</v></c>'
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f'<c r="{cell_ref}"><v>{value}</v></c>'
        text = escape(str(value))
        return f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>'

    def sheet_xml(rows: list[list[object | None]]) -> str:
        row_xml: list[str] = []
        for row_index, row in enumerate(rows, start=1):
            cells = "".join(
                cell_xml(f"{column_name(column_index)}{row_index}", value)
                for column_index, value in enumerate(row, start=1)
            )
            row_xml.append(f'<row r="{row_index}">{cells}</row>')
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
{rows}
  </sheetData>
</worksheet>
""".format(rows="\n".join(row_xml))

    sheet_entries = []
    rel_entries = []
    override_entries = []
    sheet_payloads: list[tuple[str, str]] = []
    for index, (sheet_name, rows) in enumerate(sheets, start=1):
        escaped_name = escape(sheet_name)
        sheet_entries.append(
            f'    <sheet name="{escaped_name}" sheetId="{index}" r:id="rId{index}"/>'
        )
        rel_entries.append(
            f'  <Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
        override_entries.append(
            f'  <Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        sheet_payloads.append((f"xl/worksheets/sheet{index}.xml", sheet_xml(rows)))

    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            content_types_xml.format(overrides="\n".join(override_entries)),
        )
        archive.writestr("_rels/.rels", rels_xml)
        archive.writestr("xl/workbook.xml", workbook_xml.format(sheets="\n".join(sheet_entries)))
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            workbook_rels_xml.format(relationships="\n".join(rel_entries)),
        )
        for name, payload in sheet_payloads:
            archive.writestr(name, payload)


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


def _annotation_text(viewer: JsonInspector) -> str:
    """Collect textual content from the JSON inspector annotation panel."""
    parts = []
    for widget in viewer._annotation_wrap.query(Static):
        content = _static_content(widget)
        if isinstance(content, Text):
            parts.append(content.plain)
        elif isinstance(content, Syntax):
            parts.append(content.code)
        else:
            parts.append(str(content))
    return "\n".join(parts)


def _modal_preview_text(screen) -> str:
    """Collect textual content from the annotation modal preview panel."""
    parts = []
    preview = screen.query_one("#annotation-preview")
    for widget in preview.query(Static):
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
