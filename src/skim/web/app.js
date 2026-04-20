const state = {
  tree: null,
  preview: null,
  currentPath: null,
  expandedDirs: new Set(["."]),
  expandedJson: new Set(),
  selectedJsonNodeId: null,
  selectedJsonPath: null,
  selectedStepId: null,
  modal: null,
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
  bindElements();
  bindEvents();
  void bootstrap();
});

function bindElements() {
  elements.browseRoot = document.getElementById("browse-root");
  elements.currentFile = document.getElementById("current-file");
  elements.fileTree = document.getElementById("file-tree");
  elements.previewTitle = document.getElementById("preview-title");
  elements.previewRoot = document.getElementById("preview-root");
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
  elements.fileTree.addEventListener("click", onTreeClick);
  elements.previewRoot.addEventListener("click", onPreviewClick);
  elements.modalClose.addEventListener("click", closeModal);
  elements.modalCancel.addEventListener("click", closeModal);
  elements.modalDelete.addEventListener("click", onDeleteAnnotation);
  elements.modalForm.addEventListener("submit", onSaveAnnotation);
  elements.modal.addEventListener("click", (event) => {
    if (event.target === elements.modal) {
      closeModal();
    }
  });
}

async function bootstrap() {
  try {
    state.tree = await apiJson("/api/tree");
    elements.browseRoot.textContent = state.tree.root_path || state.tree.name;
    render();
  } catch (error) {
    renderFailure(error);
  }
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
  await loadPreview(target.dataset.filePath);
}

async function onPreviewClick(event) {
  const annotate = event.target.closest("[data-annotate]");
  if (annotate) {
    openModal({
      file: state.currentPath,
      path: annotate.dataset.annotate,
      annotation: decodeAnnotation(annotate.dataset.annotation),
    });
    return;
  }

  const stepRow = event.target.closest("[data-step-id]");
  if (stepRow) {
    state.selectedStepId = stepRow.dataset.stepId;
    updateTrajectoryPreview();
    return;
  }

  const jsonToggle = event.target.closest("[data-toggle-json]");
  if (jsonToggle) {
    const node = jsonNodeByPath(jsonToggle.dataset.toggleJson);
    if (node) {
      toggleJsonNode(node);
    }
    return;
  }

  const jsonNode = event.target.closest("[data-json-node]");
  if (jsonNode) {
    const node = jsonNodeById(jsonNode.dataset.jsonNode);
    if (node) {
      selectJsonNode(node);
      if (node.children.length) {
        toggleJsonNode(node, { preserveSelection: true });
        return;
      }
      updateJsonInspectorPreview();
    }
    return;
  }
}

async function onSaveAnnotation(event) {
  event.preventDefault();
  if (!state.modal) {
    return;
  }
  const tags = elements.modalTags.value
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
      note: elements.modalNote.value,
    }),
  });
  const selectedJsonPath = state.selectedJsonPath;
  const selectedStepId = state.selectedStepId;
  closeModal();
  await loadPreview(state.currentPath, { selectedJsonPath, selectedStepId });
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
  const selectedJsonPath = state.selectedJsonPath;
  const selectedStepId = state.selectedStepId;
  closeModal();
  await loadPreview(state.currentPath, { selectedJsonPath, selectedStepId });
}

async function loadPreview(path, options = {}) {
  try {
    state.preview = await apiJson(`/api/preview?path=${encodeURIComponent(path)}`);
    state.currentPath = path;
    elements.currentFile.textContent = path;
    if (state.preview.kind === "json_inspector") {
      initializeJsonState(options.selectedJsonPath);
    } else {
      state.selectedJsonNodeId = null;
      state.selectedJsonPath = null;
    }
    if (state.preview.kind === "trajectory") {
      state.selectedStepId = options.selectedStepId || state.preview.initial_step_id;
    } else {
      state.selectedStepId = null;
    }
    render();
  } catch (error) {
    renderFailure(error);
  }
}

function initializeJsonState(selectedJsonPath = null) {
  const nodes = flattenNodes(state.preview.tree);
  const defaultExpanded = nodes
    .filter((node) => node.children.length > 0 && node.raw_path.length <= 1)
    .map((node) => node.path);
  state.expandedJson = new Set(defaultExpanded);
  const preferred =
    nodes.find((node) => node.path === selectedJsonPath) ||
    nodes.find((node) => node.id === state.preview.initial_node_id) ||
    nodes[0] ||
    null;
  state.selectedJsonNodeId = preferred ? preferred.id : null;
  state.selectedJsonPath = preferred ? preferred.path : null;
}

function openModal(payload) {
  state.modal = payload;
  elements.modalFile.textContent = payload.file;
  elements.modalPath.textContent = payload.path;
  elements.modalTags.value = payload.annotation ? payload.annotation.tags.join(", ") : "";
  elements.modalNote.value = payload.annotation ? payload.annotation.note : "";
  elements.modalDelete.classList.toggle("hidden", !payload.annotation);
  elements.modal.classList.remove("hidden");
  elements.modalTags.focus();
}

function closeModal() {
  state.modal = null;
  elements.modal.classList.add("hidden");
}

function render() {
  renderTree();
  renderPreview();
}

function renderTree() {
  if (!state.tree) {
    elements.fileTree.innerHTML = "";
    return;
  }
  const children = state.tree.children || [];
  elements.fileTree.innerHTML = children
    .map((child) => renderTreeNode(child, 0))
    .join("");
}

function renderTreeNode(node, depth) {
  const isDir = node.type === "dir";
  const expanded = state.expandedDirs.has(node.path);
  const selected = state.currentPath === node.path;
  const indent = `style="padding-left:${14 + depth * 16}px"`;
  const toggle = isDir
    ? `<button class="tree-toggle" type="button" data-toggle-dir="${escapeAttribute(node.path)}">${expanded ? "▾" : "▸"}</button>`
    : `<span></span>`;
  const size = isDir ? "" : `<span class="file-size">${escapeHtml(node.size || "")}</span>`;
  const labelAttrs = isDir
    ? ` data-dir-path="${escapeAttribute(node.path)}"`
    : ` data-file-path="${escapeAttribute(node.path)}"`;
  const rowClass = selected ? "tree-node selected" : "tree-node";
  const children = isDir && expanded
    ? `<div class="tree-children">${(node.children || []).map((child) => renderTreeNode(child, depth + 1)).join("")}</div>`
    : "";

  return `
    <div class="${rowClass}">
      <div class="tree-row" ${indent}${labelAttrs}>
        ${toggle}
        <span class="tree-label">${escapeHtml(node.name)}</span>
        ${size}
      </div>
      ${children}
    </div>
  `;
}

function renderPreview() {
  if (!state.preview) {
    elements.previewTitle.textContent = "Preview";
    elements.previewRoot.innerHTML = `
      <div class="empty-state">
        <div class="empty-mark">◇</div>
        <p>Select a file to inspect it.</p>
      </div>
    `;
    return;
  }

  elements.previewTitle.textContent = `${state.preview.name} · ${state.preview.kind}`;

  switch (state.preview.kind) {
    case "text":
      elements.previewRoot.innerHTML = renderTextPreview(state.preview);
      return;
    case "markdown":
      elements.previewRoot.innerHTML = renderMarkdownPreview(state.preview);
      return;
    case "csv":
      elements.previewRoot.innerHTML = renderCsvPreview(state.preview);
      return;
    case "json_inspector":
      elements.previewRoot.innerHTML = renderJsonInspector(state.preview);
      return;
    case "trajectory":
      elements.previewRoot.innerHTML = renderTrajectoryPreview(state.preview);
      return;
    case "too_large":
    case "error":
      elements.previewRoot.innerHTML = `<div class="notice">${escapeHtml(state.preview.message)}</div>`;
      return;
    default:
      elements.previewRoot.innerHTML = `<div class="notice">Unsupported preview kind: ${escapeHtml(state.preview.kind)}</div>`;
  }
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
      <table>
        <thead>
          <tr>${preview.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${preview.rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}
        </tbody>
      </table>
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

function renderJsonInspector(preview) {
  const selected = selectedJsonNode(preview);
  if (!selected) {
    return `<div class="notice">Empty JSON payload.</div>`;
  }

  return `
    <div class="split-view" data-json-shell>
      <div class="pane-list" data-json-pane-list>${renderJsonPaneList(preview)}</div>
      <div class="detail-panel" data-json-detail>
        ${renderJsonDetail(selected)}
      </div>
    </div>
  `;
}

function renderJsonNode(node, depth) {
  const expanded = state.expandedJson.has(node.path);
  const selected = node.id === state.selectedJsonNodeId;
  const rowStyle = `style="padding-left:${18 + depth * 16}px"`;
  const toggle = node.children.length
    ? `<button class="tree-toggle" type="button" data-toggle-json="${escapeAttribute(node.path)}">${expanded ? "▾" : "▸"}</button>`
    : `<span></span>`;
  const marker = node.annotation ? `<span class="annotation-dot"></span>` : "";
  const children = node.children.length && expanded
    ? `<div class="tree-children">${node.children.map((child) => renderJsonNode(child, depth + 1)).join("")}</div>`
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

function renderTrajectoryPreview(preview) {
  const selected = selectedTrajectoryStep(preview);

  if (!selected) {
    return `
      <div class="preview-card">
        <div class="detail-meta">
          <span class="badge">${escapeHtml(preview.header)}</span>
        </div>
        <p class="selection-subtitle">No trajectory steps available.</p>
      </div>
    `;
  }

  return `
    <div class="split-view" data-trajectory-shell>
      <div class="pane-list" data-trajectory-list>
        ${renderTrajectoryStepList(preview, selected)}
      </div>
      <div class="step-detail" data-trajectory-detail>
        ${renderTrajectoryDetail(preview, selected)}
      </div>
    </div>
  `;
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

function renderAnnotateButton(path, annotation) {
  if (!path) {
    return "";
  }
  const payload = annotation ? escapeAttribute(JSON.stringify(annotation)) : "";
  const label = annotation ? "Edit annotation" : "Annotate";
  return `<button class="ghost-button" type="button" data-annotate="${escapeAttribute(path)}" data-annotation="${payload}">${label}</button>`;
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
        <div class="preview-block detail-fields">
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
      const sectionClass = block.secondary ? "detail-section secondary" : "detail-section";
      const body = (block.blocks || []).map(renderDetailBlock).join("");
      return `
        <details class="${sectionClass}"${open}>
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
  return `
    <pre class="code-block" data-language="${escapeAttribute(language || "text")}"><code>${escapeHtml(value || "")}</code></pre>
  `;
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

function toggleDirectory(path) {
  if (state.expandedDirs.has(path)) {
    state.expandedDirs.delete(path);
  } else {
    state.expandedDirs.add(path);
  }
  renderTree();
}

function selectedJsonNode(preview = state.preview) {
  const nodes = flattenNodes(preview?.tree || []);
  const selected =
    nodes.find((node) => node.id === state.selectedJsonNodeId) ||
    nodes.find((node) => node.id === preview?.initial_node_id) ||
    nodes[0] ||
    null;
  if (selected) {
    state.selectedJsonNodeId = selected.id;
    state.selectedJsonPath = selected.path;
  }
  return selected;
}

function jsonNodeById(nodeId) {
  return flattenNodes(state.preview?.tree || []).find((node) => node.id === nodeId) || null;
}

function jsonNodeByPath(path) {
  return flattenNodes(state.preview?.tree || []).find((node) => node.path === path) || null;
}

function selectJsonNode(node) {
  state.selectedJsonNodeId = node.id;
  state.selectedJsonPath = node.path;
}

function toggleJsonNode(node, options = {}) {
  if (state.expandedJson.has(node.path)) {
    state.expandedJson.delete(node.path);
  } else {
    state.expandedJson.add(node.path);
  }
  if (!options.preserveSelection) {
    selectJsonNode(node);
  }
  updateJsonInspectorPreview();
}

function renderJsonPaneList(preview) {
  return preview.tree.map((node) => renderJsonNode(node, 0)).join("");
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

function updateJsonInspectorPreview() {
  if (!state.preview || state.preview.kind !== "json_inspector") {
    renderPreview();
    return;
  }
  if (!elements.previewRoot) {
    renderPreview();
    return;
  }
  const shell = elements.previewRoot.querySelector("[data-json-shell]");
  if (!shell) {
    renderPreview();
    return;
  }
  const selected = selectedJsonNode(state.preview);
  if (!selected) {
    renderPreview();
    return;
  }
  const paneList = shell.querySelector("[data-json-pane-list]");
  const detail = shell.querySelector("[data-json-detail]");
  if (!paneList || !detail) {
    renderPreview();
    return;
  }
  const paneScroll = paneList.scrollTop;
  const detailScroll = detail.scrollTop;
  paneList.innerHTML = renderJsonPaneList(state.preview);
  detail.innerHTML = renderJsonDetail(selected);
  paneList.scrollTop = paneScroll;
  detail.scrollTop = detailScroll;
}

function selectedTrajectoryStep(preview = state.preview) {
  const selected =
    preview?.steps?.find((step) => step.id === state.selectedStepId) ||
    preview?.steps?.find((step) => step.id === preview.initial_step_id) ||
    preview?.steps?.[0] ||
    null;
  if (selected) {
    state.selectedStepId = selected.id;
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
      ${preview.metadata_lines.map((line) => `<span class="path-pill">${escapeHtml(line)}</span>`).join("")}
    </div>
    <div class="preview-card">
      <h3>Final Output</h3>
      ${renderRenderValue(preview.final_output)}
    </div>
    <div class="preview-card">
      <h3>${escapeHtml(selected.title)}</h3>
      <div class="selection-subtitle">${escapeHtml(selected.path)}</div>
      ${selected.items.map(renderTrajectoryItem).join("")}
    </div>
  `;
}

function updateTrajectoryPreview() {
  if (!state.preview || state.preview.kind !== "trajectory") {
    renderPreview();
    return;
  }
  if (!elements.previewRoot) {
    renderPreview();
    return;
  }
  const shell = elements.previewRoot.querySelector("[data-trajectory-shell]");
  if (!shell) {
    renderPreview();
    return;
  }
  const selected = selectedTrajectoryStep(state.preview);
  if (!selected) {
    renderPreview();
    return;
  }
  const list = shell.querySelector("[data-trajectory-list]");
  const detail = shell.querySelector("[data-trajectory-detail]");
  if (!list || !detail) {
    renderPreview();
    return;
  }
  const listScroll = list.scrollTop;
  const detailScroll = detail.scrollTop;
  list.innerHTML = renderTrajectoryStepList(state.preview, selected);
  detail.innerHTML = renderTrajectoryDetail(state.preview, selected);
  list.scrollTop = listScroll;
  detail.scrollTop = detailScroll;
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

function renderFailure(error) {
  elements.previewTitle.textContent = "Preview";
  elements.previewRoot.innerHTML = `<div class="notice">${escapeHtml(error.message || String(error))}</div>`;
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
