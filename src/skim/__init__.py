"""skim: A TUI for browsing folders and previewing files."""

import json
import sys
from pathlib import Path

from rich.syntax import Syntax
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import DirectoryTree, Footer, Header, Static


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

MAX_FILE_SIZE = 1_000_000  # 1MB preview limit


class FilePreview(Static):
    """Right panel that shows file contents."""

    def show_placeholder(self) -> None:
        self.update(Text("Select a file to preview", style="dim italic"))

    def show_error(self, message: str) -> None:
        self.update(Text(message, style="red"))

    def show_file(self, path: Path) -> None:
        if not path.is_file():
            self.show_error(f"Not a file: {path.name}")
            return

        size = path.stat().st_size
        if size > MAX_FILE_SIZE:
            self.show_error(f"{path.name} is too large to preview ({size:,} bytes)")
            return

        try:
            content = path.read_text(errors="replace")
        except Exception as e:
            self.show_error(f"Could not read {path.name}: {e}")
            return

        suffix = path.suffix.lower()

        # Pretty print JSON
        if suffix == ".json":
            try:
                parsed = json.loads(content)
                content = json.dumps(parsed, indent=2)
            except json.JSONDecodeError:
                pass

        # Syntax highlight if we know the language
        lexer = SYNTAX_MAP.get(suffix)
        if lexer:
            self.update(Syntax(content, lexer, line_numbers=True, word_wrap=True))
        else:
            self.update(Text(content))


class SkimApp(App):
    """Main application."""

    TITLE = "skim"
    CSS = """
    Horizontal {
        height: 1fr;
    }
    DirectoryTree {
        width: 1fr;
        max-width: 40;
        border-right: solid $primary-background;
    }
    FilePreview {
        width: 3fr;
        overflow-y: auto;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, path: str | Path):
        super().__init__()
        self.browse_path = Path(path).resolve()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield DirectoryTree(str(self.browse_path))
            yield FilePreview(id="preview")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(FilePreview).show_placeholder()

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        self.query_one(FilePreview).show_file(Path(event.path))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    app = SkimApp(path)
    app.run()