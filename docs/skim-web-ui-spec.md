# skim web UI — Design Specification

## Summary

Browser-based interface for `skim`, a local trajectory review tool for ML engineers.
This document describes the **full target** web UI, not only the currently shipped
subset. The design goal is a faithful web port of the Textual TUI: file tree on the
left, preview work on the right, trajectory-aware inspection, local annotations, and
a dark terminal-like aesthetic.

Implementation constraints that are part of the spec:

- The web UI is localhost-only.
- Python is the source of truth for preview classification, typed preview payloads,
  syntax highlighting, and JSON / trajectory detail serialization.
- The browser is a thin renderer over `/api/preview` payloads, not a second logic
  layer that re-interprets local artifacts.
- No React, no CDN assets, and no browser-side syntax-highlighting dependency.

---

## Visual System

### Theme Tokens

#### Dark theme (default)

| Token | Value | Usage |
|---|---|---|
| `--bg-primary` | `#0e0e10` | Main background |
| `--bg-secondary` | `#151518` | Sidebar, title bar, status bar |
| `--bg-surface` | `#1a1a1f` | Cards, elevated surfaces |
| `--bg-hover` | `#1f1f25` | Hover state |
| `--bg-highlight` | `#1c1c24` | Selected / active state |
| `--fg-primary` | `#e0e0e4` | Primary text |
| `--fg-secondary` | `#a0a0a8` | Body text, descriptions |
| `--fg-muted` | `#606068` | Hints, line numbers, metadata |
| `--border` | `#2a2a32` | Primary borders |
| `--border-subtle` | `#1f1f27` | Subtle separators |
| `--accent` | `#7c8aff` | Active indicators, links, selection |
| `--green` | `#4ade80` | Success / resolved |
| `--red` | `#f87171` | Failed / destructive |

#### Light theme

| Token | Value | Usage |
|---|---|---|
| `--bg-primary` | `#fafaf9` | Main background |
| `--bg-secondary` | `#f3f3f0` | Sidebar, title bar |
| `--fg-primary` | `#1a1a1a` | Primary text |
| `--fg-secondary` | `#4a4a4a` | Body text |
| `--accent` | `#4f5bd5` | Active indicators |

### Syntax Tokens

Syntax colors are produced by Python-side highlighting and mounted in the browser as
HTML token classes. Both dark and light themes must define syntax colors.

| Token | Dark | Light | Usage |
|---|---|---|---|
| `--syn-keyword` | `#c792ea` | `#7c3aed` | Language keywords |
| `--syn-string` | `#c3e88d` | `#16a34a` | String literals |
| `--syn-comment` | `#545464` | `#a0a0a0` | Comments |
| `--syn-number` | `#f78c6c` | `#c2410c` | Numeric literals |
| `--syn-key` | `#82aaff` | `#2563eb` | Object keys |
| `--syn-decorator` | `#ffcb6b` | `#ca8a04` | Python decorators |

### Typography

| Role | Font | Size | Weight |
|---|---|---|---|
| Shell UI | JetBrains Mono | 13px | 400 |
| App title | JetBrains Mono | 14px | 600 |
| File tree items | JetBrains Mono | 13px | 400 |
| Code / preview | JetBrains Mono | 13px | 400 |
| Line numbers | JetBrains Mono | 13px | 400, reduced contrast |
| Labels / metadata | JetBrains Mono | 11px | 400 |
| Explorer heading | JetBrains Mono | 11px | 400, uppercase, `0.08em` tracking |
| Markdown body | System sans-serif | 14px | 400, `1.7` line-height |

### Layout Tokens

| Element | Value |
|---|---|
| Title bar height | 40px |
| Status bar height | 24px |
| Sidebar width | 220px default, resizable later |
| Pane gap | 2px |
| Pane padding | 4px outer |
| Pane header padding | 6px 12px |
| File tree indent | 16px per depth level |
| Pane radius | 4px |
| Badge radius | 3px |

---

## Product Architecture

### Shell Layout

Target shell:

- Title bar
- Left file tree
- Right preview work area
- Status bar

Multi-pane target:

- Up to 6 panes in a 2 × 3 grid
- 1–3 panes render as a single row
- 4–6 panes render as two rows with the first 3 panes on the top row
- Active pane uses the accent border
- On small screens, panes stack vertically instead of forcing the desktop grid

### Source of Truth

- `/api/tree` returns the browse tree
- `/api/preview?path=<rel>` returns typed preview payloads
- `/api/triage` returns normalized workspace annotation rows
- `/api/annotation-version` returns the current review-version token
- `/api/annotations` persists local review annotations under
  `<browse-root>/.skim/review.json`
- Python owns preview routing, syntax HTML generation, and structured detail payloads

### Local-Only Rules

- The server binds to `127.0.0.1` only
- File access is constrained to the selected browse root
- Tree / preview / annotation operations outside the browse root are forbidden

---

## API Contract

### `GET /api/tree`

Returns the recursive browse tree:

```json
{
  "name": ".",
  "type": "dir",
  "path": ".",
  "root_path": "/abs/root",
  "children": [
    {
      "name": "src",
      "type": "dir",
      "path": "src",
      "children": []
    },
    {
      "name": "README.md",
      "type": "file",
      "path": "README.md",
      "ext": ".md",
      "size": "4.1 KB"
    }
  ]
}
```

Skipped directories:

- `.git`
- `__pycache__`
- `node_modules`
- `.venv`
- `venv`
- `.tox`
- `.mypy_cache`
- `.ruff_cache`
- hidden directories except `.skim`

### `GET /api/preview?path=<rel>`

Canonical file preview endpoint. Response `kind` is one of:

- `text`
- `markdown`
- `csv`
- `notebook`
- `json_inspector`
- `trajectory`
- `too_large`
- `error`

#### `text`

```json
{
  "kind": "text",
  "name": "example.py",
  "path": "example.py",
  "language": "python",
  "content": "print('hello')\n",
  "render": {
    "kind": "syntax",
    "language": "python",
    "line_numbers": true,
    "value": "print('hello')\n",
    "html": "<div class=\"syntax-block\">...</div>"
  }
}
```

#### `markdown`

```json
{
  "kind": "markdown",
  "name": "README.md",
  "path": "README.md",
  "content": "# Title\n..."
}
```

#### `csv`

```json
{
  "kind": "csv",
  "name": "data.csv",
  "path": "data.csv",
  "columns": ["name", "value"],
  "rows": [["a", "1"]],
  "raw": "name,value\n...",
  "raw_render": {
    "kind": "syntax",
    "language": "csv",
    "line_numbers": true,
    "value": "name,value\n...",
    "html": "<div class=\"syntax-block\">...</div>"
  },
  "summary": "CSV Preview ...",
  "parse_error": null,
  "truncated_rows": false,
  "truncated_columns": false
}
```

#### `notebook`

```json
{
  "kind": "notebook",
  "name": "analysis.ipynb",
  "path": "analysis.ipynb",
  "language": "python",
  "summary": {
    "title": "Notebook Preview",
    "cell_count": 2,
    "nbformat": 4,
    "nbformat_minor": 5
  },
  "cells": [
    {
      "id": "cell-1",
      "kind": "markdown",
      "title": "Markdown Cell 1",
      "render": {
        "kind": "markdown",
        "value": "# Title\n..."
      },
      "outputs": []
    },
    {
      "id": "cell-2",
      "kind": "code",
      "title": "Code Cell 2",
      "render": {
        "kind": "syntax",
        "language": "python",
        "line_numbers": true,
        "value": "print('hi')\n",
        "html": "<div class=\"syntax-block\">...</div>"
      },
      "outputs": [
        {
          "id": "cell-2-output-1",
          "title": "Output 2.1",
          "render": {
            "kind": "text",
            "value": "hi\n"
          }
        }
      ]
    }
  ]
}
```

#### Shared render-leaf contract

Leaf render blocks used inside previews and detail panes:

- `text`
- `markdown`
- `syntax`

`syntax` shape:

```json
{
  "kind": "syntax",
  "language": "json",
  "line_numbers": false,
  "value": "{\n  \"ok\": true\n}",
  "html": "<div class=\"syntax-block\">...</div>"
}
```

#### `json_inspector`

```json
{
  "kind": "json_inspector",
  "name": "output.json",
  "path": "data/output.json",
  "initial_node_id": "node-0",
  "tree": [
    {
      "id": "node-0",
      "label": "Task {7}",
      "kind": "raw_dict_key",
      "path": "$.task",
      "raw_path": ["task"],
      "type_name": "object",
      "annotatable": true,
      "annotation_path": "$.task",
      "annotation": null,
      "children": [],
      "detail": {
        "kind": "detail",
        "blocks": []
      }
    }
  ]
}
```

Node fields:

- `id`
- `label`
- `kind`
- `path`
- `raw_path`
- `type_name`
- `annotatable`
- `annotation_path`
- `annotation`
- `children`
- `detail`

Rules:

- Wrapped trajectory artifacts such as `output.json` stay in the unified JSON inspector
- Trajectory overlay nodes appear under the raw `trajectory` branch
- Raw JSON nodes and mapped overlay nodes are annotatable
- Pure summary nodes are not annotatable unless mapped to a raw path

#### `trajectory`

Bare trajectory files may use the specialized trajectory view:

```json
{
  "kind": "trajectory",
  "name": "trajectory.json",
  "path": "trajectory.json",
  "header": "Trajectory | ...",
  "metadata_lines": ["model: ..."],
  "final_output": {
    "kind": "syntax",
    "language": "text",
    "line_numbers": false,
    "value": "Done",
    "html": "<div class=\"syntax-block\">...</div>"
  },
  "initial_step_id": "step-0",
  "steps": [
    {
      "id": "step-0",
      "title": "Step 1",
      "path": "$.steps[0]",
      "summary": "4 items",
      "items": []
    }
  ]
}
```

Step / item fields:

- step: `id`, `title`, `path`, `summary`, `items`
- item: `kind`, `title`, `annotation_path`, `annotation`, render payloads, event or tool metadata

#### Error and fallback rules

- malformed JSON falls back to `text`
- oversized files return `too_large`
- unknown syntax lexer falls back to `text`
- missing files return `error`

### `GET /api/annotations`

```json
{
  "version": 1,
  "files": {
    "data/output.json": {
      "annotations": {
        "$.trajectory.steps[0].output[3]": [
          {
            "id": "ann-json",
            "created_at": "2026-04-21T14:00:00.000000Z",
            "updated_at": "2026-04-21T14:05:00.000000Z",
            "tags": ["important"],
            "note": "check this"
          }
        ]
      }
    },
    "docs/spec.md": {
      "annotations": {
        "@file": [
          {
            "id": "ann-file",
            "created_at": "2026-04-21T14:10:00.000000Z",
            "updated_at": "2026-04-21T14:15:00.000000Z",
            "tags": ["follow-up"],
            "note": "Review the whole file."
          }
        ]
      }
    }
  }
}
```

The reserved `@file` key stores file-level annotations for non-JSON previews.

### `POST /api/annotations`

Request:

```json
{
  "file": "data/output.json",
  "path": "$.trajectory.steps[0].output[3]",
  "tags": ["important"],
  "note": "check this"
}
```

File-level example:

```json
{
  "file": "docs/spec.md",
  "path": "@file",
  "tags": ["follow-up"],
  "note": "Review the whole file."
}
```

Response:

```json
{ "ok": true }
```

### `DELETE /api/annotations`

Request:

```json
{
  "file": "data/output.json",
  "path": "$.trajectory.steps[0].output[3]"
}
```

Response:

```json
{ "ok": true }
```

Failure rules:

- missing file → error
- path outside browse root → forbidden
- malformed request body → error

### `GET /api/annotation-version`

```json
{
  "annotation_version": "1761087327123456789:214"
}
```

### `GET /api/triage`

```json
{
  "annotation_version": "1761087327123456789:214",
  "items": [
    {
      "annotation_id": "ann-file",
      "file_path": "docs/spec.md",
      "target_kind": "file",
      "target_label": "File",
      "target_path": null,
      "preview_kind": "markdown",
      "tags": ["follow-up"],
      "note_preview": "Review the whole file.",
      "note_full": "Review the whole file.",
      "created_at": "2026-04-21T14:10:00.000000Z",
      "updated_at": "2026-04-21T14:15:00.000000Z"
    }
  ]
}
```

---

## Preview Types

### Code Files

- Syntax-highlighted source via Python-generated `syntax` HTML
- Full-file source shows line numbers
- Supported languages: Python, JSON, YAML, TOML, JavaScript, TypeScript, HTML,
  CSS, Bash, Rust, Go, plus text fallback for other known extensions

### Markdown

- Rendered headings, lists, bold, inline code, and fenced code blocks
- Body uses system sans-serif
- Fenced code blocks use the same syntax theme as normal code blocks

### Notebook Preview

Notebook rendering is part of the core spec, not future work.

- `.ipynb` files are flattened like the TUI
- Summary header shows notebook metadata
- Markdown cells render as markdown
- Code cells render with syntax highlighting
- Outputs appear inline beneath the cell that produced them
- Invalid notebook JSON falls back to syntax-highlighted text

### JSON Inspector

Layout:

- 38 / 62 split
- Left: collapsible tree
- Right: structured detail view for the selected node

Behavior:

- branch labels may include object / array counts
- structured detail prefers human-facing sections over raw JSON dumps
- wrapper keys such as `output`, `result`, `arguments`, `content`, `text` may be promoted
- annotated nodes show a marker in the tree

### Trajectory Viewer

Layout:

- 38 / 62 split
- Left: metadata + step list
- Right: selected step detail

Behavior:

- bare trajectories may use this specialized view
- wrapped trajectories stay in the JSON inspector
- step detail shows tool calls, tool results, events, and annotation affordances

---

## Interaction Rules

### File Tree

- clicking a directory row toggles it
- clicking a file row opens it in the active pane
- disclosure triangles remain visible but are not required
- selected file uses accent border, accent text, and highlighted background
- file size renders right-aligned in muted text

### JSON Tree

- clicking a leaf row selects it
- clicking a branch row selects it and toggles expand / collapse
- annotated nodes show an in-tree marker
- expansion, selection, and scroll state are preserved per open file / pane where possible

### Preview Smoothness

- switching to a different file may rerender the pane
- local interactions inside the current preview should update only the affected subtree where practical
- annotation save / delete may refresh preview data, but should preserve the current context when possible

### Pane Semantics

- all open-file actions target the active pane
- clicking a pane makes it active
- command palette open also targets the active pane
- split / close / cycle behavior follows the existing TUI rules

### Command Palette

- Trigger: `⌘K`
- Searches the already-loaded `/api/tree` payload client-side
- Fuzzy filename filtering
- Enter opens the first match in the active pane
- Escape closes
- No new backend search endpoint is required for the initial implementation

### Annotation System

- Available on annotatable JSON nodes and mapped trajectory overlay nodes
- Triggered by an explicit annotation affordance on the selected item
- Modal contains:
  - comma-separated tags input
  - note textarea
- Stored format matches `.skim/review.json` used by the TUI

### Theme Toggle

- Both dark and light themes are part of the full target
- Theme tokens apply to shell surfaces and syntax colors
- Dark remains the default

### Status Bar

- Shows pane count
- Shows the active file path
- Shows shortcut hints
- Always visible on desktop
- May collapse or stack on small screens, but remains present

---

## Acceptance Criteria

### API

- `/api/preview` returns typed payloads for text, markdown, notebook, CSV, JSON
  inspector, trajectory, large-file, and error cases
- wrapped trajectory JSON stays in the inspector
- bare trajectory files may use the trajectory view
- annotation persistence matches `.skim/review.json`

### Interaction

- directory rows toggle without needing the triangle
- JSON branch rows toggle and select
- active-pane targeting is respected for file opens and command-palette opens
- split / close / cycle behavior matches the TUI shell

### Rendering

- syntax HTML is present for code and JSON blocks
- markdown, notebook cells, JSON detail sections, and trajectory items render from typed payloads
- both dark and light themes define syntax-token styling

### State

- expansion, selection, and scroll state persist across local interactions
- annotation refresh does not unnecessarily destroy the current preview context

---

## Future Considerations

- drag-to-resize for sidebar and pane dividers
- vim-style web keybindings (`h/j/k/l`)
- search within files
- live reload via filesystem watch
- optional agentic analysis surface layered on top of local artifact rendering
