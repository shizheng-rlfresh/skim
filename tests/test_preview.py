"""Preview-routing tests for skim.

This module covers how files are classified and routed into generic previews,
submission summaries, or specialized trajectory viewers. It does not own app-shell
interaction tests or trajectory-detail rendering behavior.
"""

import json
from pathlib import Path

import pytest
from conftest import _static_content, _tree_labels, sample_trajectory
from rich.syntax import Syntax
from textual.widgets import Collapsible, Markdown, Static

from skim import PreviewPane, SkimApp, SubmissionSummary, TrajectoryViewer, render_file
from skim.preview import CsvPreview

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_generic_json_uses_syntax_preview(tmp_path):
    """Generic JSON keeps the syntax-highlighted preview."""
    test_file = tmp_path / "plain.json"
    test_file.write_text(json.dumps({"hello": "world"}))

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], Static)
    assert isinstance(_static_content(widgets[0]), Syntax)


def test_csv_uses_specialized_preview(tmp_path):
    """CSV files should use the specialized CSV preview widget."""
    test_file = tmp_path / "example.csv"
    test_file.write_text((DATA_DIR / "example.csv").read_text())

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], CsvPreview)


def test_csv_preview_shows_table_and_raw_section():
    """CSV preview should show a table summary plus a raw CSV section."""
    widgets = render_file(DATA_DIR / "example.csv")

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


def test_wrapped_trajectory_json_uses_trajectory_viewer(tmp_path):
    """A wrapped raw trajectory uses the trajectory viewer."""
    test_file = tmp_path / "output.json"
    test_file.write_text(json.dumps({"trajectory": sample_trajectory()}))

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], TrajectoryViewer)
    assert len(widgets[0].events) == 4
    assert _tree_labels(widgets[0]._tree) == ["Metadata", "Final Output", "Step 1"]


def test_bare_trajectory_json_uses_trajectory_viewer(tmp_path):
    """A bare trajectory object uses the trajectory viewer."""
    test_file = tmp_path / "trajectory.json"
    test_file.write_text(json.dumps(sample_trajectory()))

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], TrajectoryViewer)
    assert len(widgets[0].events) == 4


def test_submission_json_uses_submission_summary(tmp_path):
    """Worker submission JSON uses the submission summary viewer."""
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
    assert isinstance(widgets[0], SubmissionSummary)
    text = widgets[0].summary_text.plain
    assert "Factors affecting WHPs" in text
    assert "https://example.invalid/trajectory.json" in text


@pytest.mark.parametrize(
    ("sample_name", "lexer"),
    [
        ("example.xml", "xml"),
        ("example.toml", "toml"),
        ("example.css", "css"),
        ("example.html", "html"),
        ("example.sql", "sql"),
        ("example.yaml", "yaml"),
    ],
)
def test_sample_backed_text_formats_use_expected_syntax_preview(sample_name, lexer):
    """Sample-backed README formats should route to the expected syntax preview."""
    widgets = render_file(DATA_DIR / sample_name)

    assert len(widgets) == 1
    assert isinstance(widgets[0], Static)
    content = _static_content(widgets[0])
    assert isinstance(content, Syntax)
    assert content.lexer.name.lower() == lexer


@pytest.mark.parametrize(
    "sample_name",
    [
        "review_note.md",
        "review_decision.md",
        "review_instruction.md",
        "score_submission.md",
    ],
)
def test_sample_backed_markdown_formats_render_markdown(sample_name):
    """Markdown samples should render through the Markdown widget."""
    widgets = render_file(DATA_DIR / sample_name)

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
        assert isinstance(pane.query_one(TrajectoryViewer), TrajectoryViewer)


async def test_non_trajectory_previews_do_not_mount_local_footer(tmp_path):
    """Only trajectory previews should render a local footer."""
    generic = tmp_path / "data.json"
    generic.write_text('{"alpha": 1}')
    submission = tmp_path / "submission.json"
    submission.write_text('{"task_name": "Task", "submission_type": "worker", "prompt": "Prompt"}')
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)

        pane.show_file(generic)
        await pilot.pause()
        assert not pane.query(".trajectory-footer")

        pane.show_file(submission)
        await pilot.pause()
        assert not pane.query(".trajectory-footer")
