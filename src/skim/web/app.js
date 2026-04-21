const MAX_PANES = 6;
const DEFAULT_SIDEBAR_WIDTH = 220;
const MIN_SIDEBAR_WIDTH = 180;
const MAX_SIDEBAR_VIEWPORT_RATIO = 0.45;
const RESIZER_GUTTER = 12;
const STACKED_BREAKPOINT = 900;
const MIN_SPLIT_RATIO = 20;
const MAX_SPLIT_RATIO = 80;
const MIN_TRACK_WEIGHT = 0.45;
const PANE_LAYOUT_STORAGE_PREFIX = "skim-pane-layout-";
const SPLIT_RATIO_STORAGE_PREFIX = "skim-split-ratio-";
const DEFAULT_JSON_SPLIT_RATIO = loadStoredSplitRatio("json", 38);
const DEFAULT_TRAJECTORY_SPLIT_RATIO = loadStoredSplitRatio("trajectory", 38);

const elements = {};

const state = {
  tree: null,
  browseRoot: "",
  expandedDirs: new Set(["."]),
  panes: [createPaneState("pane-1")],
  activePaneId: "pane-1",
  nextPaneNumber: 2,
  sidebarVisible: true,
  sidebarWidth: loadStoredSidebarWidth(),
  activeResize: null,
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
    selectedWorkbookSheetName: null,
    selectedAnnotationIds: {},
    jsonSplitRatio: loadStoredSplitRatio("json", DEFAULT_JSON_SPLIT_RATIO, id),
    trajectorySplitRatio: loadStoredSplitRatio("trajectory", DEFAULT_TRAJECTORY_SPLIT_RATIO, id),
  };
}

function bindElements() {
  elements.appShell = document.getElementById("app-shell");
  elements.browseRoot = document.getElementById("browse-root");
  elements.fileTree = document.getElementById("file-tree");
  elements.previewWork = document.getElementById("preview-work");
  elements.paneGrid = document.getElementById("pane-grid");
  elements.workspace = document.getElementById("workspace");
  elements.sidebarResizer = document.getElementById("sidebar-resizer");
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
  elements.fileTree?.addEventListener("keydown", onTreeKeyDown);
  elements.previewWork?.addEventListener("click", onWorkspaceClick);
  elements.previewWork?.addEventListener("pointerdown", onPreviewPointerDown);
  elements.sidebarToggle?.addEventListener("click", toggleSidebar);
  elements.sidebarResizer?.addEventListener("pointerdown", beginSidebarResize);
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
  document.addEventListener("pointermove", onGlobalPointerMove);
  document.addEventListener("pointerup", endActiveResize);
  document.addEventListener("pointercancel", endActiveResize);
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
  const visual = resolveFileVisual(node);
  const icon = isDir ? (expanded ? "▾" : "▸") : "";
  const indent = `style="padding-left:${14 + depth * 16}px"`;
  const behaviorAttrs = isDir
    ? ` data-dir-path="${escapeAttribute(node.path)}" role="button" tabindex="0" aria-expanded="${expanded ? "true" : "false"}"`
    : ` data-file-path="${escapeAttribute(node.path)}"`;
  const toggle = isDir
    ? `<span class="tree-toggle" data-toggle-dir="${escapeAttribute(node.path)}" aria-hidden="true">${icon}</span>`
    : `<span class="tree-toggle"></span>`;
  const children = isDir && expanded
    ? `<div class="tree-children">${(node.children || []).map((child) => renderTreeNode(child, depth + 1)).join("")}</div>`
    : "";

  return `
    <div class="tree-node ${selected ? "selected" : ""}">
      <div class="tree-row" data-file-kind="${escapeAttribute(visual.kind)}" data-file-group="${escapeAttribute(visual.group)}" ${indent}${behaviorAttrs}>
        ${toggle}
        <span class="tree-label tree-file-label">${renderFileIcon(visual)}<span class="tree-name">${escapeHtml(node.name)}</span></span>
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
  const layoutMode = paneLayoutMode(count);
  elements.workspace?.classList.toggle("sidebar-hidden", !state.sidebarVisible);
  elements.sidebarResizer?.classList.toggle("hidden", !canResizeSidebar());
  elements.paneGrid.className = `pane-grid panes-${count} layout-${layoutMode}`;
  applySidebarWidth();
  elements.paneGrid.innerHTML = renderPaneGridMarkup(state.panes);
  applyPaneGridLayout();
}

function renderPaneShell(pane) {
  const active = pane.id === state.activePaneId;
  const title = pane.preview?.name || "Preview";
  const kind = previewLabel(pane.preview);
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

function previewLabel(preview) {
  if (!preview) {
    return "Empty";
  }
  if (preview.kind === "text") {
    return languageLabel(preview.language);
  }
  const kindLabels = {
    markdown: "Markdown",
    csv: "CSV",
    xlsx: "Excel",
    notebook: "Notebook",
    json_inspector: "JSON",
    trajectory: "Trajectory",
    too_large: "Too Large",
    error: "Error",
  };
  return kindLabels[preview.kind] || languageLabel(preview.language);
}

function languageLabel(language) {
  if (!language) {
    return "Text";
  }
  const labels = {
    python: "Python",
    javascript: "JavaScript",
    typescript: "TypeScript",
    json: "JSON",
    yaml: "YAML",
    toml: "TOML",
    html: "HTML",
    css: "CSS",
    sql: "SQL",
    bash: "Shell",
    shell: "Shell",
    xml: "XML",
    rust: "Rust",
    go: "Go",
    markdown: "Markdown",
    text: "Text",
  };
  return labels[language] || language.charAt(0).toUpperCase() + language.slice(1);
}

function renderPaneGridMarkup(panes) {
  const count = panes.length;
  if (count <= 1) {
    return panes.map(renderPaneShell).join("");
  }
  if (count <= 3) {
    return renderPaneRowMarkup(panes, paneLayoutKey(count), paneLayoutKey(count));
  }
  const top = panes.slice(0, 3);
  const bottom = panes.slice(3);
  return `
    ${renderPaneRowMarkup(top, "grid-2x3", "grid-2x3-top")}
    <div class="split-resizer pane-row-resizer" data-layout-key="grid-2x3" data-resize-pane-row="0" aria-hidden="true"></div>
    ${renderPaneRowMarkup(bottom, "grid-2x3", "grid-2x3-bottom")}
  `;
}

function renderPaneRowMarkup(panes, layoutKey, rowKey) {
  return `
    <div class="pane-row" data-pane-row-key="${escapeAttribute(rowKey)}">
      ${panes.map((pane, index) => `
        ${renderPaneShell(pane)}
        ${index < panes.length - 1 ? renderPaneColumnResizer(layoutKey, rowKey, index) : ""}
      `).join("")}
    </div>
  `;
}

function renderPaneColumnResizer(layoutKey, rowKey, index) {
  return `<div class="split-resizer pane-col-resizer" data-layout-key="${escapeAttribute(layoutKey)}" data-row-key="${escapeAttribute(rowKey)}" data-resize-pane-col="${index}" aria-hidden="true"></div>`;
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
    case "xlsx":
      return renderXlsxPreview(pane);
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

function isStackedLayout(viewportWidth = getViewportWidth()) {
  return viewportWidth <= STACKED_BREAKPOINT;
}

function getViewportWidth() {
  return (
    globalThis.innerWidth ||
    document.documentElement?.clientWidth ||
    1280
  );
}

function maxSidebarWidth(viewportWidth = getViewportWidth()) {
  return Math.max(MIN_SIDEBAR_WIDTH, Math.floor(viewportWidth * MAX_SIDEBAR_VIEWPORT_RATIO));
}

function clampSidebarWidth(width, viewportWidth = getViewportWidth()) {
  const numeric = Number(width);
  if (!Number.isFinite(numeric)) {
    return DEFAULT_SIDEBAR_WIDTH;
  }
  return Math.min(maxSidebarWidth(viewportWidth), Math.max(MIN_SIDEBAR_WIDTH, Math.round(numeric)));
}

function loadStoredSidebarWidth() {
  try {
    const raw = globalThis.localStorage?.getItem("skim-sidebar-width");
    if (!raw) {
      return DEFAULT_SIDEBAR_WIDTH;
    }
    return clampSidebarWidth(Number(raw));
  } catch (_error) {
    return DEFAULT_SIDEBAR_WIDTH;
  }
}

function storeSidebarWidth() {
  try {
    globalThis.localStorage?.setItem("skim-sidebar-width", String(state.sidebarWidth));
  } catch (_error) {
    // Ignore storage failures in local-only environments.
  }
}

function applySidebarWidth() {
  elements.workspace?.style?.setProperty("--sidebar-width", `${state.sidebarWidth}px`);
}

function setSidebarWidth(width, options = {}) {
  const viewportWidth = options.viewportWidth || getViewportWidth();
  state.sidebarWidth = clampSidebarWidth(width, viewportWidth);
  applySidebarWidth();
  if (options.persist !== false) {
    storeSidebarWidth();
  }
  return state.sidebarWidth;
}

function canResizeSidebar() {
  return state.sidebarVisible && !isStackedLayout();
}

function canResizePaneLayout(viewportWidth = getViewportWidth()) {
  return state.panes.length > 1 && !isStackedLayout(viewportWidth);
}

function canResizeSplitViews(viewportWidth = getViewportWidth()) {
  return !isStackedLayout(viewportWidth);
}

function sidebarWidthFromClientX(clientX) {
  const left = elements.workspace?.getBoundingClientRect?.().left || 0;
  return clientX - left;
}

function beginSidebarResize(event) {
  if (!canResizeSidebar()) {
    return false;
  }
  return beginResize(
    {
      type: "sidebar",
      pointerId: event.pointerId ?? null,
    },
    event,
  );
}

function beginResize(payload, event) {
  state.activeResize = payload;
  elements.appShell?.classList.add("layout-resizing");
  if (payload.type === "sidebar") {
    elements.appShell?.classList.add("sidebar-resizing");
  }
  event.preventDefault?.();
  return true;
}

function onGlobalPointerMove(event) {
  if (!state.activeResize) {
    return;
  }
  switch (state.activeResize.type) {
    case "sidebar":
      setSidebarWidth(sidebarWidthFromClientX(event.clientX), { persist: false });
      break;
    case "split":
      updateSplitRatioFromPointer(
        state.activeResize.kind,
        state.activeResize.paneId,
        state.activeResize.element,
        event.clientX,
      );
      break;
    case "pane-col":
      updatePaneColumnFromPointer(
        state.activeResize.layoutKey,
        state.activeResize.rowKey,
        state.activeResize.index,
        event.clientX,
      );
      break;
    case "pane-row":
      updatePaneRowFromPointer(
        state.activeResize.layoutKey,
        state.activeResize.index,
        event.clientY,
      );
      break;
    default:
      break;
  }
}

function endActiveResize() {
  if (!state.activeResize) {
    return false;
  }
  if (state.activeResize.type === "split") {
    storeSplitRatio(state.activeResize.kind, paneById(state.activeResize.paneId));
  }
  if (state.activeResize.type === "pane-col" || state.activeResize.type === "pane-row") {
    storePaneLayout(state.activeResize.layoutKey);
  }
  state.activeResize = null;
  elements.appShell?.classList.remove("layout-resizing");
  elements.appShell?.classList.remove("sidebar-resizing");
  storeSidebarWidth();
  return true;
}

function paneLayoutMode(count) {
  if (count <= 1) {
    return "single";
  }
  if (count <= 3) {
    return "row";
  }
  return "grid";
}

function paneLayoutKey(count) {
  if (count <= 1) {
    return "single";
  }
  if (count <= 3) {
    return `row-${count}`;
  }
  return "grid-2x3";
}

function defaultPaneLayout(layoutKey) {
  if (layoutKey === "grid-2x3") {
    return { topCols: [1, 1, 1], bottomCols: [1, 1, 1], rows: [1, 1] };
  }
  if (layoutKey.startsWith("row-")) {
    const count = Number(layoutKey.split("-")[1] || 1);
    return { cols: Array.from({ length: count }, () => 1) };
  }
  return { cols: [1] };
}

function normalizeTrackWeights(weights, count) {
  if (!Array.isArray(weights) || weights.length !== count) {
    return Array.from({ length: count }, () => 1);
  }
  const normalized = weights.map((weight) => {
    const numeric = Number(weight);
    return Number.isFinite(numeric) && numeric > 0 ? numeric : 1;
  });
  return normalized;
}

function loadStoredPaneLayout(layoutKey, fallback = defaultPaneLayout(layoutKey)) {
  try {
    const raw = globalThis.localStorage?.getItem(`${PANE_LAYOUT_STORAGE_PREFIX}${layoutKey}`);
    if (!raw) {
      return fallback;
    }
    const parsed = JSON.parse(raw);
    if (layoutKey === "grid-2x3") {
      const sharedCols = normalizeTrackWeights(parsed.cols, fallback.topCols.length);
      return {
        topCols: normalizeTrackWeights(
          parsed.topCols || sharedCols,
          fallback.topCols.length,
        ),
        bottomCols: normalizeTrackWeights(
          parsed.bottomCols || sharedCols,
          fallback.bottomCols.length,
        ),
        rows: normalizeTrackWeights(parsed.rows, fallback.rows.length),
      };
    }
    return {
      cols: normalizeTrackWeights(parsed.cols, fallback.cols.length),
      rows: fallback.rows ? normalizeTrackWeights(parsed.rows, fallback.rows.length) : undefined,
    };
  } catch (_error) {
    return fallback;
  }
}

function setStoredPaneLayout(layoutKey, layout) {
  try {
    globalThis.localStorage?.setItem(
      `${PANE_LAYOUT_STORAGE_PREFIX}${layoutKey}`,
      JSON.stringify(layout),
    );
  } catch (_error) {
    // Ignore storage failures in local-only environments.
  }
  return layout;
}

function storePaneLayout(layoutKey) {
  return setStoredPaneLayout(layoutKey, currentPaneLayout(layoutKey));
}

function currentPaneLayout(layoutKey = paneLayoutKey(state.panes.length)) {
  const fallback = defaultPaneLayout(layoutKey);
  if (layoutKey === "grid-2x3") {
    return {
      topCols: state.gridTopCols || loadStoredPaneLayout(layoutKey, fallback).topCols,
      bottomCols: state.gridBottomCols || loadStoredPaneLayout(layoutKey, fallback).bottomCols,
      rows: state.gridRows || loadStoredPaneLayout(layoutKey, fallback).rows,
    };
  }
  return {
    cols: state[layoutStateKey(layoutKey)] || loadStoredPaneLayout(layoutKey, fallback).cols,
  };
}

function layoutStateKey(layoutKey) {
  return `paneLayout_${layoutKey.replaceAll("-", "_")}`;
}

function ensurePaneLayoutState(layoutKey) {
  const fallback = defaultPaneLayout(layoutKey);
  const stored = loadStoredPaneLayout(layoutKey, fallback);
  if (layoutKey === "grid-2x3") {
    if (!Array.isArray(state.gridTopCols)) {
      state.gridTopCols = stored.topCols;
    }
    if (!Array.isArray(state.gridBottomCols)) {
      state.gridBottomCols = stored.bottomCols;
    }
    if (!Array.isArray(state.gridRows)) {
      state.gridRows = stored.rows;
    }
    return {
      topCols: state.gridTopCols,
      bottomCols: state.gridBottomCols,
      rows: state.gridRows,
    };
  }
  if (!Array.isArray(state[layoutStateKey(layoutKey)])) {
    state[layoutStateKey(layoutKey)] = stored.cols;
  }
  return { cols: state[layoutStateKey(layoutKey)] };
}

function loadStoredSplitRatio(kind, defaultRatio, paneId = null) {
  try {
    if (paneId) {
      const paneRaw = globalThis.localStorage?.getItem(splitRatioStorageKey(kind, paneId));
      if (paneRaw != null) {
        return clampSplitRatio(Number(paneRaw));
      }
    }
    const raw = globalThis.localStorage?.getItem(splitRatioStorageKey(kind));
    return clampSplitRatio(raw != null ? Number(raw) : defaultRatio);
  } catch (_error) {
    return clampSplitRatio(defaultRatio);
  }
}

function setStoredSplitRatio(kind, ratio, options = {}) {
  const clamped = clampSplitRatio(ratio);
  if (options.persist !== false) {
    try {
      globalThis.localStorage?.setItem(splitRatioStorageKey(kind), String(clamped));
    } catch (_error) {
      // Ignore storage failures in local-only environments.
    }
  }
  return clamped;
}

function splitRatioStorageKey(kind, paneId = null) {
  return paneId
    ? `${SPLIT_RATIO_STORAGE_PREFIX}${kind}-${paneId}`
    : `${SPLIT_RATIO_STORAGE_PREFIX}${kind}`;
}

function storeSplitRatio(kind, pane = null) {
  if (!pane) {
    return setStoredSplitRatio(kind, defaultSplitRatio(kind));
  }
  return setPaneSplitRatio(pane, kind, pane[splitStateKey(kind)], { persist: true });
}

function splitStateKey(kind) {
  return `${kind}SplitRatio`;
}

function defaultSplitRatio(kind) {
  return kind === "trajectory" ? DEFAULT_TRAJECTORY_SPLIT_RATIO : DEFAULT_JSON_SPLIT_RATIO;
}

function currentSplitRatio(pane, kind) {
  const ratio = pane?.[splitStateKey(kind)];
  return Number.isFinite(Number(ratio)) ? clampSplitRatio(ratio) : defaultSplitRatio(kind);
}

function setPaneSplitRatio(pane, kind, ratio, options = {}) {
  if (!pane) {
    return clampSplitRatio(ratio);
  }
  const clamped = clampSplitRatio(ratio);
  pane[splitStateKey(kind)] = clamped;
  if (options.persist !== false) {
    try {
      globalThis.localStorage?.setItem(splitRatioStorageKey(kind, pane.id), String(clamped));
    } catch (_error) {
      // Ignore storage failures in local-only environments.
    }
  }
  return clamped;
}

function clampSplitRatio(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 38;
  }
  return Math.min(MAX_SPLIT_RATIO, Math.max(MIN_SPLIT_RATIO, Math.round(numeric)));
}

function trackTemplate(weights) {
  return weights
    .map((weight) => `minmax(0, ${weight}fr)`)
    .join(` ${RESIZER_GUTTER}px `);
}

function adjustTrackPair(weights, index, ratio) {
  const next = [...weights];
  const pairTotal = next[index] + next[index + 1];
  const minWeight = Math.min(MIN_TRACK_WEIGHT, pairTotal / 2);
  const clampedRatio = Math.min(1 - minWeight / pairTotal, Math.max(minWeight / pairTotal, ratio));
  next[index] = pairTotal * clampedRatio;
  next[index + 1] = pairTotal - next[index];
  return next;
}

function applyPaneGridLayout() {
  if (!elements.paneGrid) {
    return;
  }
  const count = state.panes.length;
  const layoutKey = paneLayoutKey(count);
  const layout = ensurePaneLayoutState(layoutKey);
  elements.paneGrid.classList.toggle("layout-grid", layoutKey === "grid-2x3");
  elements.paneGrid.style.gridTemplateRows = "";
  if (layoutKey === "grid-2x3") {
    elements.paneGrid.style.gridTemplateRows = trackTemplate(layout.rows);
    applyPaneRowTemplate(
      "grid-2x3-top",
      layout.topCols.slice(0, gridRowPaneCount("grid-2x3-top")),
    );
    applyPaneRowTemplate(
      "grid-2x3-bottom",
      layout.bottomCols.slice(0, gridRowPaneCount("grid-2x3-bottom")),
    );
    return;
  }
  applyPaneRowTemplate(layoutKey, layout.cols);
}

function gridRowPaneCount(rowKey) {
  if (rowKey === "grid-2x3-top") {
    return Math.min(3, state.panes.length);
  }
  if (rowKey === "grid-2x3-bottom") {
    return Math.max(0, state.panes.length - 3);
  }
  return 0;
}

function applyPaneRowTemplate(rowKey, weights) {
  if (!rowKey || !weights.length) {
    return;
  }
  const row = elements.paneGrid?.querySelector(`[data-pane-row-key="${escapeSelectorValue(rowKey)}"]`);
  if (!row) {
    return;
  }
  row.style.gridTemplateColumns = trackTemplate(weights);
}

function updatePaneColumnFromPointer(layoutKey, rowKey, index, clientX) {
  const row = elements.paneGrid?.querySelector(`[data-pane-row-key="${escapeSelectorValue(rowKey)}"]`);
  if (!row) {
    return;
  }
  const weights = rowWeightsForLayout(layoutKey, rowKey);
  const contentWidth = Math.max(
    1,
    (row.getBoundingClientRect?.().width || row.clientWidth || 1) - RESIZER_GUTTER * (weights.length - 1),
  );
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  const before = weights.slice(0, index).reduce((sum, weight) => sum + weight, 0);
  const pairTotal = weights[index] + weights[index + 1];
  const left = row.getBoundingClientRect?.().left || 0;
  const offset = clientX - left - (before / total) * contentWidth;
  const ratio = offset / ((pairTotal / total) * contentWidth || 1);
  const next = adjustTrackPair(weights, index, ratio);
  setRowWeightsForLayout(layoutKey, rowKey, next);
  applyPaneGridLayout();
}

function updatePaneRowFromPointer(layoutKey, index, clientY) {
  if (layoutKey !== "grid-2x3" || !elements.paneGrid) {
    return;
  }
  const weights = state.gridRows || ensurePaneLayoutState(layoutKey).rows;
  const contentHeight = Math.max(
    1,
    (elements.paneGrid.getBoundingClientRect?.().height || elements.paneGrid.clientHeight || 1) -
      RESIZER_GUTTER * (weights.length - 1),
  );
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  const before = weights.slice(0, index).reduce((sum, weight) => sum + weight, 0);
  const pairTotal = weights[index] + weights[index + 1];
  const top = elements.paneGrid.getBoundingClientRect?.().top || 0;
  const offset = clientY - top - (before / total) * contentHeight;
  const ratio = offset / ((pairTotal / total) * contentHeight || 1);
  state.gridRows = adjustTrackPair(weights, index, ratio);
  applyPaneGridLayout();
}

function rowWeightsForLayout(layoutKey, rowKey) {
  if (layoutKey === "grid-2x3") {
    const layout = ensurePaneLayoutState(layoutKey);
    const count = gridRowPaneCount(rowKey);
    if (rowKey === "grid-2x3-top") {
      return (state.gridTopCols || layout.topCols).slice(0, count);
    }
    return (state.gridBottomCols || layout.bottomCols).slice(0, count);
  }
  return state[layoutStateKey(layoutKey)] || ensurePaneLayoutState(layoutKey).cols;
}

function setRowWeightsForLayout(layoutKey, rowKey, weights) {
  if (layoutKey === "grid-2x3") {
    const layout = ensurePaneLayoutState(layoutKey);
    if (rowKey === "grid-2x3-top") {
      const next = [...(state.gridTopCols || layout.topCols)];
      for (let index = 0; index < weights.length; index += 1) {
        next[index] = weights[index];
      }
      state.gridTopCols = next;
      return;
    }
    const next = [...(state.gridBottomCols || layout.bottomCols)];
    for (let index = 0; index < weights.length; index += 1) {
      next[index] = weights[index];
    }
    state.gridBottomCols = next;
    return;
  }
  state[layoutStateKey(layoutKey)] = weights;
}

function updateSplitRatioFromPointer(kind, paneId, element, clientX) {
  const pane = paneById(paneId);
  if (!element || !pane) {
    return;
  }
  const rect = element.getBoundingClientRect?.();
  const ratio = ((clientX - (rect?.left || 0)) / Math.max(1, rect?.width || 1)) * 100;
  const nextRatio = setPaneSplitRatio(pane, kind, ratio, { persist: false });
  applySplitLayout(element, nextRatio);
}

function applySplitLayout(element, ratio) {
  if (!element) {
    return;
  }
  element.style.gridTemplateColumns = splitTemplate(ratio);
}

function splitTemplate(ratio) {
  return trackTemplate([ratio, 100 - ratio]);
}

function onPreviewPointerDown(event) {
  const splitResizer = event.target.closest("[data-resize-split]");
  if (splitResizer) {
    if (!canResizeSplitViews()) {
      return;
    }
    const kind = splitResizer.dataset.resizeSplit;
    const element = splitResizer.closest(
      kind === "json" ? "[data-json-shell]" : "[data-trajectory-shell]",
    );
    beginResize(
      {
        type: "split",
        kind,
        paneId: splitResizer.closest("[data-pane-id]")?.dataset.paneId || state.activePaneId,
        element,
        pointerId: event.pointerId ?? null,
      },
      event,
    );
    return;
  }
  const paneColResizer = event.target.closest("[data-resize-pane-col]");
  if (paneColResizer) {
    if (!canResizePaneLayout()) {
      return;
    }
    beginResize(
      {
        type: "pane-col",
        layoutKey: paneColResizer.dataset.layoutKey,
        rowKey: paneColResizer.dataset.rowKey,
        index: Number(paneColResizer.dataset.resizePaneCol || 0),
        pointerId: event.pointerId ?? null,
      },
      event,
    );
    return;
  }
  const paneRowResizer = event.target.closest("[data-resize-pane-row]");
  if (paneRowResizer) {
    if (!canResizePaneLayout()) {
      return;
    }
    beginResize(
      {
        type: "pane-row",
        layoutKey: paneRowResizer.dataset.layoutKey,
        index: Number(paneRowResizer.dataset.resizePaneRow || 0),
        pointerId: event.pointerId ?? null,
      },
      event,
    );
  }
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

function onTreeKeyDown(event) {
  if (event.key !== "Enter" && event.key !== " " && event.key !== "Spacebar") {
    return;
  }
  const directory = event.target.closest("[data-dir-path]");
  if (!directory) {
    return;
  }
  event.preventDefault();
  toggleDirectory(directory.dataset.dirPath);
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
  if (event.target.closest("[data-resize-split], [data-resize-pane-col], [data-resize-pane-row]")) {
    return;
  }
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

  const annotationSelection = event.target.closest("[data-select-annotation]");
  if (annotationSelection) {
    const annotationPath = annotationSelection.dataset.annotationPath;
    const annotationId = annotationSelection.dataset.selectAnnotation;
    if (annotationPath && annotationId) {
      pane.selectedAnnotationIds[annotationPath] = annotationId;
      if (pane.preview?.kind === "json_inspector") {
        updateJsonInspectorPreview(paneId);
      } else if (pane.preview?.kind === "trajectory") {
        updateTrajectoryPreview(paneId);
      }
    }
    return;
  }

  const annotate = event.target.closest("[data-annotate]");
  if (annotate) {
    const annotations = decodeAnnotationList(annotate.dataset.annotations);
    const annotationId = annotate.dataset.annotationId || null;
    openModal({
      paneId,
      file: pane.path,
      path: annotate.dataset.annotate,
      annotations,
      annotation: annotationId ? annotations.find((entry) => entry.id === annotationId) || null : null,
      annotationId,
    });
    return;
  }

  const stepRow = event.target.closest("[data-step-id]");
  if (stepRow) {
    pane.selectedStepId = stepRow.dataset.stepId;
    updateTrajectoryPreview(paneId);
    return;
  }

  const workbookTab = event.target.closest("[data-sheet-name]");
  if (workbookTab) {
    pane.selectedWorkbookSheetName = workbookTab.dataset.sheetName || null;
    renderWorkspace();
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
    pane.jsonSplitRatio = currentSplitRatio(pane, "json");
    pane.trajectorySplitRatio = currentSplitRatio(pane, "trajectory");
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
    if (pane.preview.kind === "xlsx") {
      initializeWorkbookState(pane);
    } else {
      pane.selectedWorkbookSheetName = null;
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

function initializeWorkbookState(pane) {
  const sheets = pane.preview?.sheets || [];
  if (!sheets.length) {
    pane.selectedWorkbookSheetName = null;
    return;
  }
  const preferred = sheets.find((sheet) => sheet.name === pane.selectedWorkbookSheetName) || sheets[0];
  pane.selectedWorkbookSheetName = preferred.name;
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

function renderXlsxPreview(pane) {
  initializeWorkbookState(pane);
  const preview = pane.preview;
  const sheets = preview.sheets || [];
  const selected = sheets.find((sheet) => sheet.name === pane.selectedWorkbookSheetName) || sheets[0] || null;
  const tabs = sheets.length
    ? `
      <div class="workbook-tabs" aria-label="Workbook sheets">
        ${sheets.map((sheet) => `
          <button
            class="workbook-tab ${sheet.name === selected?.name ? "selected" : ""}"
            type="button"
            aria-pressed="${sheet.name === selected?.name ? "true" : "false"}"
            data-pane-id="${escapeAttribute(pane.id)}"
            data-sheet-name="${escapeAttribute(sheet.name)}"
          >${escapeHtml(sheet.name)}</button>
        `).join("")}
      </div>
    `
    : "";
  const table = selected && selected.columns.length
    ? `
      <div class="table-wrap">
        <table>
          <thead>
            <tr>${selected.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>
          </thead>
          <tbody>
            ${selected.rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}
          </tbody>
        </table>
      </div>
    `
    : `<p class="selection-subtitle">${selected?.empty ? "Empty sheet." : "Empty workbook."}</p>`;
  const truncation = selected
    ? [
        selected.truncated_rows ? "rows truncated" : "",
        selected.truncated_columns ? "columns truncated" : "",
      ].filter(Boolean).join(" · ")
    : "";
  const counts = !selected || selected.empty
    ? "0 rows · 0 columns"
    : `${selected.row_count} rows · ${selected.column_count} columns`;

  return `
    <div class="notebook-stack">
      <div class="preview-card">
        <div class="detail-meta">
          <span class="path-pill">${escapeHtml(preview.path)}</span>
          <span class="badge">${escapeHtml(preview.summary?.title || "Workbook Preview")}</span>
          <span class="badge">${escapeHtml(`${preview.summary?.sheet_count ?? sheets.length} sheets`)}</span>
        </div>
      </div>
      ${tabs}
      <section class="preview-card">
        <div class="detail-meta">
          <span class="badge">${escapeHtml(selected?.name || "Workbook")}</span>
          <span class="badge">${escapeHtml(counts)}</span>
          ${truncation ? `<span class="badge">${escapeHtml(truncation)}</span>` : ""}
        </div>
        <div class="preview-block">${table}</div>
      </section>
    </div>
  `;
}

function renderJsonInspector(pane) {
  const selected = selectedJsonNode(pane);
  if (!selected) {
    return `<div class="notice">Empty JSON payload.</div>`;
  }
  const splitRatio = currentSplitRatio(pane, "json");

  return `
    <div class="split-view" data-json-shell style="grid-template-columns:${escapeAttribute(splitTemplate(splitRatio))}">
      <div class="pane-list" data-json-pane-list>${renderJsonPaneList(pane)}</div>
      <div class="split-resizer" data-resize-split="json" aria-hidden="true"></div>
      <div class="detail-panel" data-json-detail>${renderJsonDetail(selected, pane)}</div>
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
  const nodeAnnotations = normalizeAnnotations(node.annotations, node.annotation);
  const hasAnnotations = nodeAnnotations.length > 0 || (node.annotation_count || 0) > 0;
  const rowClass = hasAnnotations ? "json-tree-row-annotated" : "";
  const marker = hasAnnotations
    ? `<span class="annotation-marker"><span class="annotation-dot"></span><span class="annotation-glyph" aria-hidden="true">✦</span></span>`
    : "";
  const key = node.display_key || node.label;
  const value = node.display_value;
  const icon = renderJsonNodeIcon(node);
  const children = node.children.length && expanded
    ? `<div class="tree-children">${node.children.map((child) => renderJsonNode(child, depth + 1, pane)).join("")}</div>`
    : "";
  return `
    <div class="tree-node ${selected ? "selected" : ""}">
      <div class="tree-row json-tree-row ${rowClass}" data-json-node="${escapeAttribute(node.id)}" data-node-class="${escapeAttribute(node.node_class || "string")}" data-value-type="${escapeAttribute(node.value_type || "string")}" ${rowStyle}>
        ${toggle}
        <span class="tree-label json-tree-label">${marker}${icon}<span class="json-node-key">${escapeHtml(key)}</span>${value ? `<span class="json-node-value json-${escapeAttribute(node.value_type || "string")}">${escapeHtml(value)}</span>` : ""}</span>
        <span class="file-size json-node-badge">${escapeHtml(node.style)}</span>
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

function renderJsonDetail(selected, pane) {
  const annotations = normalizeAnnotations(selected.annotations, selected.annotation);
  const selectedAnnotation = selectedAnnotationEntry(
    pane,
    selected.annotation_path,
    annotations,
  );
  return `
    <h3>${escapeHtml(selected.label)}</h3>
    <div class="detail-meta">
      <span class="path-pill">${escapeHtml(selected.path)}</span>
      <span class="badge">${escapeHtml(selected.type_name)}</span>
      ${selected.annotatable ? renderAnnotationActions(pane, selected.annotation_path, annotations) : ""}
    </div>
    ${renderAnnotationPanel(
      annotations,
      selected.annotatable,
      selectedAnnotation ? selectedAnnotation.id : null,
      pane.id,
      selected.annotation_path,
    )}
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
  detail.innerHTML = renderJsonDetail(selected, pane);
  paneList.scrollTop = paneScroll;
  detail.scrollTop = detailScroll;
}

function renderTrajectoryPreview(pane) {
  const selected = selectedTrajectoryStep(pane);
  const splitRatio = currentSplitRatio(pane, "trajectory");

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
    <div class="split-view" data-trajectory-shell style="grid-template-columns:${escapeAttribute(splitTemplate(splitRatio))}">
      <div class="pane-list" data-trajectory-list>
        ${renderTrajectoryStepList(pane.preview, selected)}
      </div>
      <div class="split-resizer" data-resize-split="trajectory" aria-hidden="true"></div>
      <div class="step-detail" data-trajectory-detail>
        ${renderTrajectoryDetail(pane.preview, selected, pane)}
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

function renderTrajectoryDetail(preview, selected, pane) {
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
      ${(selected.items || []).map((item) => renderTrajectoryItem(item, pane)).join("")}
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
  detail.innerHTML = renderTrajectoryDetail(pane.preview, selected, pane);
  list.scrollTop = listScroll;
  detail.scrollTop = detailScroll;
}

function renderTrajectoryItem(item, pane) {
  if (item.kind === "tool") {
    const annotations = normalizeAnnotations(item.annotations, item.annotation);
    const inputAnnotations = normalizeAnnotations(item.input.annotations, item.input.annotation);
    const outputAnnotations = normalizeAnnotations(item.output.annotations, item.output.annotation);
    const selectedAnnotation = selectedAnnotationEntry(
      pane,
      item.annotation_path,
      annotations,
    );
    const selectedInputAnnotation = selectedAnnotationEntry(
      pane,
      item.input.annotation_path,
      inputAnnotations,
    );
    const selectedOutputAnnotation = selectedAnnotationEntry(
      pane,
      item.output.annotation_path,
      outputAnnotations,
    );
    return `
      <article class="item-card">
        <div class="item-header">
          <div>
            <div class="selection-title">
              ${(annotations.length || (item.annotation_count || 0) > 0) ? `<span class="annotation-dot"></span>` : ""}
              <strong>${escapeHtml(item.title)}</strong>
            </div>
            <div class="item-meta">
              <span class="badge">${escapeHtml(item.tool_name)}</span>
              <span class="badge">${escapeHtml(item.call_id || "")}</span>
              ${item.status ? `<span class="badge">${escapeHtml(item.status)}</span>` : ""}
            </div>
          </div>
          ${renderAnnotationActions(pane, item.annotation_path, annotations)}
        </div>
        ${renderAnnotationPanel(
          annotations,
          true,
          selectedAnnotation ? selectedAnnotation.id : null,
          pane.id,
          item.annotation_path,
        )}
        <div class="subsection-grid">
          <section class="subsection-card">
            <div class="subsection-header">
              <strong>Input</strong>
              ${renderAnnotationActions(pane, item.input.annotation_path, inputAnnotations)}
            </div>
            ${renderAnnotationPanel(
              inputAnnotations,
              true,
              selectedInputAnnotation ? selectedInputAnnotation.id : null,
              pane.id,
              item.input.annotation_path,
            )}
            ${renderRenderValue(item.input.render)}
          </section>
          <section class="subsection-card">
            <div class="subsection-header">
              <strong>Output</strong>
              ${renderAnnotationActions(pane, item.output.annotation_path, outputAnnotations)}
            </div>
            ${renderAnnotationPanel(
              outputAnnotations,
              true,
              selectedOutputAnnotation ? selectedOutputAnnotation.id : null,
              pane.id,
              item.output.annotation_path,
            )}
            ${renderRenderValue(item.output.render)}
          </section>
        </div>
      </article>
    `;
  }

  const annotations = normalizeAnnotations(item.annotations, item.annotation);
  const selectedAnnotation = selectedAnnotationEntry(
    pane,
    item.annotation_path,
    annotations,
  );
  return `
    <article class="item-card">
      <div class="item-header">
        <div>
          <div class="selection-title">
            ${(annotations.length || (item.annotation_count || 0) > 0) ? `<span class="annotation-dot"></span>` : ""}
            <strong>${escapeHtml(item.title)}</strong>
          </div>
          <div class="item-meta">
            <span class="badge">${escapeHtml(item.event_kind || "")}</span>
            ${item.role ? `<span class="badge">${escapeHtml(item.role)}</span>` : ""}
            ${item.status ? `<span class="badge">${escapeHtml(item.status)}</span>` : ""}
            ${item.excerpt ? `<span class="badge">${escapeHtml(item.excerpt)}</span>` : ""}
          </div>
        </div>
        ${renderAnnotationActions(pane, item.annotation_path, annotations)}
      </div>
      ${renderAnnotationPanel(
        annotations,
        true,
        selectedAnnotation ? selectedAnnotation.id : null,
        pane.id,
        item.annotation_path,
      )}
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
  const stateClass = annotation ? "annotate-button-active" : "annotate-button-pending";
  return `<button class="title-button annotate-button ${stateClass}" type="button" data-annotate="${escapeAttribute(path)}" data-annotation="${payload}">${label}</button>`;
}

function renderEditAnnotationButton(path, annotation, annotations) {
  if (!path || !annotation) {
    return "";
  }
  return `<button class="title-button annotate-button annotate-button-active" type="button" data-annotate="${escapeAttribute(path)}" data-annotation-id="${escapeAttribute(annotation.id)}" data-annotations="${escapeAttribute(JSON.stringify(annotations || []))}">Edit annotation</button>`;
}

function renderAnnotationActions(pane, path, annotations) {
  if (!path) {
    return "";
  }
  const selected = selectedAnnotationEntry(pane, path, annotations);
  if (!annotations || !annotations.length) {
    return renderAnnotateButton(path, null);
  }
  return `<div class="annotation-actions">${renderAnnotateButton(path, null)}${renderEditAnnotationButton(path, selected, annotations)}</div>`;
}

function renderAnnotationPanel(annotations, annotatable, selectedAnnotationId = null, paneId = "", annotationPath = "") {
  if (!annotatable) {
    return `<div class="annotation-panel"><div class="selection-subtitle">Annotations unavailable for this node.</div></div>`;
  }
  if (!annotations || !annotations.length) {
    return `<div class="annotation-panel"><div class="selection-subtitle">No annotation yet.</div></div>`;
  }
  const selected = annotations.find((entry) => entry.id === selectedAnnotationId) || annotations[0];
  return `
    <div class="annotation-panel">
      <div class="selection-subtitle">${escapeHtml(`${annotations.length} annotation${annotations.length === 1 ? "" : "s"}`)}</div>
      <div class="annotation-list">
        ${annotations.map((annotation) => `
          <button
            class="annotation-entry ${annotation.id === selected.id ? "selected" : ""}"
            type="button"
            data-select-annotation="${escapeAttribute(annotation.id)}"
            data-annotation-path="${escapeAttribute(annotationPath || "")}"
            data-pane-id="${escapeAttribute(paneId || "")}"
          >
            <span class="annotation-entry-time">${escapeHtml(formatAnnotationTimestamp(annotation.updated_at))}</span>
            <span class="annotation-entry-summary">${escapeHtml(annotation.note || "(empty)")}</span>
          </button>
        `).join("")}
      </div>
      <div class="annotation-tags">
        ${(selected.tags || []).map((tag) => `<span class="annotation-tag">${escapeHtml(tag)}</span>`).join("")}
      </div>
      <div>${escapeHtml(selected.note || "(empty)")}</div>
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
      return renderJsonFallbackBlock(block.value);
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

function renderJsonFallbackBlock(value) {
  return `<pre class="syntax-block json-fallback-block"><code>${renderJsonFallbackValue(value, 0)}</code></pre>`;
}

function renderJsonFallbackValue(value, depth) {
  if (Array.isArray(value)) {
    if (!value.length) {
      return "[]";
    }
    const indent = "  ".repeat(depth);
    const childIndent = "  ".repeat(depth + 1);
    const items = value
      .map((item) => `${childIndent}${renderJsonFallbackValue(item, depth + 1)}`)
      .join(",\n");
    return `[\n${items}\n${indent}]`;
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value);
    if (!entries.length) {
      return "{}";
    }
    const indent = "  ".repeat(depth);
    const childIndent = "  ".repeat(depth + 1);
    const items = entries.map(([key, entryValue]) => (
      `${childIndent}<span class="json-fallback-key">${escapeHtml(JSON.stringify(key))}</span>` +
      `<span class="json-fallback-punctuation">: </span>${renderJsonFallbackValue(entryValue, depth + 1)}`
    )).join(",\n");
    return `{\n${items}\n${indent}}`;
  }
  if (typeof value === "string") {
    return `<span class="json-fallback-string">${escapeHtml(JSON.stringify(value))}</span>`;
  }
  if (typeof value === "number") {
    return `<span class="json-fallback-number">${escapeHtml(String(value))}</span>`;
  }
  if (typeof value === "boolean") {
    return `<span class="json-fallback-boolean">${value ? "true" : "false"}</span>`;
  }
  if (value === null) {
    return `<span class="json-fallback-null">null</span>`;
  }
  return escapeHtml(String(value));
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

function decodeAnnotationList(value) {
  const decoded = decodeAnnotation(value);
  return Array.isArray(decoded) ? decoded : [];
}

function normalizeAnnotations(annotations, annotation) {
  if (Array.isArray(annotations)) {
    return annotations;
  }
  return annotation ? [annotation] : [];
}

function selectedAnnotationEntry(pane, annotationPath, annotations) {
  if (!annotations || !annotations.length) {
    return null;
  }
  if (!pane || !annotationPath) {
    return annotations[0];
  }
  const selectedId = pane.selectedAnnotationIds?.[annotationPath];
  const selected = annotations.find((entry) => entry.id === selectedId) || annotations[0];
  pane.selectedAnnotationIds[annotationPath] = selected.id;
  return selected;
}

function formatAnnotationTimestamp(value) {
  if (!value) {
    return "";
  }
  const normalized = String(value).replace("T", " ").replace("Z", "");
  return normalized.slice(0, 16);
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
  elements.modalDelete?.classList.toggle("hidden", !payload.annotationId);
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
      ...(state.modal.annotationId ? { annotation_id: state.modal.annotationId } : {}),
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
      annotation_id: state.modal.annotationId,
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
    ? state.palette.matches.map((match, index) => (
        renderPaletteRow(match, index, index === state.palette.selectedIndex)
      )).join("")
    : `<div class="preview-block"><div class="selection-subtitle">No matching files.</div></div>`;
}

function renderPaletteRow(match, index, selected) {
  return `
    <button
      class="palette-row ${selected ? "selected" : ""}"
      type="button"
      data-palette-path="${escapeAttribute(match.path)}"
      data-palette-index="${index}"
    >
      <span class="palette-name">${escapeHtml(match.name)}</span>
      <span class="palette-path">${escapeHtml(match.path)}</span>
    </button>
  `;
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

const FILE_NAME_OVERRIDES = {
  "dockerfile": { kind: "dockerfile", group: "config", token: "DK" },
  "makefile": { kind: "makefile", group: "config", token: "MK" },
  "readme": { kind: "readme", group: "docs", token: "RD" },
  "license": { kind: "license", group: "docs", token: "LC" },
  "package.json": { kind: "package_json", group: "config", token: "PK" },
  "package-lock.json": { kind: "lockfile", group: "config", token: "LK" },
  "pnpm-lock.yaml": { kind: "lockfile", group: "config", token: "LK" },
  "yarn.lock": { kind: "lockfile", group: "config", token: "LK" },
  "tsconfig.json": { kind: "tsconfig", group: "config", token: "TS" },
  ".gitignore": { kind: "git", group: "config", token: "GI" },
  ".gitattributes": { kind: "git", group: "config", token: "GI" },
};

const FILE_EXTENSION_MAP = {
  ".py": { kind: "python", group: "code", token: "Py" },
  ".pyi": { kind: "python", group: "code", token: "Py" },
  ".js": { kind: "javascript", group: "code", token: "JS" },
  ".mjs": { kind: "javascript", group: "code", token: "JS" },
  ".cjs": { kind: "javascript", group: "code", token: "JS" },
  ".ts": { kind: "typescript", group: "code", token: "TS" },
  ".tsx": { kind: "react", group: "code", token: "Rx" },
  ".jsx": { kind: "react", group: "code", token: "Rx" },
  ".html": { kind: "html", group: "docs", token: "HT" },
  ".css": { kind: "css", group: "docs", token: "CS" },
  ".scss": { kind: "scss", group: "docs", token: "SC" },
  ".sass": { kind: "scss", group: "docs", token: "SC" },
  ".json": { kind: "json", group: "data", token: "{}" },
  ".jsonl": { kind: "json", group: "data", token: "{}" },
  ".yaml": { kind: "yaml", group: "config", token: "YA" },
  ".yml": { kind: "yaml", group: "config", token: "YA" },
  ".toml": { kind: "toml", group: "config", token: "TO" },
  ".xml": { kind: "xml", group: "config", token: "XM" },
  ".sql": { kind: "sql", group: "data", token: "SQ" },
  ".md": { kind: "markdown", group: "docs", token: "MD" },
  ".txt": { kind: "text", group: "docs", token: "TX" },
  ".sh": { kind: "shell", group: "exec", token: "SH" },
  ".bash": { kind: "shell", group: "exec", token: "SH" },
  ".zsh": { kind: "shell", group: "exec", token: "SH" },
  ".fish": { kind: "shell", group: "exec", token: "SH" },
  ".rs": { kind: "rust", group: "code", token: "Rs" },
  ".go": { kind: "go", group: "code", token: "Go" },
  ".java": { kind: "java", group: "code", token: "Ja" },
  ".kt": { kind: "kotlin", group: "code", token: "Kt" },
  ".swift": { kind: "swift", group: "code", token: "Sw" },
  ".c": { kind: "c", group: "code", token: "C" },
  ".h": { kind: "c", group: "code", token: "C" },
  ".cc": { kind: "cpp", group: "code", token: "C+" },
  ".cpp": { kind: "cpp", group: "code", token: "C+" },
  ".hpp": { kind: "cpp", group: "code", token: "C+" },
  ".rb": { kind: "ruby", group: "code", token: "Rb" },
  ".php": { kind: "php", group: "code", token: "Ph" },
  ".ex": { kind: "elixir", group: "code", token: "Ex" },
  ".exs": { kind: "elixir", group: "code", token: "Ex" },
  ".tf": { kind: "terraform", group: "config", token: "Tf" },
  ".tfvars": { kind: "terraform", group: "config", token: "Tf" },
  ".proto": { kind: "protobuf", group: "config", token: "Pb" },
  ".ipynb": { kind: "notebook", group: "data", token: "NB" },
  ".png": { kind: "image", group: "media", token: "IM" },
  ".jpg": { kind: "image", group: "media", token: "IM" },
  ".jpeg": { kind: "image", group: "media", token: "IM" },
  ".gif": { kind: "image", group: "media", token: "IM" },
  ".svg": { kind: "image", group: "media", token: "IM" },
  ".mp3": { kind: "audio", group: "media", token: "AU" },
  ".wav": { kind: "audio", group: "media", token: "AU" },
  ".mp4": { kind: "video", group: "media", token: "VD" },
  ".mov": { kind: "video", group: "media", token: "VD" },
  ".zip": { kind: "archive", group: "archive", token: "AR" },
  ".tar": { kind: "archive", group: "archive", token: "AR" },
  ".gz": { kind: "archive", group: "archive", token: "AR" },
  ".tgz": { kind: "archive", group: "archive", token: "AR" },
  ".xz": { kind: "archive", group: "archive", token: "AR" },
  ".pdf": { kind: "pdf", group: "docs", token: "PDF" },
  ".csv": { kind: "spreadsheet", group: "data", token: "CV" },
  ".tsv": { kind: "spreadsheet", group: "data", token: "TSV" },
  ".xls": { kind: "spreadsheet", group: "data", token: "XL" },
  ".xlsx": { kind: "spreadsheet", group: "data", token: "XL" },
  ".bin": { kind: "binary", group: "binary", token: "BI" },
  ".exe": { kind: "binary", group: "binary", token: "BI" },
  ".log": { kind: "log", group: "log", token: "LG" },
};

function resolveFileVisual(node) {
  if (node.type === "dir") {
    return { kind: "directory", group: "directory", token: "DIR" };
  }
  const name = (node.name || "").toLowerCase();
  if (name.startsWith(".env")) {
    return { kind: "env", group: "config", token: "EV" };
  }
  if (FILE_NAME_OVERRIDES[name]) {
    return FILE_NAME_OVERRIDES[name];
  }
  const bareReadme = name.replace(/\.[^.]+$/, "");
  if (FILE_NAME_OVERRIDES[bareReadme]) {
    return FILE_NAME_OVERRIDES[bareReadme];
  }
  return FILE_EXTENSION_MAP[node.ext || ""] || { kind: "generic", group: "generic", token: "FI" };
}

function renderFileIcon(visual) {
  return `<span class="file-icon file-icon-${escapeAttribute(visual.kind)}" aria-hidden="true">${escapeHtml(visual.token)}</span>`;
}

const JSON_NODE_ICON_MAP = {
  object: "{}",
  array: "[]",
  string: "S",
  number: "#",
  boolean: "TF",
  null: "∅",
  bundle_summary: "BD",
  submission_summary: "SU",
  transcript_summary: "TR",
  trajectory_metadata: "MD",
  trajectory_final_output: "OUT",
  trajectory_step: "ST",
  trajectory_tool: "TL",
  trajectory_tool_input: "IN",
  trajectory_tool_output: "OU",
  trajectory_event: "EV",
};

function renderJsonNodeIcon(node) {
  const token = JSON_NODE_ICON_MAP[node.node_class] || JSON_NODE_ICON_MAP[node.value_type] || "•";
  return `<span class="json-node-icon json-node-icon-${escapeAttribute(node.node_class || node.value_type || "string")}" aria-hidden="true">${escapeHtml(token)}</span>`;
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
globalThis.initializeWorkbookState = initializeWorkbookState;
globalThis.loadStoredSidebarWidth = loadStoredSidebarWidth;
globalThis.setSidebarWidth = setSidebarWidth;
globalThis.canResizeSidebar = canResizeSidebar;
globalThis.renderPaletteRow = renderPaletteRow;
globalThis.loadStoredPaneLayout = loadStoredPaneLayout;
globalThis.setStoredPaneLayout = setStoredPaneLayout;
globalThis.loadStoredSplitRatio = loadStoredSplitRatio;
globalThis.setStoredSplitRatio = setStoredSplitRatio;
globalThis.trackTemplate = trackTemplate;
globalThis.isStackedLayout = isStackedLayout;
globalThis.canResizePaneLayout = canResizePaneLayout;
globalThis.canResizeSplitViews = canResizeSplitViews;
globalThis.onWorkspaceClick = onWorkspaceClick;
