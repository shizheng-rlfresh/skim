# skim

A terminal UI for browsing folders and previewing files. Built with [Textual](https://textual.textualize.io/).

Point it at any directory to get a file tree on the left and a content preview on the right, with syntax highlighting, markdown rendering, and a flexible split pane system.

## Install

```bash
git clone https://github.com/YOUR_USERNAME/skim.git
cd skim
uv sync
```

## Usage

```bash
uv run skim              # open current directory
uv run skim ~/my/folder  # open a specific folder
```

## Keybindings

| Key | Action |
|---|---|
| `Shift+Up/Down` | Navigate the file tree |
| `Shift+Right` | Open/expand selected item |
| `Up/Down` or `j/k` | Scroll the active preview pane |
| `s` then arrow or `h/j/k/l` | Split in a direction |
| `d` | Close the active pane |
| `w` | Cycle to the next pane |
| `q` | Quit |

## Split panes

You can have up to 6 panes arranged in a 2 row by 3 column grid. Press `s` followed by a direction key to split. The active pane is highlighted with a border. Click a pane or press `w` to switch which pane is active. New files always open in the active pane.

## Supported file types

Syntax highlighting works for Python, JSON, JavaScript, TypeScript, HTML, CSS, YAML, TOML, Bash, Rust, Go, SQL, XML, and CSV. Markdown files are rendered with formatting. JSON files are pretty printed automatically. Files over 1MB are skipped to keep things responsive.

## Development

```bash
uv add ruff pytest pytest-textual-snapshot --dev
uv run skim-dev          # launch with CSS hot reload
uv run pytest -v         # run tests
uv run ruff check src/   # lint
uv run ruff format src/  # format
```

## License

MIT