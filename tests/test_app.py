"""Tests for skim."""

from skim import SkimApp


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
