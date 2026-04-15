"""Preview-routing tests for skim.

This module covers how files are classified and routed into generic previews,
submission summaries, or specialized trajectory viewers. It does not own app-shell
interaction tests or trajectory-detail rendering behavior.
"""

import json

from conftest import _static_content, _tree_labels, sample_trajectory
from rich.syntax import Syntax
from textual.widgets import Static

from skim import PreviewPane, SkimApp, SubmissionSummary, TrajectoryViewer, render_file


def test_generic_json_uses_syntax_preview(tmp_path):
    """Generic JSON keeps the syntax-highlighted preview."""
    test_file = tmp_path / "plain.json"
    test_file.write_text(json.dumps({"hello": "world"}))

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], Static)
    assert isinstance(_static_content(widgets[0]), Syntax)


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
