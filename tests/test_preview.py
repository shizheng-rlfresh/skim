"""Preview-routing tests for skim.

This module covers how files are classified and routed into generic previews,
the unified JSON inspector, or specialized non-JSON widgets such as CSV. It
uses tracked synthetic fixtures instead of ignored local sample files so CI and
local runs exercise the same inputs.
"""

import json

import pytest
from conftest import (
    _detail_text,
    _static_content,
    _tree_labels,
    sample_bundle,
    sample_hermes_transcript,
    sample_submission,
    sample_trajectory,
)
from rich.syntax import Syntax
from textual.widgets import Collapsible, Markdown, Static, Tree

from skim import JsonInspector, PreviewPane, SkimApp, render_file
from skim.preview import CsvPreview


def test_generic_json_uses_json_inspector(tmp_path):
    """Generic JSON now uses the unified JSON inspector."""
    test_file = tmp_path / "plain.json"
    test_file.write_text(json.dumps({"hello": "world"}))

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], JsonInspector)
    assert _tree_labels(widgets[0]._tree) == ["Hello world"]


def test_csv_uses_specialized_preview(tmp_path):
    """CSV files should use the specialized CSV preview widget."""
    test_file = tmp_path / "example.csv"
    test_file.write_text("name,value\napple,4\norange,7\n")

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], CsvPreview)


def test_csv_preview_shows_table_and_raw_section(tmp_path):
    """CSV preview should show a table summary plus a raw CSV section."""
    test_file = tmp_path / "example.csv"
    test_file.write_text("name,value\napple,4\norange,7\n")

    widgets = render_file(test_file)

    assert len(widgets) == 1
    preview = widgets[0]
    assert isinstance(preview, CsvPreview)
    assert isinstance(preview._widgets[1], Static)
    assert isinstance(_static_content(preview._widgets[1]), object)
    raw = preview._widgets[2]
    assert isinstance(raw, Collapsible)
    assert raw.title == "Raw CSV"
    assert raw.collapsed


def test_csv_parse_error_shows_error_and_raw_content(tmp_path):
    """Malformed CSV should stay visible with an explicit parse-error note."""
    test_file = tmp_path / "broken.csv"
    test_file.write_text('name,value\n"broken,1\n')

    widgets = render_file(test_file)

    assert len(widgets) == 1
    preview = widgets[0]
    assert isinstance(preview, CsvPreview)
    error = preview._widgets[0]
    assert isinstance(error, Static)
    assert "CSV parse error:" in _static_content(error).plain
    raw = preview._widgets[1]
    assert isinstance(raw, Collapsible)
    assert raw.title == "Raw CSV"
    assert not raw.collapsed


def test_csv_preview_caps_wide_and_long_content(tmp_path):
    """CSV preview should cap rows, columns, and oversized cell values."""
    test_file = tmp_path / "wide.csv"
    header = ",".join(f"col_{index}" for index in range(10))
    long_cell = "x" * 80
    rows = [",".join([long_cell, *[f"value_{index}" for index in range(1, 10)]]) for _ in range(25)]
    test_file.write_text("\n".join([header, *rows]))

    widgets = render_file(test_file)

    preview = widgets[0]
    assert isinstance(preview, CsvPreview)
    table = _static_content(preview._widgets[1])
    assert len(table.columns) == 9
    assert table.row_count == 20
    first_cell = table.columns[0]._cells[0]
    assert first_cell.endswith("…")
    assert len(first_cell) == 24


def test_invalid_json_falls_back_to_syntax_preview(tmp_path):
    """Invalid JSON still renders through the generic JSON path."""
    test_file = tmp_path / "broken.json"
    test_file.write_text("{not json")

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], Static)
    assert isinstance(_static_content(widgets[0]), Syntax)


def test_wrapped_trajectory_json_uses_json_inspector(tmp_path):
    """A wrapped raw trajectory uses the unified JSON inspector."""
    test_file = tmp_path / "output.json"
    test_file.write_text(json.dumps({"trajectory": sample_trajectory()}))

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], JsonInspector)
    assert _tree_labels(widgets[0]._tree)[:4] == [
        "Metadata",
        "Final Output",
        "Step 1",
        "Trajectory {4}",
    ]


def test_bare_trajectory_json_uses_json_inspector(tmp_path):
    """A bare trajectory object uses the unified JSON inspector."""
    test_file = tmp_path / "trajectory.json"
    test_file.write_text(json.dumps(sample_trajectory()))

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], JsonInspector)
    assert _tree_labels(widgets[0]._tree)[:3] == ["Metadata", "Final Output", "Step 1"]


def test_submission_json_uses_json_inspector(tmp_path):
    """Worker submission JSON uses the unified inspector with summary nodes."""
    test_file = tmp_path / "submission.json"
    test_file.write_text(
        json.dumps(
            {
                "task_name": "Factors affecting WHPs",
                "submission_type": "Complete task",
                "prompt": "Compare spray diary information.",
                "quick_scores": "Model A: 32%",
                "agentic_grader_guidance": "Identify Chlorpyrifos.",
                "load_trajectories_s3": "https://example.invalid/trajectory.json",
            }
        )
    )

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], JsonInspector)
    labels = _tree_labels(widgets[0]._tree)
    assert labels[0] == "Submission Summary"
    assert "Task Name Factors affecting WHPs" in labels
    assert "Trajectory URL https://example.invalid/trajectory.json" in labels


async def test_submission_summary_node_renders_summary_detail(tmp_path):
    """Selecting the submission summary node should keep the summary in the inspector."""
    test_file = tmp_path / "submission.json"
    test_file.write_text(json.dumps(sample_submission()))
    widgets = render_file(test_file)
    inspector = widgets[0]
    assert isinstance(inspector, JsonInspector)

    app = SkimApp(path=".")
    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(inspector)
        summary_node = inspector._tree.root.children[0]
        inspector.on_tree_node_selected(Tree.NodeSelected(summary_node))
        await pilot.pause()

        detail = _detail_text(inspector)
        assert "Task Name:" in detail
        assert "Submission Type:" in detail
        assert "Grader Guidance" in detail


def test_bundle_json_uses_json_inspector_with_human_run_labels(tmp_path):
    """Trajectory bundles should use the inspector with human-labeled array items."""
    test_file = tmp_path / "trajectories.json"
    test_file.write_text(json.dumps(sample_bundle()))
    widgets = render_file(test_file)

    assert len(widgets) == 1
    inspector = widgets[0]
    assert isinstance(inspector, JsonInspector)
    labels = _tree_labels(inspector._tree)
    assert labels[0] == "Bundle Summary"
    assert labels[1].startswith("[0] claude-opus-4-6 #")


async def test_bundle_item_detail_decodes_embedded_task_and_trajectory(tmp_path):
    """Selecting a bundle item should decode embedded JSON strings in the detail pane."""
    test_file = tmp_path / "trajectories.json"
    test_file.write_text(json.dumps(sample_bundle()))
    widgets = render_file(test_file)
    inspector = widgets[0]
    assert isinstance(inspector, JsonInspector)

    app = SkimApp(path=".")
    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(inspector)
        item_node = inspector._tree.root.children[1]
        inspector.on_tree_node_selected(Tree.NodeSelected(item_node))
        await pilot.pause()

        detail = _detail_text(inspector)
        assert "Task" in detail
        assert "Trajectory" in detail
        assert "claude-opus-4-6" in detail
        assert "Final Output" in detail


def test_hermes_json_uses_json_inspector_with_transcript_labels(tmp_path):
    """Hermes transcripts should use the inspector with smart conversation labels."""
    test_file = tmp_path / "hermes_trajectory.json"
    test_file.write_text(json.dumps(sample_hermes_transcript()))
    widgets = render_file(test_file)

    assert len(widgets) == 1
    inspector = widgets[0]
    assert isinstance(inspector, JsonInspector)
    labels = _tree_labels(inspector._tree)
    assert labels[0] == "Transcript Summary"
    assert "Conversations [5]" in labels
    conversations_node = next(
        child
        for child in inspector._tree.root.children
        if child.label.plain.startswith("Conversations ")
    )
    conversation_labels = [child.label.plain for child in conversations_node.children]
    assert conversation_labels[0].startswith("[0] System")
    assert conversation_labels[1].startswith("[1] Human")


async def test_output_json_exposes_raw_path_on_selectable_nodes(tmp_path):
    """Each selectable JSON-inspector node should carry a stable raw path."""
    test_file = tmp_path / "output.json"
    test_file.write_text(json.dumps({"trajectory": sample_trajectory()}))
    widgets = render_file(test_file)
    inspector = widgets[0]
    assert isinstance(inspector, JsonInspector)

    metadata_node = inspector._tree.root.children[0]
    trajectory_node = next(
        child
        for child in inspector._tree.root.children
        if child.label.plain.startswith("Trajectory ")
    )
    assert metadata_node.data.raw_path == ("trajectory", "metadata")
    assert trajectory_node.data.raw_path == ("trajectory",)


@pytest.mark.parametrize(
    ("filename", "lexer", "content"),
    [
        ("example.xml", "xml", "<root><item>value</item></root>\n"),
        ("example.toml", "toml", 'title = "skim"\n[tool]\nname = "preview"\n'),
        ("example.css", "css", "body { color: #333; }\n"),
        ("example.html", "html", "<!doctype html><html><body>skim</body></html>\n"),
        ("example.sql", "sql", "select * from trajectories;\n"),
        ("example.yaml", "yaml", "name: skim\nmode: preview\n"),
    ],
)
def test_text_formats_use_expected_syntax_preview(tmp_path, filename, lexer, content):
    """Tracked synthetic text fixtures should route to the expected syntax preview."""
    test_file = tmp_path / filename
    test_file.write_text(content)

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], Static)
    content = _static_content(widgets[0])
    assert isinstance(content, Syntax)
    assert content.lexer.name.lower() == lexer


@pytest.mark.parametrize(
    "filename",
    [
        "review_note.md",
        "review_decision.md",
        "review_instruction.md",
        "score_submission.md",
    ],
)
def test_markdown_formats_render_markdown(tmp_path, filename):
    """Tracked synthetic markdown fixtures should render through Markdown."""
    test_file = tmp_path / filename
    test_file.write_text("# Heading\n\n- item one\n- item two\n")

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], Markdown)


@pytest.mark.parametrize(
    ("suffix", "lexer", "content"),
    [
        (".py", "python", "print('hello')\n"),
        (".js", "javascript", "const x = 1;\n"),
        (".ts", "typescript", "const x: number = 1;\n"),
        (".sh", "bash", "echo hello\n"),
        (".rs", "rust", "fn main() {}\n"),
        (".go", "go", "package main\nfunc main() {}\n"),
    ],
)
def test_synthetic_readme_formats_route_to_expected_syntax_preview(
    tmp_path, suffix, lexer, content
):
    """README-listed formats without sample files should still use the expected lexer."""
    test_file = tmp_path / f"example{suffix}"
    test_file.write_text(content)

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], Static)
    renderable = _static_content(widgets[0])
    assert isinstance(renderable, Syntax)
    assert renderable.lexer.name.lower() == lexer


async def test_split_panes_keep_specialized_preview(tmp_path):
    """Specialized previews still work inside split panes."""
    test_file = tmp_path / "output.json"
    test_file.write_text(json.dumps({"trajectory": sample_trajectory()}))
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.press("s")
        await pilot.press("right")
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        pane.show_file(test_file)

        assert app._total_panes() == 2
        assert isinstance(pane.query_one(JsonInspector), JsonInspector)


async def test_non_trajectory_previews_do_not_mount_local_footer(tmp_path):
    """Only JSON tree/detail previews should render the local footer."""
    markdown = tmp_path / "note.md"
    markdown.write_text("# Note\n")
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("a,b\n1,2\n")
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)

        pane.show_file(markdown)
        await pilot.pause()
        assert not pane.query(".trajectory-footer")

        pane.show_file(csv_file)
        await pilot.pause()
        assert not pane.query(".trajectory-footer")
