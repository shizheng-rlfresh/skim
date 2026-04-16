"""Application shell and top-level interaction routing for skim.

This module owns the outer browser layout, pane grid, global status bar, split/close
behavior, and app-level keyboard routing. It does not own file preview parsing or
trajectory rendering internals, which live in dedicated modules.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Header, Static

from .preview import PreviewPane
from .scrolling import DirectoryTree
from .trajectory import JsonInspector, TrajectoryViewer

MAX_ROWS = 2
MAX_COLS = 3
SCROLL_STEP = 3
PAGE_SCROLL_STEP = 20


class SkimApp(App):
    """Main skim application."""

    TITLE = "skim"
    CSS = """
    #outer {
        height: 1fr;
    }
    DirectoryTree {
        width: 1fr;
        max-width: 40;
        border-right: solid $primary-background;
    }
    #preview-area {
        width: 3fr;
    }
    .pane-row {
        height: 1fr;
    }
    PreviewPane {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
        border: round $background;
    }
    PreviewPane:focus {
        border: round $accent;
    }
    PreviewPane.active-pane {
        border: round $accent;
    }
    TrajectoryViewer, JsonInspector {
        width: 1fr;
    }
    .trajectory-body {
        height: 1fr;
    }
    .trajectory-tree {
        width: 1fr;
        min-width: 28;
        height: 1fr;
    }
    .trajectory-detail-column {
        width: 2fr;
        height: 1fr;
    }
    .annotation-status-panel {
        height: 8;
        min-height: 8;
        border: round $panel-lighten-1;
        background: $surface-lighten-1;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    .trajectory-detail-wrap {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
    }
    .trajectory-detail-field {
        padding: 0 1;
    }
    .trajectory-footer {
        height: 1;
        color: $text-muted;
        background: $surface-lighten-1;
        padding: 0 1;
        margin: 1 0 0 0;
    }
    #annotation-modal {
        width: 140;
        max-width: 96%;
        height: 80%;
        max-height: 90%;
        padding: 1;
        border: round $accent;
        background: $surface;
    }
    .annotation-modal-body {
        height: 1fr;
    }
    .annotation-modal-panel {
        height: 1fr;
        padding: 0 1;
        border: round $panel-lighten-1;
    }
    #annotation-editor-panel {
        width: 2fr;
        margin: 0 1 0 0;
    }
    #annotation-preview-panel {
        width: 3fr;
    }
    .annotation-modal-preview {
        height: 1fr;
        margin: 1 0 0 0;
    }
    .annotation-modal-actions {
        height: auto;
        margin: 1 0 0 0;
    }
    #annotation-tags {
        margin: 1 0 0 0;
    }
    #annotation-note {
        height: 1fr;
        min-height: 8;
        margin: 1 0 0 0;
    }
    Collapsible.trajectory-section {
        margin: 0 0 1 0;
    }
    Collapsible.trajectory-section-selected {
        border: round $accent;
    }
    Collapsible.trajectory-section-secondary {
        border: round $panel-lighten-1;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    .key {
        background: $primary-background;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", show=False),
        Binding("up", "scroll_up", show=False, priority=True),
        Binding("down", "scroll_down", show=False, priority=True),
        Binding("j", "scroll_down", show=False, priority=True),
        Binding("k", "scroll_up", show=False, priority=True),
        Binding("pageup", "page_up", show=False, priority=True),
        Binding("pagedown", "page_down", show=False, priority=True),
        Binding("f", "focus_file_tree", show=False),
        Binding("s", "enter_split", show=False),
        Binding("d", "close_pane", show=False),
        Binding("w", "cycle_pane", show=False),
    ]

    def __init__(self, path: str | Path = "."):
        """Initialize the app for a directory path."""
        super().__init__()
        self.browse_path = Path(path).expanduser().resolve()
        self.pane_counter = 0
        self.active_pane_id: str = ""
        self.grid: list[list[str]] = []
        self.pane_files: dict[str, Path | None] = {}
        self.split_mode = False
        self.file_tree_mode = False

    def _new_pane_id(self) -> str:
        """Return the next stable preview-pane identifier."""
        pid = f"pane-{self.pane_counter}"
        self.pane_counter += 1
        return pid

    def _total_panes(self) -> int:
        """Return the total number of preview panes in the current grid."""
        return sum(len(row) for row in self.grid)

    def _find_pane(self, pane_id: str) -> tuple[int | None, int | None]:
        """Return the row and column for a pane id, if it exists."""
        for row_index, row in enumerate(self.grid):
            for column_index, candidate in enumerate(row):
                if candidate == pane_id:
                    return row_index, column_index
        return None, None

    def compose(self) -> ComposeResult:
        """Compose the directory tree and preview area."""
        yield Header()
        with Horizontal(id="outer"):
            yield DirectoryTree(str(self.browse_path))
            yield Vertical(id="preview-area")
        yield Static("", id="status-bar")

    def on_mount(self) -> None:
        """Create the first preview pane and start in preview focus mode."""
        pane_id = self._new_pane_id()
        self.grid = [[pane_id]]
        self.pane_files[pane_id] = None
        self.active_pane_id = pane_id
        self._rebuild_layout()
        self.exit_file_tree_mode()

    def _rebuild_layout(self) -> None:
        """Rebuild the preview pane grid from current state."""
        area = self.query_one("#preview-area")
        area.remove_children()
        for row in self.grid:
            container = Horizontal(classes="pane-row")
            area.mount(container)
            for pane_id in row:
                pane = PreviewPane(id=pane_id)
                container.mount(pane)
                path = self.pane_files.get(pane_id)
                if path:
                    pane.show_file(path)
                else:
                    pane.show_placeholder()
        self._update_active_indicator()

    def set_active_pane(self, pane_id: str) -> None:
        """Set the active preview pane by id."""
        self.active_pane_id = pane_id
        self._update_active_indicator()

    def _update_active_indicator(self) -> None:
        """Refresh which pane is visually marked as active."""
        for pane in self.query(PreviewPane):
            pane.remove_class("active-pane")
        try:
            self.query_one(f"#{self.active_pane_id}", PreviewPane).add_class("active-pane")
        except Exception:
            pass

    def _status_text(self) -> str:
        """Return status-bar text for the current app mode."""
        if self.file_tree_mode:
            return (
                " [bold]q[/] Quit  "
                "[bold]↑↓[/] Move  "
                "[bold]←→[/] Branch  "
                "[bold]Esc[/] Back  "
                "[bold]s[/]+arrow Split  "
                "[bold]d[/] Close  "
                "[bold]w[/] Next pane"
            )
        return (
            " [bold]q[/] Quit  "
            "[bold]↑↓[/] Scroll  "
            "[bold]PgUp/Dn[/] Page  "
            "[bold]f[/] Tree  "
            "[bold]s[/]+arrow Split  "
            "[bold]d[/] Close  "
            "[bold]w[/] Next pane"
        )

    def _update_status_bar(self) -> None:
        """Refresh the global status bar text."""
        self.query_one("#status-bar", Static).update(self._status_text())

    def _modal_is_active(self) -> bool:
        """Return whether a modal screen currently owns keyboard interaction."""
        return isinstance(self.screen, ModalScreen)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Disable app-level arrow scrolling while a modal owns focus."""
        if self._modal_is_active() and action in {"scroll_up", "scroll_down"}:
            return False
        return super().check_action(action, parameters)

    def action_quit(self) -> None:
        """Quit the app unless a modal screen is active."""
        if self._modal_is_active():
            return
        self.exit()

    def action_focus_file_tree(self) -> None:
        """Toggle focus between the file tree and the active preview pane."""
        if self._modal_is_active():
            return
        if self.file_tree_mode:
            self.exit_file_tree_mode()
            return
        self.file_tree_mode = True
        self.query_one(DirectoryTree).focus(scroll_visible=False)
        self._update_status_bar()

    def exit_file_tree_mode(self) -> None:
        """Leave file-tree focus mode and return to the active preview pane."""
        self.file_tree_mode = False
        self._update_active_indicator()
        try:
            self.query_one(f"#{self.active_pane_id}", PreviewPane).focus(scroll_visible=False)
        except Exception:
            pass
        self._update_status_bar()

    def action_scroll_down(self) -> None:
        """Scroll down in the active pane or confirm a downward split."""
        if self._modal_is_active():
            return
        if self.split_mode:
            self.split_mode = False
            self._split("down")
            return
        if self.file_tree_mode:
            self.action_tree_down()
            return
        try:
            pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
            pane.scroll_content(SCROLL_STEP)
        except Exception:
            pass

    def action_scroll_up(self) -> None:
        """Scroll up in the active pane or confirm an upward split."""
        if self._modal_is_active():
            return
        if self.split_mode:
            self.split_mode = False
            self._split("up")
            return
        if self.file_tree_mode:
            self.action_tree_up()
            return
        try:
            pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
            pane.scroll_content(-SCROLL_STEP)
        except Exception:
            pass

    def action_tree_up(self) -> None:
        """Move the directory tree cursor up."""
        if self._modal_is_active():
            return
        self.query_one(DirectoryTree).action_cursor_up()

    def action_tree_down(self) -> None:
        """Move the directory tree cursor down."""
        if self._modal_is_active():
            return
        self.query_one(DirectoryTree).action_cursor_down()

    def action_tree_select(self) -> None:
        """Open the currently selected tree item."""
        if self._modal_is_active():
            return
        self.query_one(DirectoryTree).action_select_cursor()

    def action_tree_left(self) -> None:
        """Collapse the current file-tree branch or move to its parent."""
        if self._modal_is_active():
            return
        tree = self.query_one(DirectoryTree)
        node = tree.cursor_node
        if node is None:
            return
        if node.allow_expand and node.is_expanded:
            node.collapse()
            return
        if node.parent is not None:
            tree.move_cursor(node.parent, animate=False)

    def action_tree_right(self) -> None:
        """Expand the current file-tree branch, move into it, or open a file."""
        if self._modal_is_active():
            return
        tree = self.query_one(DirectoryTree)
        node = tree.cursor_node
        if node is None:
            return
        if node.allow_expand:
            if node.is_collapsed:
                node.expand()
                return
            if node.children:
                tree.move_cursor(node.children[0], animate=False)
            return
        self.action_tree_select()

    def action_page_down(self) -> None:
        """Scroll the active content by a page-sized amount."""
        if self._modal_is_active():
            screen = self.screen
            action = getattr(screen, "action_scroll_preview_down", None)
            if callable(action):
                action()
            return
        try:
            pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
            viewer = pane.active_json_navigator()
            if isinstance(viewer, JsonInspector):
                viewer.scroll_detail(PAGE_SCROLL_STEP)
                return
            pane.scroll_relative(y=PAGE_SCROLL_STEP, animate=False)
        except Exception:
            pass

    def action_page_up(self) -> None:
        """Scroll the active content up by a page-sized amount."""
        if self._modal_is_active():
            screen = self.screen
            action = getattr(screen, "action_scroll_preview_up", None)
            if callable(action):
                action()
            return
        try:
            pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
            viewer = pane.active_json_navigator()
            if isinstance(viewer, JsonInspector):
                viewer.scroll_detail(-PAGE_SCROLL_STEP)
                return
            pane.scroll_relative(y=-PAGE_SCROLL_STEP, animate=False)
        except Exception:
            pass

    def on_key(self, event: Key) -> None:
        """Handle split-mode keys and tree navigation shortcuts."""
        if self._modal_is_active():
            return

        if self.split_mode:
            direction_map = {
                "left": "left",
                "right": "right",
                "up": "up",
                "down": "down",
                "h": "left",
                "l": "right",
                "k": "up",
                "j": "down",
            }
            direction = direction_map.get(event.key)
            self.split_mode = False
            if direction:
                self._split(direction)
            event.prevent_default()
            event.stop()
            return

        if self.file_tree_mode:
            if event.key in {"up", "k"}:
                self.action_tree_up()
                event.prevent_default()
                event.stop()
                return
            if event.key in {"down", "j"}:
                self.action_tree_down()
                event.prevent_default()
                event.stop()
                return
            if event.key == "left":
                self.action_tree_left()
                event.prevent_default()
                event.stop()
                return
            if event.key == "right":
                self.action_tree_right()
                event.prevent_default()
                event.stop()
                return
            if event.key == "enter":
                self.action_tree_select()
                event.prevent_default()
                event.stop()
                return
            if event.key == "escape":
                self.exit_file_tree_mode()
                event.prevent_default()
                event.stop()
                return

        viewer: JsonInspector | TrajectoryViewer | None = None
        try:
            active_pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
            viewer = active_pane.active_json_navigator()
        except Exception:
            viewer = None

        if viewer is not None and event.key in {"left", "right"}:
            if viewer.handle_horizontal_key(event.key):
                event.prevent_default()
                event.stop()
                return

        if viewer is not None and event.key == "escape":
            if viewer.handle_escape_key():
                event.prevent_default()
                event.stop()
                return

        if viewer is not None and event.key == "enter":
            if viewer.handle_enter_key():
                event.prevent_default()
                event.stop()
                return

        if isinstance(viewer, JsonInspector) and event.key == "a":
            if viewer.handle_annotation_key():
                event.prevent_default()
                event.stop()
                return

        if event.key == "shift+down":
            self.action_tree_down()
            event.prevent_default()
            event.stop()
        elif event.key == "shift+up":
            self.action_tree_up()
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            self.action_tree_select()
            event.prevent_default()
            event.stop()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Open a selected file in the active preview pane."""
        path = Path(event.path)
        pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
        pane.show_file(path)
        self.pane_files[self.active_pane_id] = path
        if self.file_tree_mode:
            self.exit_file_tree_mode()

    def action_enter_split(self) -> None:
        """Enter split mode for the next direction key."""
        if self._modal_is_active():
            return
        if self._total_panes() >= MAX_ROWS * MAX_COLS:
            self.notify("Maximum 6 panes reached", severity="warning")
            return
        self.split_mode = True
        self.notify("Split: arrow or h/j/k/l, Esc cancel", timeout=2)

    def _split(self, direction: str) -> None:
        row_index, column_index = self._find_pane(self.active_pane_id)
        if row_index is None or column_index is None:
            return

        new_id = self._new_pane_id()
        self.pane_files[new_id] = None

        if direction in ("left", "right"):
            if len(self.grid[row_index]) < MAX_COLS:
                position = column_index + 1 if direction == "right" else column_index
                self.grid[row_index].insert(position, new_id)
            elif not self._try_overflow(new_id):
                return

        elif direction in ("up", "down"):
            target_row = 0 if direction == "up" else 1
            if target_row >= len(self.grid):
                self.grid.append([])
            if len(self.grid[target_row]) < MAX_COLS:
                insert_at = min(column_index, len(self.grid[target_row]))
                self.grid[target_row].insert(insert_at, new_id)
            elif not self._try_overflow(new_id):
                return

        self.active_pane_id = new_id
        self._rebuild_layout()

    def _try_overflow(self, new_id: str) -> bool:
        """Place a new pane in the first available row/column slot."""
        for row_index in range(MAX_ROWS):
            if row_index < len(self.grid) and len(self.grid[row_index]) < MAX_COLS:
                self.grid[row_index].append(new_id)
                return True
            if row_index >= len(self.grid):
                self.grid.append([new_id])
                return True
        self.notify("No room for new pane", severity="warning")
        return False

    def action_close_pane(self) -> None:
        """Close the active pane unless it is the last one."""
        if self._modal_is_active():
            return
        if self._total_panes() <= 1:
            self.notify("Cannot close last pane", severity="warning")
            return

        row_index, column_index = self._find_pane(self.active_pane_id)
        if row_index is None or column_index is None:
            return

        self.pane_files.pop(self.active_pane_id, None)
        self.grid[row_index].pop(column_index)
        if not self.grid[row_index]:
            self.grid.pop(row_index)

        next_row = min(row_index, len(self.grid) - 1)
        next_column = min(column_index, len(self.grid[next_row]) - 1)
        self.active_pane_id = self.grid[next_row][next_column]
        self._rebuild_layout()
        try:
            self.query_one(f"#{self.active_pane_id}", PreviewPane).focus()
        except Exception:
            pass

    def action_cycle_pane(self) -> None:
        """Cycle the active pane through the current grid order."""
        if self._modal_is_active():
            return
        panes = [pane_id for row in self.grid for pane_id in row]
        if len(panes) <= 1:
            return
        index = panes.index(self.active_pane_id)
        self.active_pane_id = panes[(index + 1) % len(panes)]
        self._update_active_indicator()


def main() -> None:
    """Run the app from the command line."""
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    app = SkimApp(path)
    app.run()


def dev() -> None:
    """Run the app through Textual's dev server."""
    subprocess.run(["textual", "run", "--dev", "skim:SkimApp"], check=False)
