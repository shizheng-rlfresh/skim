"""App-shell tests for skim.

This module covers the outer browser shell: pane layout, pane focus, file-tree
focus mode, global key routing, and generic scroll behavior. It does not cover
preview classification or trajectory-specific rendering rules.
"""

import json

from conftest import _static_content
from textual.widgets import Static

from skim import JsonInspector, PreviewPane, SkimApp


async def test_app_launches():
    """App starts without crashing."""
    app = SkimApp(path=".")
    async with app.run_test():
        assert app.title == "skim"
        assert app.grid == [["pane-0"]]


async def test_app_launches_in_triage_mode():
    """The triage flag should start skim in the dedicated triage view."""
    app = SkimApp(path=".", triage=True)
    async with app.run_test() as pilot:
        await pilot.pause()

        assert app.app_mode == "triage"
        assert app.query_one("#triage-queue", Static).has_focus


async def test_app_uses_custom_titlebar_instead_of_textual_header():
    """The app should use skim-owned chrome instead of Textual's settings header."""
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        await pilot.pause()

        assert len(app.query("Header")) == 0
        titlebar = app.query_one("#app-titlebar", Static)
        content = _static_content(titlebar)
        assert isinstance(content, str)
        assert "skim" in content
        assert "Browse" in content


async def test_triage_enter_opens_selected_item_in_browse_mode(tmp_path):
    """Enter in triage mode should open the selected file back into browse."""
    review_file = tmp_path / ".skim" / "review.json"
    review_file.parent.mkdir()
    review_file.write_text(
        json.dumps(
            {
                "version": 1,
                "files": {
                    "plain.json": {
                        "annotations": {
                            "$.hello": [
                                {
                                    "id": "ann-1",
                                    "created_at": "2026-04-21T14:00:00Z",
                                    "updated_at": "2026-04-21T14:05:00Z",
                                    "tags": ["important"],
                                    "note": "keep this",
                                }
                            ]
                        }
                    }
                },
            }
        )
    )
    (tmp_path / "plain.json").write_text(json.dumps({"hello": "world"}))
    app = SkimApp(path=str(tmp_path), triage=True)

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        assert app.app_mode == "browse"
        assert pane.current_path == tmp_path / "plain.json"


async def test_triage_toggle_returns_to_selected_queue_item(tmp_path):
    """Returning to triage should preserve the queue selection from the prior open."""
    review_file = tmp_path / ".skim" / "review.json"
    review_file.parent.mkdir()
    review_file.write_text(
        json.dumps(
            {
                "version": 1,
                "files": {
                    "docs/spec.md": {
                        "annotations": {
                            "@file": [
                                {
                                    "id": "ann-file",
                                    "created_at": "2026-04-21T14:00:00Z",
                                    "updated_at": "2026-04-21T14:05:00Z",
                                    "tags": ["important"],
                                    "note": "rollout wording",
                                }
                            ]
                        }
                    }
                },
            }
        )
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "spec.md").write_text("# Spec\n")
    app = SkimApp(path=str(tmp_path), triage=True)

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert app.app_mode == "browse"

        await pilot.press("t")
        await pilot.pause()

        queue = app.query_one("#triage-queue", Static)
        content = _static_content(queue)
        assert app.app_mode == "triage"
        assert "ann-file" not in content
        assert "docs/spec.md" in content
        assert "> File" in content
        assert app.triage_selected_annotation_id == "ann-file"


async def test_browse_shortcut_restores_browser_without_resetting_active_pane(tmp_path):
    """Switching through triage should preserve the current browse pane content."""
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello world")
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        pane.show_file(test_file)
        await pilot.pause()

        await pilot.press("t")
        await pilot.pause()
        assert app.app_mode == "triage"

        await pilot.press("b")
        await pilot.pause()

        assert app.app_mode == "browse"
        assert pane.current_path == test_file


async def test_triage_queue_groups_annotations_by_file(tmp_path):
    """The TUI triage queue should group visible annotations under one file header."""
    review_file = tmp_path / ".skim" / "review.json"
    review_file.parent.mkdir()
    review_file.write_text(
        json.dumps(
            {
                "version": 1,
                "files": {
                    "output.json": {
                        "annotations": {
                            "$.task": [
                                {
                                    "id": "ann-task",
                                    "created_at": "2026-04-21T14:10:00Z",
                                    "updated_at": "2026-04-21T14:15:00Z",
                                    "tags": ["bug"],
                                    "note": "task summary",
                                }
                            ],
                            "$.result": [
                                {
                                    "id": "ann-result",
                                    "created_at": "2026-04-21T14:20:00Z",
                                    "updated_at": "2026-04-21T14:25:00Z",
                                    "tags": ["followup"],
                                    "note": "result summary",
                                }
                            ],
                        }
                    }
                },
            }
        )
    )
    (tmp_path / "output.json").write_text(json.dumps({"task": "x", "result": "y"}))
    app = SkimApp(path=str(tmp_path), triage=True)

    async with app.run_test() as pilot:
        await pilot.pause()

        queue = app.query_one("#triage-queue", Static)
        content = _static_content(queue)

        assert content.count("output.json") == 1
        assert "$.task" in content
        assert "$.result" in content
        assert "task summary" in content
        assert "result summary" in content


async def test_triage_down_moves_selection_exactly_one_item(tmp_path):
    """One down-arrow press in triage should advance by exactly one annotation."""
    review_file = tmp_path / ".skim" / "review.json"
    review_file.parent.mkdir()
    review_file.write_text(
        json.dumps(
            {
                "version": 1,
                "files": {
                    "output.json": {
                        "annotations": {
                            "$.task": [
                                {
                                    "id": "ann-task",
                                    "created_at": "2026-04-21T14:10:00Z",
                                    "updated_at": "2026-04-21T14:15:00Z",
                                    "tags": ["bug"],
                                    "note": "task summary",
                                }
                            ],
                            "$.result": [
                                {
                                    "id": "ann-result",
                                    "created_at": "2026-04-21T14:20:00Z",
                                    "updated_at": "2026-04-21T14:25:00Z",
                                    "tags": ["followup"],
                                    "note": "result summary",
                                }
                            ],
                            "$.other": [
                                {
                                    "id": "ann-other",
                                    "created_at": "2026-04-21T14:30:00Z",
                                    "updated_at": "2026-04-21T14:35:00Z",
                                    "tags": ["later"],
                                    "note": "other summary",
                                }
                            ],
                        }
                    }
                },
            }
        )
    )
    (tmp_path / "output.json").write_text(json.dumps({"task": "x", "result": "y", "other": "z"}))
    app = SkimApp(path=str(tmp_path), triage=True)

    async with app.run_test() as pilot:
        await pilot.pause()

        assert app.triage_selected_annotation_id == "ann-other"

        await pilot.press("down")
        await pilot.pause()

        assert app.triage_selected_annotation_id == "ann-result"


async def test_triage_does_not_enter_split_mode(tmp_path):
    """Split mode should stay disabled while the triage shell is active."""
    review_file = tmp_path / ".skim" / "review.json"
    review_file.parent.mkdir()
    review_file.write_text(
        json.dumps(
            {
                "version": 1,
                "files": {
                    "notes.md": {
                        "annotations": {
                            "@file": [
                                {
                                    "id": "ann-file",
                                    "created_at": "2026-04-21T14:00:00Z",
                                    "updated_at": "2026-04-21T14:05:00Z",
                                    "tags": ["important"],
                                    "note": "rollout wording",
                                }
                            ]
                        }
                    }
                },
            }
        )
    )
    (tmp_path / "notes.md").write_text("# Notes\n")
    app = SkimApp(path=str(tmp_path), triage=True)

    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("s")
        await pilot.pause()

        assert not app.split_mode
        assert app._total_panes() == 1

        await pilot.press("right")
        await pilot.pause()

        assert not app.split_mode
        assert app._total_panes() == 1


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
        await pilot.press("s")
        await pilot.press("right")
        assert app._total_panes() == 2

        await pilot.press("d")
        assert app._total_panes() == 1

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

        await pilot.press("s")
        await pilot.press("right")
        assert app._total_panes() == 6


async def test_file_preview(tmp_path):
    """Selecting a file shows its content."""
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello world")

    app = SkimApp(path=str(tmp_path))
    async with app.run_test():
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        pane.show_file(test_file)
        assert pane.current_path == test_file


async def test_f_enters_file_tree_mode(tmp_path):
    """Pressing f should focus the file tree and enter tree mode."""
    (tmp_path / "one.txt").write_text("x")
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        tree = app.query_one("DirectoryTree")

        assert app.focused is pane
        assert not app.file_tree_mode

        await pilot.press("f")
        await pilot.pause()

        assert app.file_tree_mode
        assert app.focused is tree


async def test_f_toggles_back_to_active_pane(tmp_path):
    """Pressing f twice should return focus from the tree to the active pane."""
    (tmp_path / "one.txt").write_text("x")
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        tree = app.query_one("DirectoryTree")

        await pilot.press("f")
        await pilot.pause()
        assert app.file_tree_mode
        assert app.focused is tree

        await pilot.press("f")
        await pilot.pause()
        assert not app.file_tree_mode
        assert app.focused is pane
        assert pane.has_class("active-pane")


async def test_file_tree_mode_up_down_moves_tree_cursor(tmp_path):
    """While file-tree mode is active, up/down should move the tree cursor."""
    for index in range(4):
        (tmp_path / f"file_{index}.txt").write_text("x")
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one("DirectoryTree")

        await pilot.press("f")
        await pilot.pause()
        before = tree.cursor_line
        await pilot.press("down")
        await pilot.pause()

        assert tree.cursor_line > before


async def test_file_tree_mode_enter_opens_file_and_returns_to_pane(tmp_path):
    """Entering a file from tree mode should open it and restore pane focus."""
    test_file = tmp_path / "open-me.txt"
    test_file.write_text("hello")
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert pane.current_path == test_file
        assert not app.file_tree_mode
        assert app.focused is pane


async def test_file_tree_mode_escape_returns_to_active_pane(tmp_path):
    """Escape should leave file-tree mode and return focus to the preview pane."""
    (tmp_path / "one.txt").write_text("x")
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        footer = app.query_one("#status-bar", Static)

        await pilot.press("f")
        await pilot.pause()
        assert app.file_tree_mode
        assert "Back" in _static_content(footer)

        await pilot.press("escape")
        await pilot.pause()

        assert not app.file_tree_mode
        assert app.focused is pane
        content = _static_content(footer)
        assert "Tree" in content
        assert "Toggle tree" not in content


async def test_right_outside_file_tree_mode_still_routes_to_json_viewer(tmp_path):
    """Outside file-tree mode, right should keep driving the active JSON tree."""
    test_file = tmp_path / "plain.json"
    test_file.write_text(json.dumps({"alpha": {"nested": 1}, "beta": 2}))
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        pane.show_file(test_file)
        await pilot.pause()

        inspector = pane.query_one(JsonInspector)
        first_node = inspector._tree.root.children[0]
        inspector._tree.move_cursor(first_node, animate=False)
        await pilot.pause()

        assert inspector._tree.cursor_node is first_node
        assert first_node.is_collapsed

        await pilot.press("right")
        await pilot.pause()

        assert inspector._tree.cursor_node is first_node
        assert first_node.is_expanded


async def test_file_tree_mode_right_does_not_leak_to_json_viewer(tmp_path):
    """File-tree mode should consume right without mutating the active JSON tree."""
    (tmp_path / "folder").mkdir()
    test_file = tmp_path / "plain.json"
    test_file.write_text(json.dumps({"alpha": {"nested": 1}, "beta": 2}))
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        pane.show_file(test_file)
        await pilot.pause()

        inspector = pane.query_one(JsonInspector)
        first_node = inspector._tree.root.children[0]
        inspector._tree.move_cursor(first_node, animate=False)
        await pilot.pause()

        await pilot.press("f")
        await pilot.pause()
        assert app.file_tree_mode

        await pilot.press("right")
        await pilot.pause()

        assert inspector._tree.cursor_node is first_node
        assert first_node.is_collapsed


async def test_file_tree_mode_right_expands_directory(tmp_path):
    """Right should branch into a collapsed directory while file-tree mode is active."""
    child = tmp_path / "folder"
    child.mkdir()
    (child / "inside.txt").write_text("x")
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one("DirectoryTree")
        folder_node = tree.root.children[0]

        await pilot.press("f")
        await pilot.pause()
        tree.move_cursor(folder_node, animate=False)
        await pilot.pause()

        assert folder_node.is_collapsed

        await pilot.press("right")
        await pilot.pause()

        assert tree.cursor_node is folder_node
        assert folder_node.is_expanded


async def test_file_tree_mode_left_collapses_directory_then_moves_to_parent(tmp_path):
    """Left should collapse the current branch, then move up on a second press."""
    child = tmp_path / "folder"
    child.mkdir()
    (child / "inside.txt").write_text("x")
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one("DirectoryTree")
        folder_node = tree.root.children[0]

        await pilot.press("f")
        await pilot.pause()
        tree.move_cursor(folder_node, animate=False)
        folder_node.expand()
        await pilot.pause()

        assert tree.cursor_node is folder_node
        assert folder_node.is_expanded

        await pilot.press("left")
        await pilot.pause()

        assert tree.cursor_node is folder_node
        assert folder_node.is_collapsed

        await pilot.press("left")
        await pilot.pause()

        assert tree.cursor_node is tree.root


async def test_file_tree_mode_right_on_file_opens_it_and_returns_to_pane(tmp_path):
    """Right on a file should open it and leave file-tree mode."""
    test_file = tmp_path / "open-me.txt"
    test_file.write_text("hello")
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        tree = app.query_one("DirectoryTree")
        file_node = tree.root.children[0]

        await pilot.press("f")
        await pilot.pause()
        tree.move_cursor(file_node, animate=False)
        await pilot.pause()

        await pilot.press("right")
        await pilot.pause()

        assert pane.current_path == test_file
        assert not app.file_tree_mode
        assert app.focused is pane


async def test_down_outside_file_tree_mode_still_scrolls_preview_pane(tmp_path):
    """Outside file-tree mode, down should keep scrolling the active pane."""
    test_file = tmp_path / "long.txt"
    test_file.write_text("\n".join(f"line {index}" for index in range(400)))
    (tmp_path / "other.txt").write_text("x")
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(f"#{app.active_pane_id}", PreviewPane)
        tree = app.query_one("DirectoryTree")
        pane.show_file(test_file)
        await pilot.pause()

        before_scroll = pane.scroll_y
        before_cursor = tree.cursor_line
        await pilot.press("down")
        await pilot.pause()

        assert pane.scroll_y > before_scroll
        assert tree.cursor_line == before_cursor


async def test_shift_down_still_moves_file_tree_cursor(tmp_path):
    """Shift+down should remain a convenience shortcut for tree navigation."""
    for index in range(4):
        (tmp_path / f"file_{index}.txt").write_text("x")
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one("DirectoryTree")
        before = tree.cursor_line

        await pilot.press("shift+down")
        await pilot.pause()

        assert tree.cursor_line > before


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


async def test_global_footer_only_shows_app_wide_commands():
    """Global footer should not include trajectory-specific commands."""
    app = SkimApp(path=".")

    async with app.run_test() as pilot:
        await pilot.pause()

        footer = app.query_one("#status-bar", Static)
        content = _static_content(footer)

        assert isinstance(content, str)
        assert "Scroll" in content
        assert "PgUp/Dn" in content
        assert "Tree" in content
        assert "Open" not in content
        assert "Toggle tree" not in content
        assert "shortcut" not in content
        assert "JSON" not in content
        assert "Branch" not in content
        assert "Detail" not in content
        assert "Esc" not in content


async def test_file_tree_footer_shows_branch_controls(tmp_path):
    """File-tree mode footer should advertise left/right branch navigation."""
    (tmp_path / "one.txt").write_text("x")
    app = SkimApp(path=str(tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        footer = app.query_one("#status-bar", Static)

        await pilot.press("f")
        await pilot.pause()

        content = _static_content(footer)
        assert isinstance(content, str)
        assert "←→" in content
        assert "Branch" in content
        assert "Open" not in content
        assert "shortcut" not in content


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
