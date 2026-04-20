# skim

A terminal UI for browsing folders and reviewing local artifacts. Built with
[Textual](https://textual.textualize.io/).

Point it at any directory to get a file tree on the left and a content preview on the
right, with syntax highlighting, markdown rendering, split panes, flat `.ipynb`
rendering, and a **JSON inspector** that now supports `local node annotations`.

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
uv run skim-dev          # launch Textual dev mode
uv run skim-web .        # run the localhost web UI
```

## Web UI

The repo also includes a localhost browser UI:

```bash
uv run skim-web .
```

The current implementation is Python-first and localhost-only, backed by typed
preview payloads from `/api/preview`.

See the full target design spec here:

- [docs/skim-web-ui-spec.md](./docs/skim-web-ui-spec.md)

## Keybindings

### Shell And Pane Navigation

| Key | Action |
|---|---|
| `Up/Down` or `j/k` | Scroll the active preview pane |
| `PageUp/PageDown` | Page-scroll the active preview pane; in JSON inspector mode, scroll the detail panel |
| `f` | Toggle file-tree mode |
| `Shift+Up/Down` | Move the file-tree cursor without leaving the active preview |
| `Enter` | Open the current file-tree selection in the active pane |
| `s` then arrow or `h/j/k/l` | Split in a direction |
| `d` | Close the active pane |
| `w` | Cycle to the next pane |
| `q` | Quit |

### File-Tree Mode

| Key | Action |
|---|---|
| `Up/Down` or `j/k` | Move the file-tree cursor |
| `Left/Right` | Collapse, expand, or move across file-tree branches |
| `Right` on a file | Open that file in the active pane |
| `Enter` | Open the selected file or directory entry |
| `Esc` | Return to the active preview pane |

Trajectory and JSON previews show their own local command footers when they have
specialized navigation. Flat notebook previews use the generic pane scrolling above.

### Trajectory Preview

Trajectory previews use a tree/detail model:

| Key | Action |
|---|---|
| `Up/Down` | Move through the trajectory tree while in tree mode |
| `Left/Right` | Collapse, expand, or move across trajectory tree branches |
| `Enter` | Open the selected trajectory node in the detail pane |
| `Esc` | Return from the detail pane to the trajectory tree |

### JSON Inspector

JSON previews use a live inspector model:

| Key | Action |
|---|---|
| `Up/Down` | Move the JSON tree cursor |
| `Left/Right` | Collapse, expand, or move across JSON tree branches |
| `PageUp/PageDown` | Scroll the right-hand detail panel |
| `a` | Open the annotation editor for the selected annotatable node |

### Annotation Modal

| Key | Action |
|---|---|
| `Esc` | Close the modal |
| `Tab` | Move to the next editor control |
| `Enter` in tags | Jump directly to the note field |
| `PageUp/PageDown` | Scroll the right-hand node preview |

## Split panes

You can have up to 6 panes arranged in a 2 row by 3 column grid. Press `s` followed by a direction key to split. The active pane is highlighted with a border. Click a pane or press `w` to switch which pane is active. New files always open in the active pane.

## JSON review workflow

JSON files open in a structural inspector rather than a plain text dump. The inspector:

- shows a tree on the left and detail panels on the right
- adds schema-aware overlays for supported artifacts such as raw agent trajectories.
- keeps annotations local in `<browse-root>/.skim/review.json`
- marks annotated nodes in the tree and shows annotation state in a separate status panel
- opens a split annotation modal with tags and note editing on the left and a read-only
  preview of the selected node on the right

Annotations bind to the underlying raw JSON location, using `annotation_path` when an
overlay node maps to a raw node and falling back to `raw_path` otherwise.

## File size limits

Files over `1MB` are skipped to keep text previews responsive. JSON and notebook
(`.ipynb`) files get a higher limit of `10MB`.

## License

MIT
