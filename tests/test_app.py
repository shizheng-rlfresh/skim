"""Tests for skim."""

import json
from typing import Any

from rich.syntax import Syntax
from rich.text import Text
from textual.widgets import Collapsible, Markdown, Static, Tree

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
    """Trajectory tree groups tool calls into paired input/output rows."""
    viewer = TrajectoryViewer(sample_trajectory())
    step = viewer._tree.root.children[2]

    assert _tree_labels(viewer._tree) == ["Metadata", "Final Output", "Step 1"]
    event_labels = [child.label.plain for child in step.children]
    assert event_labels[0].startswith("001 Reasoning")
    assert event_labels[1].startswith("002 Assistant")
    assert event_labels[2].startswith("003 executeBash #")
    tool_node = step.children[2]
    assert [child.label.plain for child in tool_node.children] == ["Input", "Output"]


async def test_selecting_trajectory_tree_node_updates_detail():
    """Selecting a tool parent shows paired input and output detail."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        tool_node = viewer._tree.root.children[2].children[2]
        viewer.on_tree_node_selected(Tree.NodeSelected(tool_node))
        await pilot.pause()

        assert _top_level_collapsible_titles(viewer) == ["Tool", "Input", "Output"]
        assert "ls -la" in _detail_text(viewer)


async def test_final_output_only_shows_when_selected():
    """Final output is a tree item rather than the initial detail content."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)

        assert "## Final" not in _detail_text(viewer)

        final_node = viewer._tree.root.children[1]
        viewer.on_tree_node_selected(Tree.NodeSelected(final_node))
        await pilot.pause()

        assert len(viewer._detail_wrap.query(Markdown)) >= 1


async def test_message_detail_renders_markdown():
    """Message strings render as Markdown when selected."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        message_node = viewer._tree.root.children[2].children[1]
        viewer.on_tree_node_selected(Tree.NodeSelected(message_node))
        await pilot.pause()

        assert len(viewer._detail_wrap.query(Markdown)) >= 1


async def test_selecting_tool_input_keeps_tool_metadata_visible():
    """Selecting Input keeps paired tool context visible."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        input_node = viewer._tree.root.children[2].children[2].children[0]
        viewer.on_tree_node_selected(Tree.NodeSelected(input_node))
        await pilot.pause()

        detail = _detail_text(viewer)
        assert "Tool:" in detail
        assert "Call ID:" in detail
        assert _top_level_collapsible_titles(viewer) == ["Tool", "Input", "Output"]
        assert "ls -la" in detail


async def test_selecting_tool_output_keeps_tool_metadata_visible():
    """Selecting Output keeps paired tool context visible."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        output_node = viewer._tree.root.children[2].children[2].children[1]
        viewer.on_tree_node_selected(Tree.NodeSelected(output_node))
        await pilot.pause()

        detail = _detail_text(viewer)
        assert "Tool:" in detail
        assert "Call ID:" in detail
        assert _top_level_collapsible_titles(viewer) == ["Tool", "Input", "Output"]
        assert "plain terminal output" in detail


async def test_selecting_output_does_not_reorder_sections():
    """Selecting Output keeps Input above Output in the detail pane."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        output_node = viewer._tree.root.children[2].children[2].children[1]
        viewer.on_tree_node_selected(Tree.NodeSelected(output_node))
        await pilot.pause()

        assert _top_level_collapsible_titles(viewer) == ["Tool", "Input", "Output"]


async def test_tool_result_detail_decodes_stdout_stderr_and_returncode():
    """Tool results expose decoded stdout, stderr, and return code sections."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        result_node = viewer._tree.root.children[2].children[2].children[1]
        viewer.on_tree_node_selected(Tree.NodeSelected(result_node))
        await pilot.pause()

        detail = _detail_text(viewer)
        assert "returncode" in detail
        assert "stdout" in detail
        assert "stderr" in detail
        assert "plain terminal output" in detail
        assert "stdout" in _all_collapsible_titles(viewer)
        assert "stderr" in _all_collapsible_titles(viewer)


async def test_tool_result_detail_renders_json_stdout_as_syntax():
    """JSON-like stdout is shown as formatted JSON."""
    viewer = TrajectoryViewer(sample_trajectory(stdout='{"alpha": [1, 2]}'))
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        result_node = viewer._tree.root.children[2].children[2].children[1]
        viewer.on_tree_node_selected(Tree.NodeSelected(result_node))
        await pilot.pause()

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

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        result_node = viewer._tree.root.children[2].children[2].children[1]
        viewer.on_tree_node_selected(Tree.NodeSelected(result_node))
        await pilot.pause()

        assert len(viewer._detail_wrap.query(Markdown)) >= 1


async def test_tool_call_arguments_render_code_string_outside_json_blob():
    """Code argument strings render as code instead of quoted JSON values."""
    viewer = TrajectoryViewer(
        sample_trajectory(arguments={"code": "import pandas as pd\nprint(pd.__version__)"})
    )
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        tool_node = viewer._tree.root.children[2].children[2]
        viewer.on_tree_node_selected(Tree.NodeSelected(tool_node))
        await pilot.pause()

        syntax_blocks = _detail_syntax_blocks(viewer)
        assert any("import pandas as pd" in block.code for block in syntax_blocks)
        assert not any('"code":' in block.code for block in syntax_blocks)
        assert "code" in _all_collapsible_titles(viewer)


async def test_tool_result_pages_render_as_readable_sections():
    """Nested page arrays render page text outside a JSON object."""
    output = {"pages": ["## Page One\n\nUseful text"], "page_count": 1}
    viewer = TrajectoryViewer(sample_trajectory(output=output))
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        result_node = viewer._tree.root.children[2].children[2].children[1]
        viewer.on_tree_node_selected(Tree.NodeSelected(result_node))
        await pilot.pause()

        assert "pages" in _all_collapsible_titles(viewer)
        assert "Page 1" in _all_collapsible_titles(viewer)
        assert len(viewer._detail_wrap.query(Markdown)) >= 1
        assert not any('"pages":' in block.code for block in _detail_syntax_blocks(viewer))
        assert _collapsible_by_title(viewer, "pages").collapsed


async def test_nested_output_text_stdout_promotes_inner_content():
    """Nested output -> text -> stdout payloads promote the inner stdout section."""
    output = {"text": json.dumps({"stdout": "## Nested\n\nUseful text", "returncode": 0})}
    viewer = TrajectoryViewer(sample_trajectory(output=output))
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        result_node = viewer._tree.root.children[2].children[2].children[1]
        viewer.on_tree_node_selected(Tree.NodeSelected(result_node))
        await pilot.pause()

        detail = _detail_text(viewer)
        assert "stdout" in detail
        assert len(viewer._detail_wrap.query(Markdown)) >= 1
        assert not any('"text":' in block.code for block in _detail_syntax_blocks(viewer))
        assert "stdout" in _all_collapsible_titles(viewer)


async def test_output_text_wrapper_does_not_duplicate_stdout_stderr_sections():
    """Decoded output.text payloads should not also render duplicate text-wrapped sections."""
    output = {"text": {"stdout": "done", "stderr": "warn", "returncode": 0}}
    viewer = TrajectoryViewer(sample_trajectory(output=output))
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        result_node = viewer._tree.root.children[2].children[2].children[1]
        viewer.on_tree_node_selected(Tree.NodeSelected(result_node))
        await pilot.pause()

        titles = _all_collapsible_titles(viewer)
        assert titles.count("stdout") == 1
        assert titles.count("stderr") == 1
        assert "text" not in titles


async def test_wrapper_promotion_keeps_scalar_sibling_metadata():
    """Wrapper promotion keeps useful scalar siblings instead of dropping them."""
    output = {
        "output": {
            "text": '{"stdout": "done"}',
            "mime_type": "text/plain",
            "returncode": 0,
        }
    }
    viewer = TrajectoryViewer(sample_trajectory(output=output))
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        result_node = viewer._tree.root.children[2].children[2].children[1]
        viewer.on_tree_node_selected(Tree.NodeSelected(result_node))
        await pilot.pause()

        detail = _detail_text(viewer)
        assert "mime_type" in detail
        assert "text/plain" in detail
        assert "stdout" in detail


async def test_machine_shaped_tool_payload_still_renders_as_json():
    """Machine-shaped dicts keep the compact JSON rendering fallback."""
    viewer = TrajectoryViewer(sample_trajectory(arguments={"timeout": 10, "flags": [1, 2]}))
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        tool_node = viewer._tree.root.children[2].children[2]
        viewer.on_tree_node_selected(Tree.NodeSelected(tool_node))
        await pilot.pause()

        assert any('"timeout": 10' in block.code for block in _detail_syntax_blocks(viewer))


async def test_unmatched_function_call_result_still_renders_safely():
    """A result without a matching call still shows as a tool row with output."""
    viewer = TrajectoryViewer(sample_trajectory(include_call=False))
    step = viewer._tree.root.children[2]

    assert step.children[2].label.plain.startswith("003 executeBash #")
    assert step.children[2].label.plain.endswith(" Output")
    assert [child.label.plain for child in step.children[2].children] == ["Input", "Output"]


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


async def test_scroll_keys_scroll_generic_preview_pane(tmp_path):
    """App scroll actions should still scroll a normal preview pane."""
    test_file = tmp_path / "long.txt"
    test_file.write_text("\n".join(f"line {index}" for index in range(400)))
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        pane.show_file(test_file)
        await pilot.pause()

        before = pane.scroll_y
        await pilot.press("down")
        await pilot.pause()

        assert pane.scroll_y > before


async def test_scroll_keys_scroll_trajectory_detail_panel():
    """App scroll actions should scroll the trajectory detail panel, not only the outer pane."""
    stdout = "\n".join(f"line {index}" for index in range(200))
    viewer = TrajectoryViewer(sample_trajectory(stdout=stdout))
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        output_node = viewer._tree.root.children[2].children[2].children[1]
        await pilot.pause()
        viewer._tree.move_cursor(output_node, animate=False)
        await pilot.press("enter")
        await pilot.pause()

        before = viewer._detail_wrap.scroll_y
        await pilot.press("down")
        await pilot.pause()

        assert viewer._detail_wrap.scroll_y > before


async def test_trajectory_viewer_arrows_drive_tree_until_enter():
    """Trajectory previews should use arrows for tree navigation before entering detail mode."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        await pilot.pause()
        viewer.focus_tree_mode()

        assert viewer.is_tree_mode()
        assert viewer._tree.cursor_node is viewer._tree.root.children[0]

        await pilot.press("down")
        await pilot.pause()

        assert viewer._tree.cursor_node is viewer._tree.root.children[1]
        assert viewer._detail_wrap.scroll_y == 0


async def test_escape_returns_from_trajectory_detail_to_tree_mode():
    """Escape should return keyboard control from detail scrolling back to the tree."""
    stdout = "\n".join(f"line {index}" for index in range(200))
    viewer = TrajectoryViewer(sample_trajectory(stdout=stdout))
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        output_node = viewer._tree.root.children[2].children[2].children[1]
        await pilot.pause()

        viewer._tree.move_cursor(output_node, animate=False)
        await pilot.press("enter")
        await pilot.pause()
        assert not viewer.is_tree_mode()

        await pilot.press("down")
        await pilot.pause()
        scrolled = viewer._detail_wrap.scroll_y
        assert scrolled > 0

        await pilot.press("escape")
        await pilot.pause()
        assert viewer.is_tree_mode()

        await pilot.press("up")
        await pilot.pause()

        assert viewer._tree.cursor_node is viewer._tree.root.children[2].children[2].children[0]
        assert viewer._detail_wrap.scroll_y == scrolled


async def test_trajectory_viewer_mounts_local_footer():
    """Trajectory viewer should render its own local command footer."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        await pilot.pause()

        footer = viewer.query_one(".trajectory-footer", Static)
        content = _static_content(footer)

        assert isinstance(content, Text)
        assert "Move" in content.plain
        assert "Branch" in content.plain
        assert "Detail" in content.plain


async def test_trajectory_footer_switches_between_tree_and_detail_modes():
    """Trajectory footer should track tree/detail keyboard mode."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        await pilot.pause()
        viewer.focus_tree_mode()

        footer = viewer.query_one(".trajectory-footer", Static)
        tree_content = _static_content(footer)
        assert isinstance(tree_content, Text)
        assert "Move" in tree_content.plain
        assert "Branch" in tree_content.plain

        await pilot.press("enter")
        await pilot.pause()

        detail_content = _static_content(footer)
        assert isinstance(detail_content, Text)
        assert "Scroll" in detail_content.plain
        assert "Back to JSON" in detail_content.plain

        await pilot.press("escape")
        await pilot.pause()

        reset_content = _static_content(footer)
        assert isinstance(reset_content, Text)
        assert "Move" in reset_content.plain
        assert "Branch" in reset_content.plain


async def test_global_footer_only_shows_app_wide_commands():
    """Global footer should not include trajectory-specific commands."""
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        await pilot.pause()

        footer = app.query_one("#status-bar", Static)
        content = _static_content(footer)

        assert isinstance(content, str)
        assert "Scroll" in content
        assert "Open" in content
        assert "JSON" not in content
        assert "Branch" not in content
        assert "Detail" not in content
        assert "Esc" not in content


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


async def test_mouse_drag_scrolls_preview_pane(tmp_path):
    """Dragging inside a preview pane should scroll long generic content."""
    test_file = tmp_path / "long.txt"
    test_file.write_text("\n".join(f"line {index}" for index in range(400)))
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        pane.show_file(test_file)
        await pilot.pause()
        before = pane.scroll_y

        await pilot.mouse_down(pane, offset=(5, 10))
        await pilot.hover(pane, offset=(5, 1))
        await pilot.mouse_up(pane, offset=(5, 1))
        await pilot.pause()

        assert pane.scroll_y > before


async def test_mouse_drag_scrolls_directory_tree(tmp_path):
    """Dragging inside the file tree should scroll the tree."""
    for index in range(80):
        (tmp_path / f"file_{index}.txt").write_text("x")
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one("DirectoryTree")
        before = tree.scroll_y

        await pilot.mouse_down(tree, offset=(5, 10))
        await pilot.hover(tree, offset=(5, 1))
        await pilot.mouse_up(tree, offset=(5, 1))
        await pilot.pause()

        assert tree.scroll_y > before


async def test_mouse_drag_scrolls_trajectory_tree():
    """Dragging inside the trajectory tree should scroll long step lists."""
    viewer = TrajectoryViewer(multi_step_trajectory(20))
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        await pilot.pause()
        tree = viewer.query_one(".trajectory-tree", Tree)
        before = tree.scroll_y

        await pilot.mouse_down(tree, offset=(5, 10))
        await pilot.hover(tree, offset=(5, 1))
        await pilot.mouse_up(tree, offset=(5, 1))
        await pilot.pause()

        assert tree.scroll_y > before


async def test_mouse_drag_scrolls_trajectory_detail():
    """Dragging on the detail pane background should scroll long detail output."""
    viewer = TrajectoryViewer(sample_trajectory())
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        await pane.mount(viewer)
        output_node = viewer._tree.root.children[2].children[2].children[1]
        viewer._tree.move_cursor(output_node, animate=False)
        await pilot.press("enter")
        await pilot.pause()
        detail = viewer.query_one(".trajectory-detail-wrap")
        before = detail.scroll_y

        await pilot.mouse_down(detail, offset=(0, 10))
        await pilot.hover(detail, offset=(0, 1))
        await pilot.mouse_up(detail, offset=(0, 1))
        await pilot.pause()

        assert detail.scroll_y > before


def sample_trajectory(
    stdout: str = "plain terminal output",
    arguments: dict | None = None,
    output: dict | None = None,
    include_call: bool = True,
    include_result: bool = True,
):
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


def _top_level_collapsible_titles(viewer: TrajectoryViewer) -> list[str]:
    return [child.title for child in viewer._detail_wrap.children if isinstance(child, Collapsible)]


def _all_collapsible_titles(viewer: TrajectoryViewer) -> list[str]:
    return [widget.title for widget in viewer._detail_wrap.query(Collapsible)]


def _collapsible_by_title(viewer: TrajectoryViewer, title: str) -> Collapsible:
    for widget in viewer._detail_wrap.query(Collapsible):
        if widget.title == title:
            return widget
    raise AssertionError(f"Collapsible with title {title!r} not found")
