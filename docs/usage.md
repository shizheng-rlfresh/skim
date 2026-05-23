# skim usage

This guide covers the operational commands for SKIM's TUI, Web UI, annotation
CLI, and local verification workflow.

## Install

```bash
git clone https://github.com/shizheng-rlfresh/skim.git
cd skim
uv sync
```

Requires Python 3.12 or newer.

## TUI

```bash
uv run skim              # open current directory
uv run skim ~/my/folder  # open a specific folder
uv run skim . --triage   # start directly in triage mode
uv run skim-dev          # launch Textual dev mode
```

The TUI keeps the browser shell stable: directory tree on the left, preview
panes on the right, and specialized previews inside panes for supported files.

### Shell and pane navigation

| Key | Action |
|---|---|
| `Up/Down` or `j/k` | Scroll the active preview pane |
| `PageUp/PageDown` | Page-scroll the active preview pane; in JSON inspector mode, scroll the detail panel |
| `f` | Toggle file-tree mode |
| `t` | Switch to triage mode |
| `b` | Switch back to browse mode |
| `Shift+Up/Down` | Move the file-tree cursor without leaving the active preview |
| `Enter` | Open the current file-tree selection in the active pane |
| `s` then arrow or `h/j/k/l` | Split in a direction |
| `d` | Close the active pane |
| `w` | Cycle to the next pane |
| `q` | Quit |

### File-tree mode

| Key | Action |
|---|---|
| `Up/Down` or `j/k` | Move the file-tree cursor |
| `Left/Right` | Collapse, expand, or move across file-tree branches |
| `Right` on a file | Open that file in the active pane |
| `Enter` | Open the selected file or directory entry |
| `Esc` | Return to the active preview pane |

### Trajectory preview

| Key | Action |
|---|---|
| `Up/Down` | Move through the trajectory tree while in tree mode |
| `Left/Right` | Collapse, expand, or move across trajectory tree branches |
| `Enter` | Open the selected trajectory node in the detail pane |
| `Esc` | Return from the detail pane to the trajectory tree |

### JSON inspector

| Key | Action |
|---|---|
| `Up/Down` | Move the JSON tree cursor |
| `Left/Right` | Collapse, expand, or move across JSON tree branches |
| `PageUp/PageDown` | Scroll the right-hand detail panel |
| `a` | Open the annotation editor for the selected annotatable node |

### Annotation modal

| Key | Action |
|---|---|
| `Esc` | Close the modal |
| `Tab` | Move to the next editor control |
| `Enter` in tags | Jump directly to the note field |
| `PageUp/PageDown` | Scroll the right-hand node preview |

## Web UI

```bash
uv run skim-web .
uv run skim-web ~/my/folder --port 8008
```

The Web UI is localhost-only and uses the same Python preview serialization and
annotation storage as the TUI. It includes browse and triage modes, multi-pane
preview work, annotation editing, and local dark/light themes.

## Annotation CLI

The annotation CLI is intended for agents and scripts that need to discover
review targets and mutate annotations without driving a UI.

```bash
uv run skim annotate inspect --root . --file output.json --json
uv run skim annotate add --root . --file output.json --path '$.task' --tag issue --note 'Check this' --json
uv run skim annotate list --root . --file output.json --json
uv run skim annotate update --root . --file output.json --path '$.task' --id ann-id --note 'Updated note' --json
uv run skim annotate delete --root . --file output.json --path '$.task' --id ann-id --json
```

Commands:

- `inspect --file PATH [--root PATH] [--json]` lists valid annotatable targets
  for one file.
- `add --file PATH --path TARGET --note TEXT [--tag TAG ...] [--root PATH]
  [--json]` creates an annotation.
- `list [--file PATH] [--root PATH] [--json]` lists annotations newest-first.
- `update --file PATH --path TARGET --id ID [--note TEXT] [--tag TAG ...]
  [--root PATH] [--json]` updates one annotation by id.
- `delete --file PATH --path TARGET --id ID [--root PATH] [--json]` deletes
  one annotation by id.

Agents should call `inspect` before annotating JSON. Mutation commands use
portable targets such as `@file` or JSON paths like `$.trajectory.steps[0]`.
Deep raw descendants under trajectory event/tool internals are intentionally not
annotatable because humans cannot reliably find them in the TUI or Web UI.

`delete` can still remove stale persisted annotations by exact id, even if the
current file no longer exposes that target. This allows cleanup when a file
shape changes after review.

## Annotation storage

Annotations are stored locally under:

```text
<browse-root>/.skim/review.json
```

Non-JSON previews use the reserved `@file` target key. JSON previews use
UI-visible raw or overlay paths returned by `inspect`. Workspace triage in the
TUI and Web UI is derived from the same file.

## File size limits

Rich previews are capped to keep the TUI and Web UI responsive. Most text-like
files use a 1 MB rich-preview limit. JSON and notebook files use a 10 MB
rich-preview limit. Recognized text-like files above those limits fall back to
plain text up to 25 MB. Unknown, binary, or larger files render as too large.

## Local verification

Before commit or push, run local verification in this order:

```bash
uv run ruff format .
uv run ruff check .
uv run pytest -v
```
