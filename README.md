# skim

A terminal UI for browsing folders and previewing files. Built with [Textual](https://textual.textualize.io/).

Point it at any directory to get a file tree on the left and a content preview on the right, with syntax highlighting, markdown rendering, and a flexible split pane system.

## Install

```bash
git clone https://github.com/shizheng-rlfresh/skim.git
cd skim
uv sync
```

Requires Python 3.12 or newer.

## Usage

```bash
uv run skim              # open current directory
uv run skim ~/my/folder  # open a specific folder
```

## Keybindings

| Key | Action |
|---|---|
| `f` | Toggle between the file tree and the active preview pane |
| `Shift+Up/Down` | Move the file tree cursor |
| `Enter` | Open the selected file from the tree |
| `Esc` | Leave file-tree mode or return from trajectory detail to the trajectory tree |
| `Up/Down` or `j/k` | Scroll the active preview pane |
| `s` then arrow or `h/j/k/l` | Split in a direction |
| `d` | Close the active pane |
| `w` | Cycle to the next pane |
| `q` | Quit |

Trajectory previews have their own local controls shown in the viewer footer:

| Key | Action |
|---|---|
| `Up/Down` | Move through the trajectory tree while in JSON mode |
| `Left/Right` | Collapse, expand, or move across trajectory tree branches |
| `Enter` | Open the selected trajectory node in the detail pane |
| `Esc` | Return from the detail pane to the trajectory tree |

## Split panes

You can have up to 6 panes arranged in a 2 row by 3 column grid. Press `s` followed by a direction key to split. The active pane is highlighted with a border. Click a pane or press `w` to switch which pane is active. New files always open in the active pane.

## Supported file types

Syntax highlighting works for Python, JSON, JavaScript, TypeScript, HTML, CSS, YAML, TOML, Bash, Rust, Go, SQL, XML, and CSV. Markdown files are rendered with formatting. JSON files are pretty printed automatically. Files over 1MB are skipped to keep things responsive.

## License

MIT
