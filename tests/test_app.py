"""Tests for skim."""

import json

from rich.syntax import Syntax
from rich.text import Text
from textual.widgets import Markdown, Static, Tree

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
    assert _tree_labels(widgets[0]._tree) == ["Metadata", "Final Output", "Step 1"]


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


def test_trajectory_tree_groups_step_events():
    """Trajectory tree groups low-level events below their step."""
    viewer = TrajectoryViewer(sample_trajectory())
    step = viewer._tree.root.children[2]

    assert _tree_labels(viewer._tree) == ["Metadata", "Final Output", "Step 1"]
    event_labels = [child.label.plain for child in step.children]
    assert event_labels[0].startswith("001 reasoning Need inspect files.")
    assert event_labels[1].startswith("002 message assistant I will inspect files.")
    assert event_labels[2].startswith("003 function_call syntara__executeBash")
    assert "ls -la" in event_labels[2]
    assert event_labels[3].startswith("004 function_call_result syntara__executeBash")
    assert "stdout" in event_labels[3]


async def test_selecting_trajectory_tree_node_updates_detail():
    """Selecting a trajectory tree node updates the detail state."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test():
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        tool_node = viewer._tree.root.children[2].children[2]
        viewer.on_tree_node_selected(Tree.NodeSelected(tool_node))

        assert "function_call" in _detail_text(viewer)
        assert "ls -la" in _detail_text(viewer)


async def test_final_output_only_shows_when_selected():
    """Final output is a tree item rather than the initial detail content."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test():
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)

        assert "## Final" not in _detail_text(viewer)

        final_node = viewer._tree.root.children[1]
        viewer.on_tree_node_selected(Tree.NodeSelected(final_node))

        assert len(viewer._detail_wrap.query(Markdown)) >= 1


async def test_message_detail_renders_markdown():
    """Message strings render as Markdown when selected."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test():
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        message_node = viewer._tree.root.children[2].children[1]
        viewer.on_tree_node_selected(Tree.NodeSelected(message_node))

        assert len(viewer._detail_wrap.query(Markdown)) >= 1


async def test_tool_result_detail_decodes_stdout_stderr_and_returncode():
    """Tool results expose decoded stdout, stderr, and return code sections."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test():
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        result_node = viewer._tree.root.children[2].children[3]
        viewer.on_tree_node_selected(Tree.NodeSelected(result_node))

        detail = _detail_text(viewer)
        assert "returncode" in detail
        assert "stdout" in detail
        assert "stderr" in detail
        assert "plain terminal output" in detail


async def test_tool_result_detail_renders_json_stdout_as_syntax():
    """JSON-like stdout is shown as formatted JSON."""
    viewer = TrajectoryViewer(sample_trajectory(stdout='{"alpha": [1, 2]}'))
    app = SkimApp(path=".")

    async with app.run_test():
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        result_node = viewer._tree.root.children[2].children[3]
        viewer.on_tree_node_selected(Tree.NodeSelected(result_node))

        syntax_blocks = [
            _static_content(widget)
            for widget in viewer._detail_wrap.query(Static)
            if isinstance(_static_content(widget), Syntax)
        ]
        assert any('"alpha": [' in block.code for block in syntax_blocks)


async def test_tool_result_detail_renders_markdown_stdout():
    """Markdown and fenced code stdout render through Markdown."""
    stdout = "## Report\n\n```python\nprint('hi')\n```"
    viewer = TrajectoryViewer(sample_trajectory(stdout=stdout))
    app = SkimApp(path=".")

    async with app.run_test():
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        result_node = viewer._tree.root.children[2].children[3]
        viewer.on_tree_node_selected(Tree.NodeSelected(result_node))

        assert len(viewer._detail_wrap.query(Markdown)) >= 1


async def test_tool_call_arguments_render_code_string_outside_json_blob():
    """Code argument strings render as code instead of quoted JSON values."""
    viewer = TrajectoryViewer(
        sample_trajectory(arguments={"code": "import pandas as pd\nprint(pd.__version__)"})
    )
    app = SkimApp(path=".")

    async with app.run_test():
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        tool_node = viewer._tree.root.children[2].children[2]
        viewer.on_tree_node_selected(Tree.NodeSelected(tool_node))

        syntax_blocks = _detail_syntax_blocks(viewer)
        assert any("import pandas as pd" in block.code for block in syntax_blocks)
        assert not any('"code":' in block.code for block in syntax_blocks)


async def test_tool_result_pages_render_as_readable_sections():
    """Nested page arrays render page text outside a JSON object."""
    output = {"pages": ["## Page One\n\nUseful text"], "page_count": 1}
    viewer = TrajectoryViewer(sample_trajectory(output=output))
    app = SkimApp(path=".")

    async with app.run_test():
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        result_node = viewer._tree.root.children[2].children[3]
        viewer.on_tree_node_selected(Tree.NodeSelected(result_node))

        detail = _detail_text(viewer)
        assert "Page 1" in detail
        assert len(viewer._detail_wrap.query(Markdown)) >= 1
        assert not any('"pages":' in block.code for block in _detail_syntax_blocks(viewer))


async def test_machine_shaped_tool_payload_still_renders_as_json():
    """Machine-shaped dicts keep the compact JSON rendering fallback."""
    viewer = TrajectoryViewer(sample_trajectory(arguments={"timeout": 10, "flags": [1, 2]}))
    app = SkimApp(path=".")

    async with app.run_test():
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        tool_node = viewer._tree.root.children[2].children[2]
        viewer.on_tree_node_selected(Tree.NodeSelected(tool_node))

        assert any('"timeout": 10' in block.code for block in _detail_syntax_blocks(viewer))


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


def sample_trajectory(
    stdout: str = "plain terminal output",
    arguments: dict | None = None,
    output: dict | None = None,
):
    """Return a small raw trajectory fixture."""
    arguments = {"command": "ls -la"} if arguments is None else arguments
    output = (
        {"stdout": stdout, "stderr": "warning text", "returncode": 0} if output is None else output
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
        "steps": [
            {
                "output": [
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
                    {
                        "type": "function_call",
                        "name": "syntara__executeBash",
                        "callId": "tool-1",
                        "arguments": json.dumps(arguments),
                    },
                    {
                        "type": "function_call_result",
                        "name": "syntara__executeBash",
                        "callId": "tool-1",
                        "output": {"text": json.dumps(output)},
                    },
                ]
            }
        ],
    }


def _static_content(widget: Static):
    return widget._Static__content


def _tree_labels(tree: Tree):
    return [child.label.plain for child in tree.root.children]


def _detail_text(viewer: TrajectoryViewer) -> str:
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


def _detail_syntax_blocks(viewer: TrajectoryViewer) -> list[Syntax]:
    return [
        _static_content(widget)
        for widget in viewer._detail_wrap.query(Static)
        if isinstance(_static_content(widget), Syntax)
    ]
