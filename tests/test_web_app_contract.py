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
state.preview = {
  kind: "json_inspector",
  tree: [{
    id: "node-1",
    path: "$.task",
    raw_path: ["task"],
    children: [{ id: "node-2", path: "$.task.name", raw_path: ["task", "name"], children: [] }],
  }],
};
state.expandedJson = new Set();
state.selectedJsonNodeId = null;
state.selectedJsonPath = null;
`, ctx);
ctx.renderPreview = () => {};
await ctx.onPreviewClick({
  target: {
    closest(selector) {
      if (selector === "[data-json-node]") return { dataset: { jsonNode: "node-1" } };
      if (selector === "[data-toggle-json]") return null;
      return null;
    },
  },
});
console.log(JSON.stringify({
  expanded: vm.runInContext('state.expandedJson.has("$.task")', ctx),
  selectedJsonNodeId: vm.runInContext('state.selectedJsonNodeId', ctx),
  selectedJsonPath: vm.runInContext('state.selectedJsonPath', ctx),
}));
"""
    )

    assert result == {
        "expanded": True,
        "selectedJsonNodeId": "node-1",
        "selectedJsonPath": "$.task",
    }
