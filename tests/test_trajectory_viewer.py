"""Trajectory-viewer tests for skim.

This module covers trajectory normalization, tree construction, detail rendering,
local viewer controls, and specialized drag/keyboard behavior. It does not own
outer app-shell layout or generic preview classification.
"""

import json

from conftest import (
    _all_collapsible_titles,
    _collapsible_by_title,
    _detail_syntax_blocks,
    _detail_text,
    _static_content,
    _top_level_collapsible_titles,
    _tree_labels,
    multi_step_trajectory,
    sample_trajectory,
)
from rich.syntax import Syntax
from rich.text import Text
from textual.widgets import Markdown, Static, Tree

from skim import PreviewPane, SkimApp, TrajectoryViewer, normalize_events


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
