"""Tests for skim."""

import json

from rich.syntax import Syntax
from textual.widgets import Static

from skim import (
    PreviewPane,
    SkimApp,
    SubmissionSummary,
    TrajectoryViewer,
    normalize_events,
    render_file,
)


async def test_app_launches():
    """App starts without crashing."""
    app = SkimApp(path=".")
    async with app.run_test():
        assert app.title == "skim"
        assert app.grid == [["pane-0"]]


async def test_split_right():
    """Pressing s then right creates a second pane."""
    app = SkimApp(path=".")
    async with app.run_test() as pilot:
        await pilot.press("s")
        await pilot.press("right")
        assert app._total_panes() == 2
        assert len(app.grid[0]) == 2


async def test_split_down():
    """Pressing s then down creates a second row."""
    app = SkimApp(path=".")
    async with app.run_test() as pilot:
        await pilot.press("s")
        await pilot.press("down")
        assert app._total_panes() == 2
        assert len(app.grid) == 2


async def test_close_pane():
    """Can close a pane but not the last one."""
    app = SkimApp(path=".")
    async with app.run_test() as pilot:
        # open a split
        await pilot.press("s")
        await pilot.press("right")
        assert app._total_panes() == 2

        # close it
        await pilot.press("d")
        assert app._total_panes() == 1

        # can't close the last one
        await pilot.press("d")
        assert app._total_panes() == 1


async def test_cycle_pane():
    """w cycles through panes."""
    app = SkimApp(path=".")
    async with app.run_test() as pilot:
        await pilot.press("s")
        await pilot.press("right")
        first_active = app.active_pane_id

        await pilot.press("w")
        second_active = app.active_pane_id

        assert first_active != second_active

        await pilot.press("w")
        assert app.active_pane_id == first_active


async def test_max_panes():
    """Cannot exceed 6 panes."""
    app = SkimApp(path=".")
    async with app.run_test() as pilot:
        for _ in range(5):
            await pilot.press("s")
            await pilot.press("right")
        assert app._total_panes() == 6

        # seventh should fail
        await pilot.press("s")
        await pilot.press("right")
        assert app._total_panes() == 6


async def test_file_preview(tmp_path):
    """Selecting a file shows its content."""
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello world")

    app = SkimApp(path=str(tmp_path))
    async with app.run_test() as pilot:
        # give the tree time to load
        await pilot.pause()
        from skim import PreviewPane

        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        pane.show_file(test_file)
        assert pane.current_path == test_file


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


def test_bare_trajectory_json_uses_trajectory_viewer(tmp_path):
    """A bare trajectory object uses the trajectory viewer."""
    test_file = tmp_path / "trajectory.json"
    test_file.write_text(json.dumps(sample_trajectory()))

    widgets = render_file(test_file)

    assert len(widgets) == 1
    assert isinstance(widgets[0], TrajectoryViewer)
    assert len(widgets[0].events) == 4


def test_normalize_events_extracts_supported_event_kinds():
    """Trajectory event normalization keeps the supported low-level event kinds."""
    events = normalize_events(sample_trajectory())

    assert [event.kind for event in events] == [
        "reasoning",
        "message",
        "function_call",
        "function_call_result",
    ]
    assert events[1].label == "assistant"
    assert events[2].label == "syntara__executeBash"
    assert "ls -la" in events[2].excerpt


async def test_clicking_trajectory_event_updates_detail():
    """Clicking an event item updates the trajectory detail state."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test():
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        await viewer._event_items[2].on_click()

        assert viewer.selected_index == 2
        assert "function_call" in viewer.detail_text.plain
        assert "ls -la" in viewer.detail_text.plain


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


def sample_trajectory():
    """Return a small raw trajectory fixture."""
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
        "steps": [
            {
                "output": [
                    {
                        "type": "reasoning",
                        "content": [{"type": "input_text", "text": "Need inspect files."}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "I will inspect files."}],
                    },
                    {
                        "type": "function_call",
                        "name": "syntara__executeBash",
                        "callId": "tool-1",
                        "arguments": '{"command": "ls -la"}',
                    },
                    {
                        "type": "function_call_result",
                        "name": "syntara__executeBash",
                        "callId": "tool-1",
                        "output": {"text": '{"stdout": "ok", "returncode": 0}'},
                    },
                ]
            }
        ],
    }


def _static_content(widget: Static):
    return widget._Static__content
