const MAX_PANES = 6;

const elements = {};

const state = {
  tree: null,
  browseRoot: "",
  expandedDirs: new Set(["."]),
  panes: [createPaneState("pane-1")],
  activePaneId: "pane-1",
  nextPaneNumber: 2,
  sidebarVisible: true,
  theme: loadStoredTheme(),
  palette: {
    open: false,
    query: "",
    selectedIndex: 0,
    matches: [],
  },
  modal: null,
};

document.addEventListener("DOMContentLoaded", () => {
  bindElements();
  bindEvents();
  applyTheme();
  void bootstrap();
});

function createPaneState(id) {
  return {
    id,
    path: null,
    preview: null,
    expandedJson: new Set(),
    selectedJsonNodeId: null,
    selectedJsonPath: null,
    selectedStepId: null,
  };
}

function bindElements() {
  elements.browseRoot = document.getElementById("browse-root");
  elements.fileTree = document.getElementById("file-tree");
  elements.previewWork = document.getElementById("preview-work");
  elements.paneGrid = document.getElementById("pane-grid");
  elements.workspace = document.getElementById("workspace");
  elements.statusPaneCount = document.getElementById("status-pane-count");
  elements.statusActivePath = document.getElementById("status-active-path");
  elements.sidebarToggle = document.getElementById("sidebar-toggle");
  elements.splitPane = document.getElementById("split-pane");
  elements.themeToggle = document.getElementById("theme-toggle");
  elements.paletteToggle = document.getElementById("palette-toggle");
  elements.palette = document.getElementById("command-palette");
  elements.paletteInput = document.getElementById("palette-input");
  elements.paletteResults = document.getElementById("palette-results");
  elements.modal = document.getElementById("annotation-modal");
  elements.modalFile = document.getElementById("modal-file");
  elements.modalPath = document.getElementById("modal-path");
  elements.modalTags = document.getElementById("annotation-tags");
  elements.modalNote = document.getElementById("annotation-note");
  elements.modalDelete = document.getElementById("annotation-delete");
  elements.modalClose = document.getElementById("modal-close");
  elements.modalCancel = document.getElementById("annotation-cancel");
  elements.modalForm = document.getElementById("annotation-form");
}

function bindEvents() {
  elements.fileTree?.addEventListener("click", onTreeClick);
  elements.previewWork?.addEventListener("click", onWorkspaceClick);
  elements.sidebarToggle?.addEventListener("click", toggleSidebar);
  elements.splitPane?.addEventListener("click", splitActivePane);
  elements.themeToggle?.addEventListener("click", toggleTheme);
  elements.paletteToggle?.addEventListener("click", openPalette);
  elements.paletteInput?.addEventListener("input", onPaletteInput);
  elements.paletteResults?.addEventListener("click", onPaletteClick);
  elements.palette?.addEventListener("click", (event) => {
    if (event.target === elements.palette) {
      closePalette();
    }
  });
  document.addEventListener("keydown", onKeyDown);
  elements.modalClose?.addEventListener("click", closeModal);
  elements.modalCancel?.addEventListener("click", closeModal);
  elements.modalDelete?.addEventListener("click", onDeleteAnnotation);
  elements.modalForm?.addEventListener("submit", onSaveAnnotation);
  elements.modal?.addEventListener("click", (event) => {
    if (event.target === elements.modal) {
      closeModal();
    }
  });
}

async function bootstrap() {
  try {
    state.tree = await apiJson("/api/tree");
    state.browseRoot = state.tree.root_path || state.tree.name || ".";
    render();
  } catch (error) {
    renderFailure(error);
  }
}

function loadStoredTheme() {
  try {
    return globalThis.localStorage?.getItem("skim-theme") || "dark";
  } catch (_error) {
    return "dark";
  }
}

function storeTheme() {
  try {
    globalThis.localStorage?.setItem("skim-theme", state.theme);
  } catch (_error) {
    // Ignore storage failures in local-only environments.
  }
}

function applyTheme() {
  if (document.documentElement) {
    document.documentElement.dataset.theme = state.theme;
  }
  if (elements.themeToggle) {
    elements.themeToggle.textContent = state.theme === "dark" ? "◐" : "◑";
  }
}

function activePane() {
  return state.panes.find((pane) => pane.id === state.activePaneId) || state.panes[0] || null;
}

function paneById(paneId) {
  return state.panes.find((pane) => pane.id === paneId) || null;
}

function render() {
  applyTheme();
  renderTree();
  renderWorkspace();
  renderStatusBar();
  renderPalette();
}

function renderTree() {
  if (!elements.fileTree) {
    return;
  }
  if (!state.tree) {
    elements.fileTree.innerHTML = "";
    return;
  }
  const children = state.tree.children || [];
  elements.fileTree.innerHTML = children.map((child) => renderTreeNode(child, 0)).join("");
}

function renderTreeNode(node, depth) {
  const isDir = node.type === "dir";
  const expanded = state.expandedDirs.has(node.path);
  const selected = activePane()?.path === node.path;
  const icon = isDir ? (expanded ? "▾" : "▸") : fileIcon(node.ext || "");
  const indent = `style="padding-left:${14 + depth * 16}px"`;
  const labelAttrs = isDir
    ? ` data-dir-path="${escapeAttribute(node.path)}"`
    : ` data-file-path="${escapeAttribute(node.path)}"`;
  const toggle = isDir
    ? `<button class="tree-toggle" type="button" data-toggle-dir="${escapeAttribute(node.path)}">${icon}</button>`
    : `<span class="tree-toggle">${escapeHtml(icon)}</span>`;
  const children = isDir && expanded
    ? `<div class="tree-children">${(node.children || []).map((child) => renderTreeNode(child, depth + 1)).join("")}</div>`
    : "";

  return `
    <div class="tree-node ${selected ? "selected" : ""}">
      <div class="tree-row" ${indent}${labelAttrs}>
        ${toggle}
        <span class="tree-label">${escapeHtml(node.name)}</span>
        <span class="file-size">${escapeHtml(node.size || "")}</span>
      </div>
      ${children}
    </div>
  `;
}

function renderWorkspace() {
  if (!elements.paneGrid) {
    return;
  }
  const count = state.panes.length;
  elements.workspace?.classList.toggle("sidebar-hidden", !state.sidebarVisible);
  elements.paneGrid.className = `pane-grid panes-${count}`;
  elements.paneGrid.style.setProperty("--pane-count", String(Math.min(count, 3)));
  elements.paneGrid.innerHTML = state.panes.map(renderPaneShell).join("");
}

function renderPaneShell(pane) {
  const active = pane.id === state.activePaneId;
  const title = pane.preview?.name || "Preview";
  const kind = pane.preview?.kind || "empty";
  const path = pane.path || "No file selected";
  const closeButton = state.panes.length > 1
    ? `<button class="title-button" type="button" data-close-pane="${escapeAttribute(pane.id)}">×</button>`
    : "";

  return `
    <article class="pane-shell ${active ? "active" : ""}" data-pane-id="${escapeAttribute(pane.id)}">
      <header class="pane-header">
        <div class="pane-title">
          <div class="pane-title-text">${escapeHtml(title)}</div>
          <div class="pane-path">${escapeHtml(path)}</div>
        </div>
        <div class="title-actions">
          <span class="pane-kind">${escapeHtml(kind)}</span>
          ${closeButton}
        </div>
      </header>
      <div class="pane-content">
        ${renderPaneContent(pane)}
      </div>
    </article>
  `;
}

function renderPaneContent(pane) {
  if (!pane.preview) {
    return `
      <div class="empty-state">
        <div>
          <div class="empty-mark">◇</div>
          <div>Select a file to inspect it.</div>
        </div>
      </div>
    `;
  }

  switch (pane.preview.kind) {
    case "text":
      return renderTextPreview(pane.preview);
    case "markdown":
      return renderMarkdownPreview(pane.preview);
    case "csv":
      return renderCsvPreview(pane.preview);
    case "json_inspector":
      return renderJsonInspector(pane);
    case "trajectory":
      return renderTrajectoryPreview(pane);
    case "notebook":
      return renderNotebookPreview(pane.preview);
    case "too_large":
    case "error":
      return `<div class="notice">${escapeHtml(pane.preview.message)}</div>`;
    default:
      return `<div class="notice">Unsupported preview kind: ${escapeHtml(pane.preview.kind)}</div>`;
  }
}

function renderStatusBar() {
  if (elements.statusPaneCount) {
    elements.statusPaneCount.textContent = `${state.panes.length} pane${state.panes.length === 1 ? "" : "s"}`;
  }
  if (elements.statusActivePath) {
    elements.statusActivePath.textContent = activePane()?.path || "No file selected";
  }
  if (elements.browseRoot) {
    elements.browseRoot.textContent = state.browseRoot || "Loading…";
  }
}

function toggleSidebar() {
  state.sidebarVisible = !state.sidebarVisible;
  renderWorkspace();
}

function splitActivePane() {
  if (state.panes.length >= MAX_PANES) {
    return null;
  }
  const paneId = `pane-${state.nextPaneNumber}`;
  state.nextPaneNumber += 1;
  const activeIndex = state.panes.findIndex((pane) => pane.id === state.activePaneId);
  const newPane = createPaneState(paneId);
  const insertIndex = activeIndex >= 0 ? activeIndex + 1 : state.panes.length;
  state.panes.splice(insertIndex, 0, newPane);
  state.activePaneId = paneId;
  renderWorkspace();
  renderStatusBar();
  return newPane;
}

function closePane(paneId) {
  if (state.panes.length <= 1) {
    return;
  }
  const index = state.panes.findIndex((pane) => pane.id === paneId);
  if (index < 0) {
    return;
  }
  state.panes.splice(index, 1);
  if (state.activePaneId === paneId) {
    const replacement = state.panes[Math.max(0, index - 1)] || state.panes[0];
    state.activePaneId = replacement.id;
  }
  renderWorkspace();
  renderStatusBar();
}

function setActivePane(paneId) {
  if (state.activePaneId === paneId || !paneById(paneId)) {
    return;
  }
  state.activePaneId = paneId;
  renderWorkspace();
  renderStatusBar();
}

async function onTreeClick(event) {
  const toggle = event.target.closest("[data-toggle-dir]");
  if (toggle) {
    toggleDirectory(toggle.dataset.toggleDir);
    return;
  }

  const directory = event.target.closest("[data-dir-path]");
  if (directory) {
    toggleDirectory(directory.dataset.dirPath);
    return;
  }

  const target = event.target.closest("[data-file-path]");
  if (!target) {
    return;
  }
  await globalThis.loadPreviewForPane(target.dataset.filePath, state.activePaneId);
}

function toggleDirectory(path) {
  if (state.expandedDirs.has(path)) {
    state.expandedDirs.delete(path);
  } else {
    state.expandedDirs.add(path);
  }
  renderTree();
}

async function onWorkspaceClick(event) {
  const closeButton = event.target.closest("[data-close-pane]");
  if (closeButton) {
    closePane(closeButton.dataset.closePane);
    return;
  }

  const paneElement = event.target.closest("[data-pane-id]");
  const paneId = paneElement?.dataset.paneId;
  if (paneId) {
    setActivePane(paneId);
  }

  if (paneId) {
    await onPreviewClick(event, paneId);
  }
}

async function onPreviewClick(event, paneId = state.activePaneId) {
  const pane = paneById(paneId);
  if (!pane) {
    return;
  }

  const annotate = event.target.closest("[data-annotate]");
  if (annotate) {
    openModal({
      paneId,
      file: pane.path,
      path: annotate.dataset.annotate,
      annotation: decodeAnnotation(annotate.dataset.annotation),
    });
    return;
  }

  const stepRow = event.target.closest("[data-step-id]");
  if (stepRow) {
    pane.selectedStepId = stepRow.dataset.stepId;
    updateTrajectoryPreview(paneId);
    return;
  }

  const jsonToggle = event.target.closest("[data-toggle-json]");
  if (jsonToggle) {
    const node = jsonNodeByPath(pane, jsonToggle.dataset.toggleJson);
    if (node) {
      toggleJsonNode(pane, node);
    }
    return;
  }

  const jsonNode = event.target.closest("[data-json-node]");
  if (jsonNode) {
    const node = jsonNodeById(pane, jsonNode.dataset.jsonNode);
    if (node) {
      selectJsonNode(pane, node);
      if (node.children.length) {
        toggleJsonNode(pane, node, { preserveSelection: true });
        return;
      }
      updateJsonInspectorPreview(paneId);
    }
  }
}

async function loadPreview(path, options = {}) {
  return globalThis.loadPreviewForPane(path, state.activePaneId, options);
}

async function loadPreviewForPane(path, paneId, options = {}) {
  const pane = paneById(paneId);
  if (!pane) {
    return null;
  }
  try {
    pane.preview = await apiJson(`/api/preview?path=${encodeURIComponent(path)}`);
    pane.path = path;
    if (pane.preview.kind === "json_inspector") {
      initializeJsonState(pane, options.selectedJsonPath);
    } else {
      pane.selectedJsonNodeId = null;
      pane.selectedJsonPath = null;
      pane.expandedJson = new Set();
    }
    if (pane.preview.kind === "trajectory") {
      pane.selectedStepId = options.selectedStepId || pane.preview.initial_step_id;
    } else {
      pane.selectedStepId = null;
    }
    renderTree();
    renderWorkspace();
    renderStatusBar();
    return pane.preview;
  } catch (error) {
    pane.preview = {
      kind: "error",
      name: path.split("/").pop() || path,
      path,
      message: error.message || String(error),
    };
    pane.path = path;
    renderWorkspace();
    renderStatusBar();
    return pane.preview;
  }
}

function initializeJsonState(pane, selectedJsonPath = null) {
  const nodes = flattenNodes(pane.preview?.tree || []);
  const defaultExpanded = nodes
    .filter((node) => node.children.length > 0 && node.raw_path.length <= 1)
    .map((node) => node.path);
  pane.expandedJson = new Set(defaultExpanded);
  const preferred =
    nodes.find((node) => node.path === selectedJsonPath) ||
    nodes.find((node) => node.id === pane.preview?.initial_node_id) ||
    nodes[0] ||
    null;
  pane.selectedJsonNodeId = preferred ? preferred.id : null;
  pane.selectedJsonPath = preferred ? preferred.path : null;
}

function renderTextPreview(preview) {
  return `
    <div class="preview-card">
      <div class="detail-meta">
        <span class="path-pill">${escapeHtml(preview.path)}</span>
        ${preview.language ? `<span class="badge">${escapeHtml(preview.language)}</span>` : ""}
      </div>
      ${renderRenderValue(preview.render || { kind: "text", value: preview.content })}
    </div>
  `;
}

function renderMarkdownPreview(preview) {
  return `
    <div class="preview-card">
      <div class="detail-meta">
        <span class="path-pill">${escapeHtml(preview.path)}</span>
        <span class="badge">markdown</span>
      </div>
      ${renderMarkdown(preview.content)}
    </div>
  `;
}

function renderCsvPreview(preview) {
  const table = preview.columns.length
    ? `
      <div class="table-wrap">
        <table>
          <thead>
            <tr>${preview.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>
          </thead>
          <tbody>
            ${preview.rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}
          </tbody>
        </table>
      </div>
    `
    : `<p class="selection-subtitle">No tabular rows available.</p>`;

  const truncation = [
    preview.truncated_rows ? "rows truncated" : "",
    preview.truncated_columns ? "columns truncated" : "",
  ].filter(Boolean).join(" · ");

  return `
    <div class="preview-card">
      <div class="detail-meta">
        <span class="path-pill">${escapeHtml(preview.path)}</span>
        <span class="badge">${escapeHtml(preview.summary)}</span>
        ${preview.parse_error ? `<span class="badge">${escapeHtml(preview.parse_error)}</span>` : ""}
        ${truncation ? `<span class="badge">${escapeHtml(truncation)}</span>` : ""}
      </div>
      <div class="preview-block">${table}</div>
      <details class="raw-toggle">
        <summary>Raw CSV</summary>
        ${renderRenderValue(preview.raw_render || { kind: "text", value: preview.raw })}
      </details>
    </div>
  `;
}

function renderJsonInspector(pane) {
  const selected = selectedJsonNode(pane);
  if (!selected) {
    return `<div class="notice">Empty JSON payload.</div>`;
  }

  return `
    <div class="split-view" data-json-shell>
      <div class="pane-list" data-json-pane-list>${renderJsonPaneList(pane)}</div>
      <div class="detail-panel" data-json-detail>${renderJsonDetail(selected)}</div>
    </div>
  `;
}

function renderJsonPaneList(pane) {
  return (pane.preview?.tree || []).map((node) => renderJsonNode(node, 0, pane)).join("");
}

function renderJsonNode(node, depth, pane) {
  const expanded = pane.expandedJson.has(node.path);
  const selected = node.id === pane.selectedJsonNodeId;
  const rowStyle = `style="padding-left:${18 + depth * 16}px"`;
  const toggle = node.children.length
    ? `<button class="tree-toggle" type="button" data-toggle-json="${escapeAttribute(node.path)}">${expanded ? "▾" : "▸"}</button>`
    : `<span class="tree-toggle"></span>`;
  const marker = node.annotation ? `<span class="annotation-dot"></span>` : "";
  const children = node.children.length && expanded
    ? `<div class="tree-children">${node.children.map((child) => renderJsonNode(child, depth + 1, pane)).join("")}</div>`
    : "";
  return `
    <div class="tree-node ${selected ? "selected" : ""}">
      <div class="tree-row" data-json-node="${escapeAttribute(node.id)}" ${rowStyle}>
        ${toggle}
        <span class="tree-label">${marker}${marker ? " " : ""}${escapeHtml(node.label)}</span>
        <span class="file-size">${escapeHtml(node.style)}</span>
      </div>
      ${children}
    </div>
  `;
}

function selectedJsonNode(pane) {
  const nodes = flattenNodes(pane.preview?.tree || []);
  const selected =
    nodes.find((node) => node.id === pane.selectedJsonNodeId) ||
    nodes.find((node) => node.id === pane.preview?.initial_node_id) ||
    nodes[0] ||
    null;
  if (selected) {
    pane.selectedJsonNodeId = selected.id;
    pane.selectedJsonPath = selected.path;
  }
  return selected;
}

function jsonNodeById(pane, nodeId) {
  return flattenNodes(pane.preview?.tree || []).find((node) => node.id === nodeId) || null;
}

function jsonNodeByPath(pane, path) {
  return flattenNodes(pane.preview?.tree || []).find((node) => node.path === path) || null;
}

function selectJsonNode(pane, node) {
  pane.selectedJsonNodeId = node.id;
  pane.selectedJsonPath = node.path;
}

function toggleJsonNode(pane, node, options = {}) {
  if (pane.expandedJson.has(node.path)) {
    pane.expandedJson.delete(node.path);
  } else {
    pane.expandedJson.add(node.path);
  }
  if (!options.preserveSelection) {
    selectJsonNode(pane, node);
  }
  updateJsonInspectorPreview(pane.id);
}

function renderJsonDetail(selected) {
  return `
    <h3>${escapeHtml(selected.label)}</h3>
    <div class="detail-meta">
      <span class="path-pill">${escapeHtml(selected.path)}</span>
      <span class="badge">${escapeHtml(selected.type_name)}</span>
      ${selected.annotatable ? renderAnnotateButton(selected.annotation_path, selected.annotation) : ""}
    </div>
    ${renderAnnotationPanel(selected.annotation, selected.annotatable)}
    ${renderDetailPayload(selected.detail)}
  `;
}

function updateJsonInspectorPreview(paneId = state.activePaneId) {
  const pane = paneById(paneId);
  if (!pane || pane.preview?.kind !== "json_inspector") {
    renderWorkspace();
    return;
  }
  const shell = elements.previewWork?.querySelector(`[data-pane-id="${escapeSelectorValue(paneId)}"] [data-json-shell]`);
  if (!shell) {
    renderWorkspace();
    return;
  }
  const selected = selectedJsonNode(pane);
  if (!selected) {
    renderWorkspace();
    return;
  }
  const paneList = shell.querySelector("[data-json-pane-list]");
  const detail = shell.querySelector("[data-json-detail]");
  if (!paneList || !detail) {
    renderWorkspace();
    return;
  }
  const paneScroll = paneList.scrollTop;
  const detailScroll = detail.scrollTop;
  paneList.innerHTML = renderJsonPaneList(pane);
  detail.innerHTML = renderJsonDetail(selected);
  paneList.scrollTop = paneScroll;
  detail.scrollTop = detailScroll;
}

function renderTrajectoryPreview(pane) {
  const selected = selectedTrajectoryStep(pane);

  if (!selected) {
    return `
      <div class="preview-card">
        <div class="detail-meta">
          <span class="badge">${escapeHtml(pane.preview.header)}</span>
        </div>
        <p class="selection-subtitle">No trajectory steps available.</p>
      </div>
    `;
  }

  return `
    <div class="split-view" data-trajectory-shell>
      <div class="pane-list" data-trajectory-list>
        ${renderTrajectoryStepList(pane.preview, selected)}
      </div>
      <div class="step-detail" data-trajectory-detail>
        ${renderTrajectoryDetail(pane.preview, selected)}
      </div>
    </div>
  `;
}

function selectedTrajectoryStep(pane) {
  const preview = pane.preview;
  const selected =
    preview?.steps?.find((step) => step.id === pane.selectedStepId) ||
    preview?.steps?.find((step) => step.id === preview.initial_step_id) ||
    preview?.steps?.[0] ||
    null;
  if (selected) {
    pane.selectedStepId = selected.id;
  }
  return selected;
}

function renderTrajectoryStepList(preview, selected) {
  return preview.steps.map((step) => `
    <button class="selection-row ${step.id === selected.id ? "selected" : ""}" type="button" data-step-id="${escapeAttribute(step.id)}">
      <div class="selection-title">${escapeHtml(step.title)}</div>
      <div class="selection-subtitle">${escapeHtml(step.summary)}</div>
    </button>
  `).join("");
}

function renderTrajectoryDetail(preview, selected) {
  return `
    <h3>${escapeHtml(preview.header)}</h3>
    <div class="trajectory-meta">
      ${(preview.metadata_lines || []).map((line) => `<span class="path-pill">${escapeHtml(line)}</span>`).join("")}
    </div>
    <div class="preview-card">
      <h3>Final Output</h3>
      ${renderRenderValue(preview.final_output)}
    </div>
    <div class="preview-card">
      <h3>${escapeHtml(selected.title)}</h3>
      <div class="selection-subtitle">${escapeHtml(selected.path)}</div>
      ${(selected.items || []).map(renderTrajectoryItem).join("")}
    </div>
  `;
}

function updateTrajectoryPreview(paneId = state.activePaneId) {
  const pane = paneById(paneId);
  if (!pane || pane.preview?.kind !== "trajectory") {
    renderWorkspace();
    return;
  }
  const shell = elements.previewWork?.querySelector(`[data-pane-id="${escapeSelectorValue(paneId)}"] [data-trajectory-shell]`);
  if (!shell) {
    renderWorkspace();
    return;
  }
  const selected = selectedTrajectoryStep(pane);
  if (!selected) {
    renderWorkspace();
    return;
  }
  const list = shell.querySelector("[data-trajectory-list]");
  const detail = shell.querySelector("[data-trajectory-detail]");
  if (!list || !detail) {
    renderWorkspace();
    return;
  }
  const listScroll = list.scrollTop;
  const detailScroll = detail.scrollTop;
  list.innerHTML = renderTrajectoryStepList(pane.preview, selected);
  detail.innerHTML = renderTrajectoryDetail(pane.preview, selected);
  list.scrollTop = listScroll;
  detail.scrollTop = detailScroll;
}

function renderTrajectoryItem(item) {
  if (item.kind === "tool") {
    return `
      <article class="item-card">
        <div class="item-header">
          <div>
            <div class="selection-title">
              ${item.annotation ? `<span class="annotation-dot"></span>` : ""}
              <strong>${escapeHtml(item.title)}</strong>
            </div>
            <div class="item-meta">
              <span class="badge">${escapeHtml(item.tool_name)}</span>
              <span class="badge">${escapeHtml(item.call_id || "")}</span>
              ${item.status ? `<span class="badge">${escapeHtml(item.status)}</span>` : ""}
            </div>
          </div>
          ${renderAnnotateButton(item.annotation_path, item.annotation)}
        </div>
        ${renderAnnotationPanel(item.annotation, true)}
        <div class="subsection-grid">
          <section class="subsection-card">
            <div class="subsection-header">
              <strong>Input</strong>
              ${renderAnnotateButton(item.input.annotation_path, item.input.annotation)}
            </div>
            ${renderAnnotationPanel(item.input.annotation, true)}
            ${renderRenderValue(item.input.render)}
          </section>
          <section class="subsection-card">
            <div class="subsection-header">
              <strong>Output</strong>
              ${renderAnnotateButton(item.output.annotation_path, item.output.annotation)}
            </div>
            ${renderAnnotationPanel(item.output.annotation, true)}
            ${renderRenderValue(item.output.render)}
          </section>
        </div>
      </article>
    `;
  }

  return `
    <article class="item-card">
      <div class="item-header">
        <div>
          <div class="selection-title">
            ${item.annotation ? `<span class="annotation-dot"></span>` : ""}
            <strong>${escapeHtml(item.title)}</strong>
          </div>
          <div class="item-meta">
            <span class="badge">${escapeHtml(item.event_kind || "")}</span>
            ${item.role ? `<span class="badge">${escapeHtml(item.role)}</span>` : ""}
            ${item.status ? `<span class="badge">${escapeHtml(item.status)}</span>` : ""}
            ${item.excerpt ? `<span class="badge">${escapeHtml(item.excerpt)}</span>` : ""}
          </div>
        </div>
        ${renderAnnotateButton(item.annotation_path, item.annotation)}
      </div>
      ${renderAnnotationPanel(item.annotation, true)}
      ${renderRenderValue(item.render)}
    </article>
  `;
}

function renderNotebookPreview(preview) {
  const version = preview.summary.nbformat_minor != null
    ? `${preview.summary.nbformat}.${preview.summary.nbformat_minor}`
    : String(preview.summary.nbformat ?? "");
  const cells = preview.cells || [];
  const body = cells.length
    ? cells.map(renderNotebookCell).join("")
    : `<div class="preview-card"><div class="selection-subtitle">Empty notebook.</div></div>`;

  return `
    <div class="notebook-stack">
      <section class="preview-card">
        <div class="notebook-title">Notebook Preview</div>
        <div class="notebook-meta">
          <span class="badge">${escapeHtml(preview.path)}</span>
          <span class="badge">${escapeHtml(`${preview.summary.cell_count} cells`)}</span>
          ${version ? `<span class="badge">nbformat ${escapeHtml(version)}</span>` : ""}
          <span class="badge">${escapeHtml(preview.language || "python")}</span>
        </div>
      </section>
      ${body}
    </div>
  `;
}

function renderNotebookCell(cell) {
  const outputs = (cell.outputs || []).map((output) => `
    <div class="preview-block">
      <div class="notebook-label">${escapeHtml(output.title)}</div>
      ${renderRenderValue(output.render)}
    </div>
  `).join("");

  return `
    <section class="notebook-cell">
      <div class="notebook-label">${escapeHtml(cell.title)}</div>
      ${renderRenderValue(cell.render)}
      ${outputs}
    </section>
  `;
}

function renderAnnotateButton(path, annotation) {
  if (!path) {
    return "";
  }
  const payload = annotation ? escapeAttribute(JSON.stringify(annotation)) : "";
  const label = annotation ? "Edit annotation" : "Annotate";
  return `<button class="title-button" type="button" data-annotate="${escapeAttribute(path)}" data-annotation="${payload}">${label}</button>`;
}

function renderAnnotationPanel(annotation, annotatable) {
  if (!annotatable) {
    return `<div class="annotation-panel"><div class="selection-subtitle">Annotations unavailable for this node.</div></div>`;
  }
  if (!annotation) {
    return `<div class="annotation-panel"><div class="selection-subtitle">No annotation yet.</div></div>`;
  }
  return `
    <div class="annotation-panel">
      <div class="annotation-tags">
        ${annotation.tags.map((tag) => `<span class="annotation-tag">${escapeHtml(tag)}</span>`).join("")}
      </div>
      <div>${escapeHtml(annotation.note || "(empty)")}</div>
    </div>
  `;
}

function renderRenderValue(render) {
  if (!render) {
    return `<div class="preview-block"><div class="selection-subtitle">No detail available.</div></div>`;
  }
  switch (render.kind) {
    case "syntax":
      return renderSyntaxBlock(render);
    case "markdown":
      return `<div class="preview-block">${renderMarkdown(render.value)}</div>`;
    case "code":
      return renderCodeBlock(render.value, render.language || "text");
    case "json":
      return `<pre class="json-block">${escapeHtml(JSON.stringify(render.value, null, 2))}</pre>`;
    case "text":
    default:
      return `<pre class="text-block">${escapeHtml(render.value || "")}</pre>`;
  }
}

function renderDetailPayload(detail) {
  if (!detail || detail.kind !== "detail") {
    return `<div class="preview-block"><div class="selection-subtitle">No detail available.</div></div>`;
  }
  const blocks = (detail.blocks || []).map(renderDetailBlock).join("");
  return `<div class="detail-stack">${blocks || `<div class="preview-block"><div class="selection-subtitle">No detail available.</div></div>`}</div>`;
}

function renderDetailBlock(block) {
  if (!block) {
    return "";
  }
  switch (block.kind) {
    case "syntax":
      return renderSyntaxBlock(block);
    case "fields":
      return `
        <div class="detail-fields">
          ${(block.fields || []).map((field) => `
            <div class="detail-field">
              <span class="detail-field-label">${escapeHtml(field.label)}</span>
              <span class="detail-field-value">${escapeHtml(field.value)}</span>
            </div>
          `).join("")}
        </div>
      `;
    case "section": {
      const open = block.collapsed ? "" : " open";
      const body = (block.blocks || []).map(renderDetailBlock).join("");
      return `
        <details class="detail-section"${open}>
          <summary>${escapeHtml(block.title || "Section")}</summary>
          <div class="detail-section-body">${body}</div>
        </details>
      `;
    }
    case "markdown":
      return `<div class="preview-block">${renderMarkdown(block.value)}</div>`;
    case "code":
      return renderCodeBlock(block.value, block.language || "text");
    case "json":
      return `<pre class="json-block">${escapeHtml(JSON.stringify(block.value, null, 2))}</pre>`;
    case "text":
    default:
      return `<pre class="text-block">${escapeHtml(block.value || "")}</pre>`;
  }
}

function renderCodeBlock(value, language) {
  return `<pre class="code-block" data-language="${escapeAttribute(language || "text")}"><code>${escapeHtml(value || "")}</code></pre>`;
}

function renderSyntaxBlock(render) {
  if (render && render.html) {
    return render.html;
  }
  return renderCodeBlock(render?.value || "", render?.language || "text");
}

function renderMarkdown(value) {
  let html = escapeHtml(value || "");
  html = html.replace(/```([\s\S]*?)```/g, (_match, code) => renderCodeBlock(code.trim(), "text"));
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/^- (.+)$/gm, "<div>• $1</div>");
  html = html.replace(/\n\n/g, "<br><br>");
  return `<div class="markdown-block">${html}</div>`;
}

function flattenNodes(nodes) {
  const result = [];
  for (const node of nodes) {
    result.push(node);
    result.push(...flattenNodes(node.children || []));
  }
  return result;
}

function decodeAnnotation(value) {
  if (!value) {
    return null;
  }
  try {
    return JSON.parse(value);
  } catch (_error) {
    return null;
  }
}

function openModal(payload) {
  state.modal = payload;
  elements.modalFile && (elements.modalFile.textContent = payload.file || "");
  elements.modalPath && (elements.modalPath.textContent = payload.path || "");
  if (elements.modalTags) {
    elements.modalTags.value = payload.annotation ? payload.annotation.tags.join(", ") : "";
  }
  if (elements.modalNote) {
    elements.modalNote.value = payload.annotation ? payload.annotation.note : "";
  }
  elements.modalDelete?.classList.toggle("hidden", !payload.annotation);
  elements.modal?.classList.remove("hidden");
  elements.modalTags?.focus();
}

function closeModal() {
  state.modal = null;
  elements.modal?.classList.add("hidden");
}

async function onSaveAnnotation(event) {
  event.preventDefault();
  if (!state.modal) {
    return;
  }
  const tags = (elements.modalTags?.value || "")
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
  await apiJson("/api/annotations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file: state.modal.file,
      path: state.modal.path,
      tags,
      note: elements.modalNote?.value || "",
    }),
  });
  const pane = paneById(state.modal.paneId);
  const selectedJsonPath = pane?.selectedJsonPath;
  const selectedStepId = pane?.selectedStepId;
  const paneId = state.modal.paneId;
  const file = state.modal.file;
  closeModal();
  await globalThis.loadPreviewForPane(file, paneId, { selectedJsonPath, selectedStepId });
}

async function onDeleteAnnotation() {
  if (!state.modal) {
    return;
  }
  await apiJson("/api/annotations", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file: state.modal.file,
      path: state.modal.path,
    }),
  });
  const pane = paneById(state.modal.paneId);
  const selectedJsonPath = pane?.selectedJsonPath;
  const selectedStepId = pane?.selectedStepId;
  const paneId = state.modal.paneId;
  const file = state.modal.file;
  closeModal();
  await globalThis.loadPreviewForPane(file, paneId, { selectedJsonPath, selectedStepId });
}

function openPalette() {
  state.palette.open = true;
  state.palette.query = "";
  state.palette.selectedIndex = 0;
  updatePaletteMatches();
  renderPalette();
  elements.paletteInput?.focus();
}

function closePalette() {
  state.palette.open = false;
  renderPalette();
}

function onPaletteInput(event) {
  state.palette.query = event.target.value;
  state.palette.selectedIndex = 0;
  updatePaletteMatches();
  renderPalette();
}

function onPaletteClick(event) {
  const target = event.target.closest("[data-palette-path]");
  if (!target) {
    return;
  }
  state.palette.selectedIndex = Number(target.dataset.paletteIndex || 0);
  void openPaletteSelection();
}

function updatePaletteMatches() {
  const files = flattenTreeFiles(state.tree);
  const query = (state.palette.query || "").trim().toLowerCase();
  const matches = files
    .map((file) => ({
      ...file,
      score: fuzzyScore(query, file.name.toLowerCase(), file.path.toLowerCase()),
    }))
    .filter((file) => file.score < Number.POSITIVE_INFINITY)
    .sort((left, right) => left.score - right.score || left.path.localeCompare(right.path))
    .slice(0, 40);
  state.palette.matches = matches;
  if (state.palette.selectedIndex >= matches.length) {
    state.palette.selectedIndex = Math.max(0, matches.length - 1);
  }
}

function flattenTreeFiles(tree, parents = []) {
  if (!tree) {
    return [];
  }
  if (tree.type === "file") {
    return [{ name: tree.name, path: tree.path, parents }];
  }
  return (tree.children || []).flatMap((child) =>
    flattenTreeFiles(child, tree.name && tree.path !== "." ? [...parents, tree.name] : parents)
  );
}

function fuzzyScore(query, name, path) {
  if (!query) {
    return path.length;
  }
  const nameScore = subsequenceScore(query, name);
  const pathScore = subsequenceScore(query, path);
  return Math.min(nameScore, pathScore + 100);
}

function subsequenceScore(query, value) {
  let score = 0;
  let index = -1;
  for (const char of query) {
    index = value.indexOf(char, index + 1);
    if (index < 0) {
      return Number.POSITIVE_INFINITY;
    }
    score += index;
  }
  return score + value.length - query.length;
}

async function openPaletteSelection() {
  const match = state.palette.matches[state.palette.selectedIndex] || null;
  if (!match) {
    return null;
  }
  await globalThis.loadPreviewForPane(match.path, state.activePaneId);
  closePalette();
  return match.path;
}

function renderPalette() {
  if (!elements.palette || !elements.paletteResults) {
    return;
  }
  elements.palette.classList.toggle("hidden", !state.palette.open);
  if (elements.paletteInput && elements.paletteInput.value !== state.palette.query) {
    elements.paletteInput.value = state.palette.query;
  }
  elements.paletteResults.innerHTML = state.palette.matches.length
    ? state.palette.matches.map((match, index) => `
        <button
          class="palette-row ${index === state.palette.selectedIndex ? "selected" : ""}"
          type="button"
          data-palette-path="${escapeAttribute(match.path)}"
          data-palette-index="${index}"
        >
          <span>${escapeHtml(match.name)}</span>
          <span class="palette-path">${escapeHtml(match.path)}</span>
        </button>
      `).join("")
    : `<div class="preview-block"><div class="selection-subtitle">No matching files.</div></div>`;
}

function onKeyDown(event) {
  const key = event.key.toLowerCase();
  if ((event.metaKey || event.ctrlKey) && key === "k") {
    event.preventDefault();
    if (state.palette.open) {
      closePalette();
    } else {
      openPalette();
    }
    return;
  }
  if ((event.metaKey || event.ctrlKey) && key === "b") {
    event.preventDefault();
    toggleSidebar();
    return;
  }
  if (event.key === "Escape") {
    if (state.modal) {
      closeModal();
      return;
    }
    if (state.palette.open) {
      closePalette();
    }
    return;
  }
  if (!state.palette.open) {
    return;
  }
  if (event.key === "ArrowDown") {
    event.preventDefault();
    state.palette.selectedIndex = Math.min(
      state.palette.selectedIndex + 1,
      Math.max(0, state.palette.matches.length - 1),
    );
    renderPalette();
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    state.palette.selectedIndex = Math.max(0, state.palette.selectedIndex - 1);
    renderPalette();
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    void openPaletteSelection();
  }
}

function toggleTheme() {
  state.theme = state.theme === "dark" ? "light" : "dark";
  storeTheme();
  applyTheme();
  renderWorkspace();
}

function fileIcon(extension) {
  switch (extension) {
    case ".py":
      return "λ";
    case ".json":
    case ".jsonl":
    case ".ipynb":
      return "{}";
    case ".yaml":
    case ".yml":
      return "⚙";
    case ".md":
      return "¶";
    case ".css":
      return "#";
    case ".js":
    case ".ts":
    case ".tsx":
      return "⋯";
    default:
      return "•";
  }
}

function renderFailure(error) {
  const pane = activePane();
  if (pane) {
    pane.preview = {
      kind: "error",
      name: "preview",
      path: pane.path || "",
      message: error.message || String(error),
    };
  }
  renderWorkspace();
  renderStatusBar();
}

async function apiJson(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#96;");
}

function escapeSelectorValue(value) {
  return String(value).replaceAll("\\", "\\\\").replaceAll('"', '\\"');
}

globalThis.createPaneState = createPaneState;
globalThis.loadPreviewForPane = loadPreviewForPane;
