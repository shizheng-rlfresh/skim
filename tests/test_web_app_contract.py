"""Small browser-contract tests for the vanilla web client."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

APP_JS = Path(__file__).resolve().parents[1] / "src" / "skim" / "web" / "app.js"


def run_app_js(script: str) -> dict:
    """Evaluate app.js in Node with a tiny DOM stub and return JSON output."""
    harness = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({json.dumps(str(APP_JS))}, "utf8");
const context = {{
  console,
  Set,
  Map,
  vm,
  window: {{}},
  document: {{
    addEventListener() {{}},
    getElementById() {{ return null; }},
  }},
  localStorage: {{
    _store: {{}},
    getItem(key) {{ return this._store[key] ?? null; }},
    setItem(key, value) {{ this._store[key] = String(value); }},
    removeItem(key) {{ delete this._store[key]; }},
  }},
  fetch: async () => ({{ ok: true, json: async () => ({{}}) }}),
}};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(source, context);
const ctx = context;

(async () => {{
{script}
}})().catch((error) => {{
  console.error(error.stack || String(error));
  process.exit(1);
}});
"""
    result = subprocess.run(
        ["node", "-e", harness],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_render_text_preview_uses_python_highlighted_html():
    """Text previews should mount syntax HTML instead of plain escaped pre blocks."""
    result = run_app_js(
        """
const html = ctx.renderTextPreview({
  path: "example.py",
  language: "python",
  render: {
    kind: "syntax",
    html: '<div class="syntax-block"><span class="tok-k">def</span></div>',
    value: "def hi():\\n    return 1\\n",
  },
});
console.log(JSON.stringify({
  hasSyntax: html.includes('syntax-block'),
  escapedSyntax: html.includes('&lt;div class=&quot;syntax-block&quot;&gt;'),
}));
"""
    )

    assert result == {"hasSyntax": True, "escapedSyntax": False}


def test_render_detail_block_supports_syntax_payloads():
    """Structured detail blocks should render syntax HTML fragments directly."""
    result = run_app_js(
        """
const html = ctx.renderDetailBlock({
  kind: "syntax",
  html: '<div class="syntax-block"><span class="tok-p">{{}}</span></div>',
  value: "{}",
});
console.log(JSON.stringify({
  hasSyntax: html.includes('syntax-block'),
  hasTextFallback: html.includes('text-block'),
}));
"""
    )

    assert result == {"hasSyntax": True, "hasTextFallback": False}


def test_render_notebook_preview_renders_flat_cells_and_outputs():
    """Notebook previews should render cell blocks and inline outputs."""
    result = run_app_js(
        """
const html = ctx.renderNotebookPreview({
  path: "example.ipynb",
  language: "python",
  summary: { cell_count: 2, nbformat: 4, nbformat_minor: 5 },
  cells: [
    {
      title: "Markdown Cell 1",
      render: { kind: "markdown", value: "# Title\\n\\nBody" },
      outputs: [],
    },
    {
      title: "Code Cell 2",
      render: {
        kind: "syntax",
        html: '<div class="syntax-block"><span class="tok-k">print</span></div>',
        value: "print(1)",
      },
      outputs: [
        {
          title: "Output 2.1",
          render: { kind: "text", value: "1\\n" },
        },
      ],
    },
  ],
});
console.log(JSON.stringify({
  hasSummary: html.includes("Notebook Preview"),
  hasMarkdownCell: html.includes("Markdown Cell 1"),
  hasCodeSyntax: html.includes("syntax-block"),
  hasOutput: html.includes("Output 2.1"),
}));
"""
    )

    assert result == {
        "hasSummary": True,
        "hasMarkdownCell": True,
        "hasCodeSyntax": True,
        "hasOutput": True,
    }


def test_directory_row_click_toggles_without_triangle_target():
    """Clicking the directory row itself should expand or collapse that directory."""
    result = run_app_js(
        """
vm.runInContext('state.expandedDirs = new Set(["."]);', ctx);
let treeRenders = 0;
ctx.renderTree = () => { treeRenders += 1; };
await ctx.onTreeClick({
  target: {
    closest(selector) {
      if (selector === "[data-toggle-dir]") return null;
      if (selector === "[data-dir-path]") return { dataset: { dirPath: "src" } };
      if (selector === "[data-file-path]") return null;
      return null;
    },
  },
});
console.log(JSON.stringify({
  expanded: vm.runInContext('state.expandedDirs.has("src")', ctx),
  treeRenders,
}));
"""
    )

    assert result == {"expanded": True, "treeRenders": 1}


def test_json_branch_row_click_toggles_and_selects_without_triangle_target():
    """Clicking a JSON branch row should expand it and keep it selected."""
    result = run_app_js(
        """
vm.runInContext(`
state.panes = [createPaneState("pane-1")];
state.activePaneId = "pane-1";
state.panes[0].preview = {
  kind: "json_inspector",
  tree: [{
    id: "node-1",
    path: "$.task",
    raw_path: ["task"],
    children: [{ id: "node-2", path: "$.task.name", raw_path: ["task", "name"], children: [] }],
  }],
};
state.panes[0].expandedJson = new Set();
state.panes[0].selectedJsonNodeId = null;
state.panes[0].selectedJsonPath = null;
`, ctx);
ctx.renderWorkspace = () => {};
await ctx.onPreviewClick({
  target: {
    closest(selector) {
      if (selector === "[data-json-node]") return { dataset: { jsonNode: "node-1" } };
      if (selector === "[data-toggle-json]") return null;
      if (selector === "[data-pane-id]") return { dataset: { paneId: "pane-1" } };
      return null;
    },
  },
}, "pane-1");
console.log(JSON.stringify({
  expanded: vm.runInContext('state.panes[0].expandedJson.has("$.task")', ctx),
  selectedJsonNodeId: vm.runInContext('state.panes[0].selectedJsonNodeId', ctx),
  selectedJsonPath: vm.runInContext('state.panes[0].selectedJsonPath', ctx),
}));
"""
    )

    assert result == {
        "expanded": True,
        "selectedJsonNodeId": "node-1",
        "selectedJsonPath": "$.task",
    }


def test_split_active_pane_adds_new_active_pane_up_to_limit():
    """Splitting should create a new active pane until the six-pane cap."""
    result = run_app_js(
        """
vm.runInContext('state.panes = [createPaneState("pane-1")]; state.activePaneId = "pane-1";', ctx);
for (let index = 0; index < 7; index += 1) {
  ctx.splitActivePane();
}
console.log(JSON.stringify({
  paneCount: vm.runInContext('state.panes.length', ctx),
  activePaneId: vm.runInContext('state.activePaneId', ctx),
  paneIds: vm.runInContext('state.panes.map((pane) => pane.id)', ctx),
}));
"""
    )

    assert result == {
        "paneCount": 6,
        "activePaneId": "pane-6",
        "paneIds": ["pane-1", "pane-2", "pane-3", "pane-4", "pane-5", "pane-6"],
    }


def test_tree_click_opens_file_in_the_active_pane():
    """File-tree opens should target the active pane rather than a global preview."""
    result = run_app_js(
        """
let capture = null;
ctx.loadPreviewForPane = async (path, paneId) => {
  capture = { path, paneId };
};
vm.runInContext(`
state.panes = [createPaneState("pane-1"), createPaneState("pane-2")];
state.activePaneId = "pane-2";
`, ctx);
await ctx.onTreeClick({
  target: {
    closest(selector) {
      if (selector === "[data-toggle-dir]") return null;
      if (selector === "[data-dir-path]") return null;
      if (selector === "[data-file-path]") return { dataset: { filePath: "src/skim/server.py" } };
      return null;
    },
  },
});
console.log(JSON.stringify(capture));
"""
    )

    assert result == {"path": "src/skim/server.py", "paneId": "pane-2"}


def test_command_palette_fuzzy_match_opens_selection_in_active_pane():
    """Palette selection should use the active pane and client-side tree matches."""
    result = run_app_js(
        """
let capture = null;
ctx.loadPreviewForPane = async (path, paneId) => {
  capture = { path, paneId };
};
vm.runInContext(`
state.tree = {
  children: [
    { name: "server.py", type: "file", path: "src/skim/server.py" },
    { name: "styles.css", type: "file", path: "src/skim/web/styles.css" },
  ],
};
state.panes = [createPaneState("pane-1"), createPaneState("pane-2")];
state.activePaneId = "pane-2";
state.palette = { open: true, query: "srv", selectedIndex: 0, matches: [] };
`, ctx);
ctx.updatePaletteMatches();
await ctx.openPaletteSelection();
console.log(JSON.stringify({
  capture,
  matchPaths: vm.runInContext('state.palette.matches.map((entry) => entry.path)', ctx),
  paletteOpen: vm.runInContext('state.palette.open', ctx),
}));
"""
    )

    assert result == {
        "capture": {"path": "src/skim/server.py", "paneId": "pane-2"},
        "matchPaths": ["src/skim/server.py"],
        "paletteOpen": False,
    }


def test_theme_toggle_persists_preference():
    """Theme changes should update state and persist to localStorage."""
    result = run_app_js(
        """
vm.runInContext('state.theme = "dark";', ctx);
ctx.toggleTheme();
console.log(JSON.stringify({
  theme: vm.runInContext('state.theme', ctx),
  storedTheme: ctx.localStorage.getItem("skim-theme"),
}));
"""
    )

    assert result == {"theme": "light", "storedTheme": "light"}
