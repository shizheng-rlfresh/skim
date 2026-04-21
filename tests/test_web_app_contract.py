"""Small browser-contract tests for the vanilla web client."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parents[1] / "src" / "skim" / "web" / "app.js"


def run_app_js(script: str) -> dict:
    """Evaluate app.js in Node with a tiny DOM stub and return JSON output."""
    if shutil.which("node") is None:
        pytest.skip("node is required for browser-contract tests")
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


def test_run_app_js_skips_cleanly_when_node_is_unavailable(monkeypatch):
    """Browser-contract tests should skip instead of failing when Node is absent."""
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with pytest.raises(pytest.skip.Exception, match="node is required"):
        run_app_js("console.log(JSON.stringify({ ok: true }));")


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


def test_render_detail_block_uses_syntax_markup_for_json_fallback():
    """Raw JSON detail blocks should reuse syntax-style markup instead of plain pre blocks."""
    result = run_app_js(
        """
const html = ctx.renderDetailBlock({
  kind: "json",
  value: { plan: { step: 1, ok: true } },
});
console.log(JSON.stringify({
  hasSyntax: html.includes('syntax-block'),
  hasJsonPre: html.includes('json-block'),
  hasJsonKey: html.includes('json-fallback-key'),
}));
"""
    )

    assert result == {"hasSyntax": True, "hasJsonPre": False, "hasJsonKey": True}


def test_render_palette_row_uses_explicit_name_and_path_classes():
    """Palette rows should expose separate high-contrast name and muted path hooks."""
    result = run_app_js(
        """
const html = ctx.renderPaletteRow(
  { name: "server.py", path: "src/skim/server.py" },
  0,
  true,
);
console.log(JSON.stringify({
  hasNameClass: html.includes('palette-name'),
  hasPathClass: html.includes('palette-path'),
  hasSelectedClass: html.includes('palette-row selected'),
}));
"""
    )

    assert result == {
        "hasNameClass": True,
        "hasPathClass": True,
        "hasSelectedClass": True,
    }


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


def test_render_tree_node_uses_rich_file_icon_mapping():
    """File-tree rows should emit mapped file-kind metadata and icon markup."""
    result = run_app_js(
        """
vm.runInContext(`
state.panes = [createPaneState("pane-1")];
state.activePaneId = "pane-1";
state.panes[0].path = "src/main.py";
`, ctx);
const html = ctx.renderTreeNode({
  name: "main.py",
  type: "file",
  ext: ".py",
  path: "src/main.py",
  size: "1.2 KB",
}, 0);
console.log(JSON.stringify({
  hasKind: html.includes('data-file-kind="python"'),
  hasIcon: html.includes('file-icon'),
  hasToken: html.includes('Py'),
}));
"""
    )

    assert result == {"hasKind": True, "hasIcon": True, "hasToken": True}


def test_render_tree_node_falls_back_to_generic_icon_for_unknown_file():
    """Unknown extensions should still get a generic file icon/category."""
    result = run_app_js(
        """
const html = ctx.renderTreeNode({
  name: "artifact.foo",
  type: "file",
  ext: ".foo",
  path: "artifact.foo",
  size: "3 B",
}, 0);
console.log(JSON.stringify({
  hasGenericKind: html.includes('data-file-kind="generic"'),
  hasGenericToken: html.includes('FI'),
}));
"""
    )

    assert result == {"hasGenericKind": True, "hasGenericToken": True}


def test_render_pane_shell_uses_human_readable_preview_labels():
    """Pane headers should show user-facing type labels instead of raw preview kinds."""
    result = run_app_js(
        """
const pythonHtml = ctx.renderPaneShell({
  id: "pane-1",
  path: "src/skim/server.py",
  preview: {
    kind: "text",
    name: "server.py",
    path: "src/skim/server.py",
    language: "python",
  },
});
const jsonHtml = ctx.renderPaneShell({
  id: "pane-2",
  path: "broken.json",
  preview: {
    kind: "text",
    name: "broken.json",
    path: "broken.json",
    language: "json",
  },
});
const inspectorHtml = ctx.renderPaneShell({
  id: "pane-3",
  path: "output.json",
  preview: {
    kind: "json_inspector",
    name: "output.json",
    path: "output.json",
  },
});
console.log(JSON.stringify({
  pythonLabel: pythonHtml.includes('<span class="pane-kind">Python</span>'),
  jsonLabel: jsonHtml.includes('<span class="pane-kind">JSON</span>'),
  inspectorLabel: inspectorHtml.includes('<span class="pane-kind">JSON</span>'),
  rawTextMissing: !pythonHtml.includes('<span class="pane-kind">text</span>'),
}));
"""
    )

    assert result == {
        "pythonLabel": True,
        "jsonLabel": True,
        "inspectorLabel": True,
        "rawTextMissing": True,
    }


def test_render_json_node_uses_structured_icon_key_and_value_segments():
    """JSON tree rows should render typed icons and separate key/value spans."""
    result = run_app_js(
        """
const html = ctx.renderJsonNode({
  id: "node-1",
  path: "$.name",
  display_key: "name",
  display_value: '"skim"',
  value_type: "string",
  node_class: "string",
  synthetic: false,
  label: "name",
  style: "string",
  annotation: null,
  children: [],
}, 0, {
  expandedJson: new Set(),
  selectedJsonNodeId: "node-1",
});
console.log(JSON.stringify({
  hasNodeClass: html.includes('data-node-class="string"'),
  hasIcon: html.includes('json-node-icon'),
  hasKey: html.includes('json-node-key'),
  hasValue: html.includes('json-node-value'),
  hasValueType: html.includes('json-string'),
}));
"""
    )

    assert result == {
        "hasNodeClass": True,
        "hasIcon": True,
        "hasKey": True,
        "hasValue": True,
        "hasValueType": True,
    }


def test_render_json_node_uses_overlay_node_class_for_synthetic_nodes():
    """Synthetic overlay nodes should render their override class instead of raw value type."""
    result = run_app_js(
        """
const html = ctx.renderJsonNode({
  id: "node-1",
  path: "$.trajectory.metadata",
  display_key: "Metadata",
  display_value: null,
  value_type: "object",
  node_class: "trajectory_metadata",
  synthetic: true,
  label: "Metadata",
  style: "metadata",
  annotation: null,
  children: [{ id: "child-1", path: "$.trajectory.metadata.model", children: [] }],
}, 0, {
  expandedJson: new Set(["$.trajectory.metadata"]),
  selectedJsonNodeId: "node-1",
});
console.log(JSON.stringify({
  hasOverlayClass: html.includes('data-node-class="trajectory_metadata"'),
  hasOverlayToken: html.includes('MD'),
}));
"""
    )

    assert result == {"hasOverlayClass": True, "hasOverlayToken": True}


def test_render_annotate_button_uses_distinct_default_and_annotated_states():
    """Annotate buttons should stand out and switch state after an annotation exists."""
    result = run_app_js(
        """
const plain = ctx.renderAnnotateButton("$.task", null);
const annotated = ctx.renderAnnotateButton("$.task", { tags: ["important"], note: "Keep" });
console.log(JSON.stringify({
  plainHasClass: plain.includes('annotate-button') && plain.includes('annotate-button-pending'),
  plainLabel: plain.includes(">Annotate<"),
  annotatedHasClass:
    annotated.includes('annotate-button') &&
    annotated.includes('annotate-button-active'),
  annotatedLabel: annotated.includes(">Edit annotation<"),
}));
"""
    )

    assert result == {
        "plainHasClass": True,
        "plainLabel": True,
        "annotatedHasClass": True,
        "annotatedLabel": True,
    }


def test_render_annotation_panel_lists_multiple_entries_and_defaults_to_newest():
    """The annotation panel should show multiple entries newest-first for one node."""
    result = run_app_js(
        """
const html = ctx.renderAnnotationPanel(
  [
    {
      id: "newer",
      created_at: "2026-04-20T11:00:00Z",
      updated_at: "2026-04-20T11:30:00Z",
      tags: ["bug"],
      note: "newer note",
    },
    {
      id: "older",
      created_at: "2026-04-20T10:00:00Z",
      updated_at: "2026-04-20T10:00:00Z",
      tags: ["evidence"],
      note: "older note",
    },
  ],
  true,
  "newer",
);
console.log(JSON.stringify({
  hasList: html.includes('annotation-list'),
  hasCount: html.includes('2 annotations'),
  newerBeforeOlder: html.indexOf('newer note') < html.indexOf('older note'),
  hasSelectedClass: html.includes('annotation-entry selected'),
}));
"""
    )

    assert result == {
        "hasList": True,
        "hasCount": True,
        "newerBeforeOlder": True,
        "hasSelectedClass": True,
    }


def test_render_json_node_marks_annotated_rows_more_obviously():
    """Annotated JSON rows should emit a dedicated row state and stronger marker glyph."""
    result = run_app_js(
        """
const html = ctx.renderJsonNode({
  id: "node-1",
  path: "$.name",
  display_key: "name",
  display_value: '"skim"',
  value_type: "string",
  node_class: "string",
  synthetic: false,
  label: "name",
  style: "string",
  annotation: { tags: ["important"], note: "watch this" },
  children: [],
}, 0, {
  expandedJson: new Set(),
  selectedJsonNodeId: "node-1",
});
console.log(JSON.stringify({
  hasAnnotatedRow: html.includes('json-tree-row-annotated'),
  hasMarker: html.includes('annotation-glyph'),
}));
"""
    )

    assert result == {"hasAnnotatedRow": True, "hasMarker": True}


def test_render_json_and_trajectory_previews_include_split_resizers():
    """Split views should include draggable resizer gutters for both preview kinds."""
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
    label: "task",
    display_key: "task",
    display_value: "{1}",
    value_type: "object",
    node_class: "object",
    style: "object",
    type_name: "object",
    annotation: null,
    annotatable: true,
    annotation_path: "$.task",
    detail: { kind: "detail", blocks: [] },
    children: [],
  }],
  initial_node_id: "node-1",
};
state.panes[0].selectedJsonNodeId = "node-1";
state.panes[0].jsonSplitRatio = 42;
state.panes[0].trajectorySplitRatio = 36;
`, ctx);
const jsonHtml = ctx.renderJsonInspector(vm.runInContext('state.panes[0]', ctx));
const trajectoryHtml = ctx.renderTrajectoryPreview({
  id: "pane-1",
  preview: {
    header: "traj",
    metadata_lines: [],
    final_output: { kind: "text", value: "done" },
    steps: [{ id: "step-1", title: "Step 1", summary: "summary", items: [] }],
    initial_step_id: "step-1",
  },
  selectedStepId: "step-1",
  trajectorySplitRatio: 36,
});
console.log(JSON.stringify({
  hasJsonResizer: jsonHtml.includes('data-resize-split="json"'),
  hasTrajectoryResizer: trajectoryHtml.includes('data-resize-split="trajectory"'),
}));
"""
    )

    assert result == {"hasJsonResizer": True, "hasTrajectoryResizer": True}


def test_json_and_trajectory_split_ratios_are_pane_local():
    """Each pane should render its own split ratio instead of sharing one global value."""
    result = run_app_js(
        """
vm.runInContext(`
state.panes = [createPaneState("pane-1"), createPaneState("pane-2")];
state.panes[0].preview = {
  kind: "json_inspector",
  tree: [{
    id: "node-1",
    path: "$.task",
    raw_path: ["task"],
    label: "task",
    display_key: "task",
    display_value: "{1}",
    value_type: "object",
    node_class: "object",
    style: "object",
    type_name: "object",
    annotation: null,
    annotatable: true,
    annotation_path: "$.task",
    detail: { kind: "detail", blocks: [] },
    children: [],
  }],
  initial_node_id: "node-1",
};
state.panes[1].preview = JSON.parse(JSON.stringify(state.panes[0].preview));
state.panes[0].selectedJsonNodeId = "node-1";
state.panes[1].selectedJsonNodeId = "node-1";
state.panes[0].jsonSplitRatio = 31;
state.panes[1].jsonSplitRatio = 64;
state.panes[0].trajectorySplitRatio = 28;
state.panes[1].trajectorySplitRatio = 59;
`, ctx);
const jsonA = ctx.renderJsonInspector(vm.runInContext('state.panes[0]', ctx));
const jsonB = ctx.renderJsonInspector(vm.runInContext('state.panes[1]', ctx));
const trajectoryA = ctx.renderTrajectoryPreview({
  id: "pane-1",
  preview: {
    header: "traj",
    metadata_lines: [],
    final_output: { kind: "text", value: "done" },
    steps: [{ id: "step-1", title: "Step 1", summary: "summary", items: [] }],
    initial_step_id: "step-1",
  },
  selectedStepId: "step-1",
  trajectorySplitRatio: 28,
});
const trajectoryB = ctx.renderTrajectoryPreview({
  id: "pane-2",
  preview: {
    header: "traj",
    metadata_lines: [],
    final_output: { kind: "text", value: "done" },
    steps: [{ id: "step-1", title: "Step 1", summary: "summary", items: [] }],
    initial_step_id: "step-1",
  },
  selectedStepId: "step-1",
  trajectorySplitRatio: 59,
});
console.log(JSON.stringify({
  jsonAUsesOwnRatio: jsonA.includes('grid-template-columns:minmax(0, 31fr) 12px minmax(0, 69fr)'),
  jsonBUsesOwnRatio: jsonB.includes('grid-template-columns:minmax(0, 64fr) 12px minmax(0, 36fr)'),
  trajectoryAUsesOwnRatio:
    trajectoryA.includes('grid-template-columns:minmax(0, 28fr) 12px minmax(0, 72fr)'),
  trajectoryBUsesOwnRatio:
    trajectoryB.includes('grid-template-columns:minmax(0, 59fr) 12px minmax(0, 41fr)'),
}));
"""
    )

    assert result == {
        "jsonAUsesOwnRatio": True,
        "jsonBUsesOwnRatio": True,
        "trajectoryAUsesOwnRatio": True,
        "trajectoryBUsesOwnRatio": True,
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


def test_render_tree_node_makes_directory_rows_keyboard_focusable():
    """Directory rows should expose keyboard semantics for toggling."""
    result = run_app_js(
        """
const html = ctx.renderTreeNode({
  name: "src",
  type: "dir",
  path: "src",
  children: [],
}, 0);
console.log(JSON.stringify({
  hasRole: html.includes('role="button"'),
  hasTabIndex: html.includes('tabindex="0"'),
  hasExpanded: html.includes('aria-expanded="false"'),
}));
"""
    )

    assert result == {"hasRole": True, "hasTabIndex": True, "hasExpanded": True}


def test_directory_row_keyboard_toggle_supports_enter_and_space():
    """Pressing Enter or Space on a directory row should toggle that directory."""
    result = run_app_js(
        """
vm.runInContext('state.expandedDirs = new Set(["."]);', ctx);
let prevented = 0;
let treeRenders = 0;
ctx.renderTree = () => { treeRenders += 1; };
ctx.onTreeKeyDown({
  key: "Enter",
  preventDefault() { prevented += 1; },
  target: {
    closest(selector) {
      if (selector === "[data-dir-path]") return { dataset: { dirPath: "src" } };
      return null;
    },
  },
});
ctx.onTreeKeyDown({
  key: " ",
  preventDefault() { prevented += 1; },
  target: {
    closest(selector) {
      if (selector === "[data-dir-path]") return { dataset: { dirPath: "src" } };
      return null;
    },
  },
});
console.log(JSON.stringify({
  expanded: vm.runInContext('state.expandedDirs.has("src")', ctx),
  prevented,
  treeRenders,
}));
"""
    )

    assert result == {"expanded": False, "prevented": 2, "treeRenders": 2}


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


def test_sidebar_width_helpers_clamp_store_and_restore_preference():
    """Sidebar width should clamp to bounds and persist in local storage."""
    result = run_app_js(
        """
vm.runInContext('state.sidebarWidth = 220; state.sidebarVisible = true;', ctx);
ctx.setSidebarWidth(50, { viewportWidth: 1200 });
const clampedMin = vm.runInContext('state.sidebarWidth', ctx);
ctx.setSidebarWidth(900, { viewportWidth: 1200 });
const clampedMax = vm.runInContext('state.sidebarWidth', ctx);
ctx.localStorage.setItem("skim-sidebar-width", "366");
console.log(JSON.stringify({
  clampedMin,
  clampedMax,
  restored: ctx.loadStoredSidebarWidth(),
}));
"""
    )

    assert result == {"clampedMin": 180, "clampedMax": 540, "restored": 366}


def test_pane_layout_and_split_ratio_helpers_persist_resizable_tracks():
    """Pane-grid tracks and split ratios should persist and restore from local storage."""
    result = run_app_js(
        """
ctx.setStoredPaneLayout("row-3", { cols: [2, 1, 1] });
ctx.setStoredPaneLayout("grid-2x3", {
  topCols: [3, 1, 1],
  bottomCols: [1, 2, 1],
  rows: [3, 1],
});
ctx.setStoredSplitRatio("json", 44);
ctx.setStoredSplitRatio("trajectory", 35);
console.log(JSON.stringify({
  rowLayout: ctx.loadStoredPaneLayout("row-3", { cols: [1, 1, 1] }),
  gridLayout: ctx.loadStoredPaneLayout("grid-2x3", {
    topCols: [1, 1, 1],
    bottomCols: [1, 1, 1],
    rows: [1, 1],
  }),
  jsonRatio: ctx.loadStoredSplitRatio("json", 38),
  trajectoryRatio: ctx.loadStoredSplitRatio("trajectory", 38),
  trackTemplate: ctx.trackTemplate([2, 1, 1]),
}));
"""
    )

    assert result == {
        "rowLayout": {"cols": [2, 1, 1]},
        "gridLayout": {"topCols": [3, 1, 1], "bottomCols": [1, 2, 1], "rows": [3, 1]},
        "jsonRatio": 44,
        "trajectoryRatio": 35,
        "trackTemplate": "minmax(0, 2fr) 12px minmax(0, 1fr) 12px minmax(0, 1fr)",
    }


def test_grid_2x3_row_column_updates_are_independent():
    """Top and bottom 2x3 row column weights should resize independently."""
    result = run_app_js(
        """
vm.runInContext(`
state.panes = [
  createPaneState("pane-1"),
  createPaneState("pane-2"),
  createPaneState("pane-3"),
  createPaneState("pane-4"),
  createPaneState("pane-5"),
  createPaneState("pane-6"),
];
state.gridTopCols = [3, 1, 1];
state.gridBottomCols = [1, 2, 1];
state.gridRows = [2, 1];
`, ctx);
ctx.setRowWeightsForLayout("grid-2x3", "grid-2x3-top", [2, 2, 1]);
const afterTopResize = {
  top: ctx.rowWeightsForLayout("grid-2x3", "grid-2x3-top"),
  bottom: ctx.rowWeightsForLayout("grid-2x3", "grid-2x3-bottom"),
  layout: ctx.currentPaneLayout("grid-2x3"),
};
ctx.setRowWeightsForLayout("grid-2x3", "grid-2x3-bottom", [1, 1, 2]);
console.log(JSON.stringify({
  afterTopResize,
  afterBottomResize: {
    top: ctx.rowWeightsForLayout("grid-2x3", "grid-2x3-top"),
    bottom: ctx.rowWeightsForLayout("grid-2x3", "grid-2x3-bottom"),
    layout: ctx.currentPaneLayout("grid-2x3"),
  },
}));
"""
    )

    assert result == {
        "afterTopResize": {
            "top": [2, 2, 1],
            "bottom": [1, 2, 1],
            "layout": {"topCols": [2, 2, 1], "bottomCols": [1, 2, 1], "rows": [2, 1]},
        },
        "afterBottomResize": {
            "top": [2, 2, 1],
            "bottom": [1, 1, 2],
            "layout": {"topCols": [2, 2, 1], "bottomCols": [1, 1, 2], "rows": [2, 1]},
        },
    }


def test_grid_2x3_bottom_row_keeps_hidden_track_when_sixth_pane_is_added():
    """A bottom-row resize should preserve the latent third track for a later sixth pane."""
    result = run_app_js(
        """
vm.runInContext(`
state.panes = [
  createPaneState("pane-1"),
  createPaneState("pane-2"),
  createPaneState("pane-3"),
  createPaneState("pane-4"),
  createPaneState("pane-5"),
];
state.activePaneId = "pane-5";
state.nextPaneNumber = 6;
state.gridTopCols = [1, 1, 1];
state.gridBottomCols = [1, 2, 3];
state.gridRows = [1, 1];
`, ctx);
ctx.setRowWeightsForLayout("grid-2x3", "grid-2x3-bottom", [4, 1]);
ctx.splitActivePane();
console.log(JSON.stringify({
  bottom: ctx.rowWeightsForLayout("grid-2x3", "grid-2x3-bottom"),
  layout: ctx.currentPaneLayout("grid-2x3"),
}));
"""
    )

    assert result == {
        "bottom": [4, 1, 3],
        "layout": {"topCols": [1, 1, 1], "bottomCols": [4, 1, 3], "rows": [1, 1]},
    }


def test_sidebar_resize_is_disabled_when_sidebar_is_hidden():
    """The resize handle should be inactive when the sidebar is hidden."""
    result = run_app_js(
        """
vm.runInContext('state.sidebarVisible = false;', ctx);
console.log(JSON.stringify({
  canResize: ctx.canResizeSidebar(),
}));
"""
    )

    assert result == {"canResize": False}


def test_non_sidebar_resize_helpers_disable_in_stacked_mode():
    """Pane and split resizing should be disabled in stacked mobile layouts."""
    result = run_app_js(
        """
console.log(JSON.stringify({
  stacked: ctx.isStackedLayout(800),
  canResizePanes: ctx.canResizePaneLayout(800),
  canResizeSplits: ctx.canResizeSplitViews(800),
}));
"""
    )

    assert result == {"stacked": True, "canResizePanes": False, "canResizeSplits": False}
