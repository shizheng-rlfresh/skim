"""App-shell tests for skim.

This module covers the outer browser shell: pane layout, pane focus, file-tree
focus mode, global key routing, and generic scroll behavior. It does not cover
preview classification or trajectory-specific rendering rules.
"""

from conftest import _static_content
from textual.widgets import Static

from skim import PreviewPane, SkimApp


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
        assert "File tree" in _static_content(footer)


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
        assert "File tree" in content
        assert "Open" in content
        assert "JSON" not in content
        assert "Branch" not in content
        assert "Detail" not in content
        assert "Esc" not in content


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
