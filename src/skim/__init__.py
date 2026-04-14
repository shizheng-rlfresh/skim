"""skim: A TUI for browsing folders and previewing files."""

import json
import sys
from pathlib import Path

from rich.syntax import Syntax
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Key
from textual.widgets import DirectoryTree, Header, Markdown, Static

SYNTAX_MAP = {
    ".py": "python",
    ".json": "json",
    ".js": "javascript",
    ".ts": "typescript",
    ".html": "html",
    ".css": "css",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".sh": "bash",
    ".bash": "bash",
    ".rs": "rust",
    ".go": "go",
    ".sql": "sql",
    ".xml": "xml",
    ".csv": "csv",
}

MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdown"}
MAX_FILE_SIZE = 1_000_000
MAX_ROWS = 2
MAX_COLS = 3
SCROLL_STEP = 3


def render_file(path: Path) -> list:
    """Return a list of widgets for the given file."""
    if not path.is_file():
        return [Static(Text(f"Not a file: {path.name}", style="red"))]

    size = path.stat().st_size
    if size > MAX_FILE_SIZE:
        return [Static(Text(f"{path.name} is too large ({size:,} bytes)", style="red"))]

    try:
        content = path.read_text(errors="replace")
    except Exception as e:
        return [Static(Text(f"Could not read {path.name}: {e}", style="red"))]

    suffix = path.suffix.lower()

    if suffix in MARKDOWN_EXTENSIONS:
        return [Markdown(content)]

    if suffix == ".json":
        try:
            parsed = json.loads(content)
            content = json.dumps(parsed, indent=2)
        except json.JSONDecodeError:
            pass

    lexer = SYNTAX_MAP.get(suffix)
    if lexer:
        return [Static(Syntax(content, lexer, line_numbers=True, word_wrap=True))]
    return [Static(Text(content))]


class PreviewPane(VerticalScroll, can_focus=True):
    """Scrollable panel that shows file contents."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.current_path: Path | None = None

    def show_placeholder(self, message: str = "Select a file") -> None:
        self.current_path = None
        self.remove_children()
        self.mount(Static(Text(message, style="dim italic")))

    def show_file(self, path: Path) -> None:
        self.current_path = path
        self.remove_children()
        for widget in render_file(path):
            self.mount(widget)
        self.scroll_home(animate=False)

    def on_click(self) -> None:
        self.app.set_active_pane(self.id)


class SkimApp(App):
    """Main application."""

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
    PreviewPane.active-pane {
        border: round $accent;
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
        Binding("s", "enter_split", show=False),
        Binding("d", "close_pane", show=False),
        Binding("w", "cycle_pane", show=False),
    ]

    STATUS_TEXT = (
        " [bold]q[/] Quit  "
        "[bold]↑↓[/] Scroll  "
        "[bold]⇧↑↓[/] Tree  "
        "[bold]Enter[/] Open  "
        "[bold]s[/]+arrow Split  "
        "[bold]d[/] Close  "
        "[bold]w[/] Next pane"
    )

    def __init__(self, path: str | Path = "."):
        super().__init__()
        self.browse_path = Path(path).expanduser().resolve()
        self.pane_counter = 0
        self.active_pane_id: str = ""
        self.grid: list[list[str]] = []
        self.pane_files: dict[str, Path | None] = {}
        self.split_mode = False

    def _new_pane_id(self) -> str:
        pid = f"pane-{self.pane_counter}"
        self.pane_counter += 1
        return pid

    def _total_panes(self) -> int:
        return sum(len(row) for row in self.grid)

    def _find_pane(self, pane_id: str) -> tuple[int | None, int | None]:
        for r, row in enumerate(self.grid):
            for c, pid in enumerate(row):
                if pid == pane_id:
                    return r, c
        return None, None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="outer"):
            yield DirectoryTree(str(self.browse_path))
            yield Vertical(id="preview-area")
        yield Static(self.STATUS_TEXT, id="status-bar")

    def on_mount(self) -> None:
        pid = self._new_pane_id()
        self.grid = [[pid]]
        self.pane_files[pid] = None
        self.active_pane_id = pid
        self._rebuild_layout()
        self.query_one(DirectoryTree).focus()

    def _rebuild_layout(self) -> None:
        area = self.query_one("#preview-area")
        area.remove_children()
        for r, row in enumerate(self.grid):
            h = Horizontal(classes="pane-row")
            area.mount(h)
            for pid in row:
                pane = PreviewPane(id=pid)
                h.mount(pane)
                path = self.pane_files.get(pid)
                if path:
                    pane.show_file(path)
                else:
                    pane.show_placeholder()
        self._update_active_indicator()

    def set_active_pane(self, pane_id: str) -> None:
        self.active_pane_id = pane_id
        self._update_active_indicator()

    def _update_active_indicator(self) -> None:
        for pane in self.query(PreviewPane):
            pane.remove_class("active-pane")
        try:
            self.query_one(f"#{self.active_pane_id}", PreviewPane).add_class("active-pane")
        except Exception:
            pass

    # --- scrolling the active pane ---

    def action_scroll_down(self) -> None:
        if self.split_mode:
            self.split_mode = False
            self._split("down")
            return
        try:
            pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
            pane.scroll_relative(y=SCROLL_STEP, animate=False)
        except Exception:
            pass

    def action_scroll_up(self) -> None:
        if self.split_mode:
            self.split_mode = False
            self._split("up")
            return
        try:
            pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
            pane.scroll_relative(y=-SCROLL_STEP, animate=False)
        except Exception:
            pass

    # --- tree navigation ---

    def action_tree_up(self) -> None:
        self.query_one(DirectoryTree).action_cursor_up()

    def action_tree_down(self) -> None:
        self.query_one(DirectoryTree).action_cursor_down()

    def action_tree_select(self) -> None:
        self.query_one(DirectoryTree).action_select_cursor()

    # --- split mode and tree nav key handler ---

    def on_key(self, event: Key) -> None:
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

        # shift+arrows navigate the file tree, enter opens
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

    # --- file selection ---

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        path = Path(event.path)
        pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
        pane.show_file(path)
        self.pane_files[self.active_pane_id] = path

    # --- split ---

    def action_enter_split(self) -> None:
        if self._total_panes() >= MAX_ROWS * MAX_COLS:
            self.notify("Maximum 6 panes reached", severity="warning")
            return
        self.split_mode = True
        self.notify("Split: arrow or h/j/k/l, Esc cancel", timeout=2)

    def _split(self, direction: str) -> None:
        r, c = self._find_pane(self.active_pane_id)
        if r is None or c is None:
            return

        new_id = self._new_pane_id()
        self.pane_files[new_id] = None

        if direction in ("left", "right"):
            if len(self.grid[r]) < MAX_COLS:
                pos = c + 1 if direction == "right" else c
                self.grid[r].insert(pos, new_id)
            elif not self._try_overflow(new_id):
                return

        elif direction in ("up", "down"):
            target = 0 if direction == "up" else 1
            if target >= len(self.grid):
                self.grid.append([])
            if len(self.grid[target]) < MAX_COLS:
                insert_at = min(c, len(self.grid[target]))
                self.grid[target].insert(insert_at, new_id)
            elif not self._try_overflow(new_id):
                return

        self.active_pane_id = new_id
        self._rebuild_layout()

    def _try_overflow(self, new_id: str) -> bool:
        for i in range(MAX_ROWS):
            if i < len(self.grid) and len(self.grid[i]) < MAX_COLS:
                self.grid[i].append(new_id)
                return True
            if i >= len(self.grid):
                self.grid.append([new_id])
                return True
        self.notify("No room for new pane", severity="warning")
        return False

    # --- close pane ---

    def action_close_pane(self) -> None:
        if self._total_panes() <= 1:
            self.notify("Cannot close last pane", severity="warning")
            return

        r, c = self._find_pane(self.active_pane_id)
        if r is None or c is None:
            return

        self.pane_files.pop(self.active_pane_id, None)
        self.grid[r].pop(c)
        if not self.grid[r]:
            self.grid.pop(r)

        row_idx = min(r, len(self.grid) - 1)
        col_idx = min(c, len(self.grid[row_idx]) - 1)
        self.active_pane_id = self.grid[row_idx][col_idx]
        self._rebuild_layout()
        try:
            self.query_one(f"#{self.active_pane_id}", PreviewPane).focus()
        except Exception:
            pass

    # --- cycle panes ---

    def action_cycle_pane(self) -> None:
        all_panes = [pid for row in self.grid for pid in row]
        if len(all_panes) <= 1:
            return
        idx = all_panes.index(self.active_pane_id)
        self.active_pane_id = all_panes[(idx + 1) % len(all_panes)]
        self._update_active_indicator()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    app = SkimApp(path)
    app.run()


def dev():
    import subprocess

    subprocess.run(["textual", "run", "--dev", "skim:SkimApp"])
