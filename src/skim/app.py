"""Application shell and top-level interaction routing for skim.

This module owns the outer browser layout, pane grid, global status bar, split/close
behavior, and app-level keyboard routing. It does not own file preview parsing or
trajectory rendering internals, which live in dedicated modules.
"""

from __future__ import annotations

import subprocess
from collections import OrderedDict
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static, TextArea

from .preview import PreviewPane
from .review import FILE_ANNOTATION_KEY, AnnotationRecord, AnnotationStore
from .scrolling import DirectoryTree
from .trajectory import AnnotationEditorResult, JsonInspector, TrajectoryViewer

MAX_ROWS = 2
MAX_COLS = 3
SCROLL_STEP = 3
PAGE_SCROLL_STEP = 20


class TriageQueue(Static):
    """Focusable triage queue surface."""

    can_focus = True


class TriageDetail(Static):
    """Focusable triage detail surface."""

    can_focus = True


class ReviewAnnotationEditor(ModalScreen[AnnotationEditorResult | None]):
    """Generic file/triage annotation editor modal."""

    BINDINGS = [Binding("escape", "cancel", show=False)]

    def __init__(
        self,
        *,
        heading: str,
        file_path: str,
        target_path: str,
        preview_text: str,
        annotation: AnnotationRecord | None,
        on_submit=None,
    ) -> None:
        """Initialize the modal for one annotation target."""
        super().__init__()
        self.heading = heading
        self.file_path = file_path
        self.target_path = target_path
        self.preview_text = preview_text
        self.annotation = annotation
        self._on_submit = on_submit

    def compose(self) -> ComposeResult:
        """Compose the shared annotation modal."""
        tags = ", ".join(self.annotation.tags) if self.annotation is not None else ""
        note = self.annotation.note if self.annotation is not None else ""
        yield Vertical(
            Horizontal(
                Vertical(
                    Static(self.heading, classes="annotation-modal-title"),
                    Static(f"File: {self.file_path}", classes="annotation-modal-path"),
                    Static(f"Target: {self.target_path}", classes="annotation-modal-path"),
                    Input(value=tags, placeholder="tags, comma, separated", id="annotation-tags"),
                    TextArea(note, id="annotation-note"),
                    Horizontal(
                        Button("Save", id="annotation-save", variant="primary"),
                        Button(
                            "Delete",
                            id="annotation-delete",
                            variant="error",
                            disabled=self.annotation is None,
                        ),
                        Button("Cancel", id="annotation-cancel"),
                        classes="annotation-modal-actions",
                    ),
                    id="annotation-editor-panel",
                    classes="annotation-modal-panel",
                ),
                Vertical(
                    Static("Target Preview", classes="annotation-modal-preview-title"),
                    Static(
                        self.preview_text,
                        id="annotation-preview",
                        classes="annotation-modal-preview",
                    ),
                    id="annotation-preview-panel",
                    classes="annotation-modal-panel",
                ),
                classes="annotation-modal-body",
            ),
            id="annotation-modal",
        )

    def on_mount(self) -> None:
        """Focus the tags field when the modal opens."""
        self.query_one("#annotation-tags", Input).focus()

    def action_cancel(self) -> None:
        """Dismiss the modal without changes."""
        self.dismiss(None)

    def action_save(self) -> None:
        """Dismiss with a save payload."""
        self._submit(
            AnnotationEditorResult(
                action="save",
                annotation_id=self.annotation.id if self.annotation is not None else None,
                tags=_parse_annotation_tags(self.query_one("#annotation-tags", Input).value),
                note=self.query_one("#annotation-note", TextArea).text.rstrip(),
            )
        )

    def action_delete(self) -> None:
        """Dismiss with a delete payload."""
        self._submit(
            AnnotationEditorResult(
                action="delete",
                annotation_id=self.annotation.id if self.annotation is not None else None,
            )
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle modal button clicks."""
        if event.button.id == "annotation-save":
            self.action_save()
        elif event.button.id == "annotation-delete":
            self.action_delete()
        else:
            self.action_cancel()
        event.stop()

    def _submit(self, result: AnnotationEditorResult) -> None:
        """Invoke the save/delete callback before dismissing the modal."""
        if self._on_submit is not None:
            self._on_submit(result)
        self.dismiss(result)


def _parse_annotation_tags(raw_tags: str) -> tuple[str, ...]:
    """Parse the comma-separated tag field used by the modal editor."""
    return tuple(tag.strip() for tag in raw_tags.split(",") if tag.strip())


class SkimApp(App):
    """Main skim application."""

    TITLE = "skim"
    CSS = """
    #app-titlebar {
        dock: top;
        height: 1;
        background: $surface;
        color: $text;
        padding: 0 1;
    }
    #outer {
        height: 1fr;
    }
    #browser-shell, #triage-shell {
        width: 1fr;
        height: 1fr;
    }
    .hidden-view {
        display: none;
    }
    DirectoryTree {
        width: 1fr;
        max-width: 40;
        border-right: solid $primary-background;
    }
    #preview-area {
        width: 3fr;
    }
    .pane-row {
        height: 1fr;
    }
    PreviewPane {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
        border: round $background;
    }
    PreviewPane:focus {
        border: round $accent;
    }
    PreviewPane.active-pane {
        border: round $accent;
    }
    TrajectoryViewer, JsonInspector {
        width: 1fr;
    }
    .trajectory-body {
        height: 1fr;
    }
    .trajectory-tree {
        width: 1fr;
        min-width: 28;
        height: 1fr;
    }
    .trajectory-detail-column {
        width: 2fr;
        height: 1fr;
    }
    .annotation-status-panel {
        width: 1fr;
        height: auto;
        min-height: 8;
        max-height: 1fr;
        border: round $panel-lighten-1;
        background: $surface-lighten-1;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    .trajectory-detail-wrap {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
    }
    .trajectory-detail-field {
        padding: 0 1;
    }
    .trajectory-footer {
        height: 1;
        color: $text-muted;
        background: $surface-lighten-1;
        padding: 0 1;
        margin: 1 0 0 0;
    }
    #annotation-modal {
        width: 140;
        max-width: 96%;
        height: 80%;
        max-height: 90%;
        padding: 1;
        border: round $accent;
        background: $surface;
    }
    .annotation-modal-body {
        height: 1fr;
    }
    .annotation-modal-panel {
        height: 1fr;
        padding: 0 1;
        border: round $panel-lighten-1;
    }
    #annotation-editor-panel {
        width: 2fr;
        margin: 0 1 0 0;
    }
    #annotation-preview-panel {
        width: 3fr;
    }
    .annotation-modal-preview {
        height: 1fr;
        margin: 1 0 0 0;
    }
    .annotation-modal-actions {
        height: auto;
        margin: 1 0 0 0;
    }
    #annotation-tags {
        margin: 1 0 0 0;
    }
    #annotation-note {
        height: 1fr;
        min-height: 8;
        margin: 1 0 0 0;
    }
    Collapsible.trajectory-section {
        margin: 0 0 1 0;
    }
    Collapsible.trajectory-section-selected {
        border: round $accent;
    }
    Collapsible.trajectory-section-secondary {
        border: round $panel-lighten-1;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    .key {
        background: $primary-background;
        color: $text;
        padding: 0 1;
    }
    #triage-shell {
        padding: 0 1;
    }
    #triage-filters {
        width: 28;
        padding: 0 1;
        border-right: solid $primary-background;
    }
    #triage-queue {
        width: 2fr;
        padding: 0 1;
        border-right: solid $primary-background;
    }
    #triage-detail {
        width: 2fr;
        padding: 0 1;
    }
    .triage-panel {
        height: 1fr;
    }
    .triage-label {
        margin: 1 0 0 0;
    }
    .triage-filter-input {
        margin: 0 0 1 0;
    }
    #triage-summary {
        margin: 1 0 0 0;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("q", "quit", show=False),
        Binding("up", "scroll_up", show=False, priority=True),
        Binding("down", "scroll_down", show=False, priority=True),
        Binding("j", "scroll_down", show=False, priority=True),
        Binding("k", "scroll_up", show=False, priority=True),
        Binding("pageup", "page_up", show=False, priority=True),
        Binding("pagedown", "page_down", show=False, priority=True),
        Binding("f", "focus_file_tree", show=False),
        Binding("s", "enter_split", show=False),
        Binding("d", "close_pane", show=False),
        Binding("w", "cycle_pane", show=False),
        Binding("t", "show_triage", show=False),
        Binding("b", "show_browse", show=False),
    ]

    def __init__(self, path: str | Path = ".", *, triage: bool = False):
        """Initialize the app for a directory path."""
        super().__init__()
        self.browse_path = Path(path).expanduser().resolve()
        self.review_store = AnnotationStore(self.browse_path)
        self.pane_counter = 0
        self.active_pane_id: str = ""
        self.grid: list[list[str]] = []
        self.pane_files: dict[str, Path | None] = {}
        self.split_mode = False
        self.file_tree_mode = False
        self.app_mode = "triage" if triage else "browse"
        self.triage_items = []
        self.triage_selected_annotation_id: str | None = None
        self.triage_last_annotation_version = self.review_store.annotation_version

    def _new_pane_id(self) -> str:
        """Return the next stable preview-pane identifier."""
        pid = f"pane-{self.pane_counter}"
        self.pane_counter += 1
        return pid

    def _total_panes(self) -> int:
        """Return the total number of preview panes in the current grid."""
        return sum(len(row) for row in self.grid)

    def _find_pane(self, pane_id: str) -> tuple[int | None, int | None]:
        """Return the row and column for a pane id, if it exists."""
        for row_index, row in enumerate(self.grid):
            for column_index, candidate in enumerate(row):
                if candidate == pane_id:
                    return row_index, column_index
        return None, None

    def compose(self) -> ComposeResult:
        """Compose the directory tree and preview area."""
        yield Static("", id="app-titlebar")
        with Horizontal(id="outer"):
            with Horizontal(id="browser-shell"):
                yield DirectoryTree(str(self.browse_path))
                yield Vertical(id="preview-area")
            with Horizontal(id="triage-shell"):
                with Vertical(id="triage-filters", classes="triage-panel"):
                    yield Static("Search", classes="triage-label")
                    yield Input(
                        placeholder="file, tag, note",
                        id="triage-search",
                        classes="triage-filter-input",
                    )
                    yield Static("Tag", classes="triage-label")
                    yield Input(
                        placeholder="exact tag",
                        id="triage-tag-filter",
                        classes="triage-filter-input",
                    )
                    yield Static("File Type", classes="triage-label")
                    yield Input(
                        placeholder="markdown, json, csv",
                        id="triage-kind-filter",
                        classes="triage-filter-input",
                    )
                    yield Static("", id="triage-summary")
                yield TriageQueue("", id="triage-queue", classes="triage-panel")
                yield TriageDetail("", id="triage-detail", classes="triage-panel")
        yield Static("", id="status-bar")

    def on_mount(self) -> None:
        """Create the first preview pane and start in preview focus mode."""
        pane_id = self._new_pane_id()
        self.grid = [[pane_id]]
        self.pane_files[pane_id] = None
        self.active_pane_id = pane_id
        self._rebuild_layout()
        self._refresh_triage_view(preserve_selection=False)
        self._show_mode(self.app_mode)
        self.set_interval(2, self._poll_annotation_updates, pause=False)
        if self.app_mode == "browse":
            self.exit_file_tree_mode()
        else:
            self.query_one("#triage-queue", TriageQueue).focus()

    def _rebuild_layout(self) -> None:
        """Rebuild the preview pane grid from current state."""
        area = self.query_one("#preview-area")
        area.remove_children()
        for row in self.grid:
            container = Horizontal(classes="pane-row")
            area.mount(container)
            for pane_id in row:
                pane = PreviewPane(id=pane_id)
                container.mount(pane)
                path = self.pane_files.get(pane_id)
                if path:
                    pane.show_file(path)
                else:
                    pane.show_placeholder()
        self._update_active_indicator()

    def _show_mode(self, mode: str) -> None:
        """Show either the browse shell or the triage shell."""
        self.app_mode = mode
        self.split_mode = False
        browser = self.query_one("#browser-shell", Horizontal)
        triage = self.query_one("#triage-shell", Horizontal)
        if mode == "triage":
            browser.add_class("hidden-view")
            triage.remove_class("hidden-view")
            self.file_tree_mode = False
            self.query_one("#triage-queue", TriageQueue).focus(scroll_visible=False)
        else:
            triage.add_class("hidden-view")
            browser.remove_class("hidden-view")
            self.exit_file_tree_mode()
        self._update_titlebar()
        self._update_status_bar()

    def _update_titlebar(self) -> None:
        """Refresh the skim-owned title bar."""
        mode_label = "Triage" if self.app_mode == "triage" else "Browse"
        self.query_one("#app-titlebar", Static).update(f"skim [{mode_label}]")

    def _triage_filters(self) -> tuple[str, str, str]:
        """Return the active triage filter values."""
        return (
            self.query_one("#triage-search", Input).value.strip().lower(),
            self.query_one("#triage-tag-filter", Input).value.strip(),
            self.query_one("#triage-kind-filter", Input).value.strip().lower(),
        )

    def _visible_triage_items(self):
        """Return triage items filtered by the current TUI controls."""
        search, tag, kind = self._triage_filters()
        items = []
        for item in self.review_store.triage_items():
            if tag and tag not in item.tags:
                continue
            if kind and item.preview_kind.lower() != kind:
                continue
            if search:
                haystack = " ".join(
                    filter(
                        None,
                        [
                            item.file_path,
                            item.target_label,
                            item.target_path or "",
                            item.note_preview,
                            item.note_full,
                            *item.tags,
                        ],
                    )
                ).lower()
                if search not in haystack:
                    continue
            items.append(item)
        return items

    def _selected_triage_item(self):
        """Return the selected triage row, defaulting to the first visible item."""
        visible = self._visible_triage_sequence()
        selected = next(
            (item for item in visible if item.annotation_id == self.triage_selected_annotation_id),
            visible[0] if visible else None,
        )
        self.triage_selected_annotation_id = (
            selected.annotation_id if selected is not None else None
        )
        return selected

    def _refresh_triage_view(self, *, preserve_selection: bool = True) -> None:
        """Refresh triage state and repaint the triage panels."""
        previous = self.triage_selected_annotation_id if preserve_selection else None
        self.triage_items = self.review_store.triage_items()
        visible = self._visible_triage_items()
        sequence = self._visible_triage_sequence(visible)
        selected = next(
            (item for item in sequence if item.annotation_id == previous),
            sequence[0] if sequence else None,
        )
        self.triage_selected_annotation_id = (
            selected.annotation_id if selected is not None else None
        )
        self.triage_last_annotation_version = self.review_store.annotation_version
        summary = self.query_one("#triage-summary", Static)
        summary.update(f"{len(visible)} item{'s' if len(visible) != 1 else ''}")
        queue = self.query_one("#triage-queue", TriageQueue)
        queue.update(self._triage_queue_text(visible))
        detail = self.query_one("#triage-detail", TriageDetail)
        detail.update(self._triage_detail_text(selected))

    def _group_triage_items(self, items):
        """Group visible triage items by file while preserving newest-first file order."""
        grouped: OrderedDict[str, list] = OrderedDict()
        for item in items:
            grouped.setdefault(item.file_path, []).append(item)
        return list(grouped.items())

    def _visible_triage_sequence(self, items=None):
        """Return visible triage rows in the same order the grouped queue renders them."""
        visible = self._visible_triage_items() if items is None else items
        sequence = []
        for _, group_items in self._group_triage_items(visible):
            sequence.extend(group_items)
        return sequence

    def _triage_queue_text(self, items) -> str:
        """Return the rendered triage queue text."""
        if not items:
            return "No annotations match the current filters."
        lines: list[str] = []
        grouped_items = self._group_triage_items(items)
        for index, (file_path, group_items) in enumerate(grouped_items):
            latest = group_items[0]
            annotation_count = len(group_items)
            updated = latest.updated_at[:16].replace("T", " ")
            lines.append(
                f"{file_path} [{latest.preview_kind}] {annotation_count} annotation"
                f"{'s' if annotation_count != 1 else ''} · {updated}"
            )
            for item in group_items:
                marker = ">" if item.annotation_id == self.triage_selected_annotation_id else " "
                note_preview = item.note_preview or "(empty)"
                lines.append(f"{marker} {item.target_label or 'File'} :: {note_preview}")
            if index != len(grouped_items) - 1:
                lines.append("")
        return "\n".join(lines)

    def _triage_detail_text(self, item) -> str:
        """Return the rendered triage detail text."""
        if item is None:
            return "No annotation selected."
        tags = ", ".join(item.tags) if item.tags else "(none)"
        return (
            f"File: {item.file_path}\n"
            f"Target: {item.target_label}\n"
            f"Kind: {item.preview_kind}\n"
            f"Tags: {tags}\n"
            f"Created: {item.created_at}\n"
            f"Updated: {item.updated_at}\n\n"
            f"{item.note_full or '(empty)'}"
        )

    def _cycle_triage_focus(self) -> None:
        """Cycle focus among the triage controls."""
        widgets = [
            self.query_one("#triage-search", Input),
            self.query_one("#triage-tag-filter", Input),
            self.query_one("#triage-kind-filter", Input),
            self.query_one("#triage-queue", TriageQueue),
            self.query_one("#triage-detail", TriageDetail),
        ]
        focused = self.focused if self.focused in widgets else widgets[0]
        index = widgets.index(focused) if focused in widgets else 0
        widgets[(index + 1) % len(widgets)].focus(scroll_visible=False)

    def _move_triage_selection(self, delta: int) -> None:
        """Move the triage selection up or down."""
        visible = self._visible_triage_sequence()
        if not visible:
            self.triage_selected_annotation_id = None
            self._refresh_triage_view()
            return
        current = next(
            (
                index
                for index, item in enumerate(visible)
                if item.annotation_id == self.triage_selected_annotation_id
            ),
            0,
        )
        next_index = max(0, min(len(visible) - 1, current + delta))
        self.triage_selected_annotation_id = visible[next_index].annotation_id
        self._refresh_triage_view()

    def _open_triage_item(self) -> None:
        """Open the selected triage item into browse mode."""
        item = self._selected_triage_item()
        if item is None:
            return
        path = self.browse_path / item.file_path
        pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
        pane.show_file(path)
        self.pane_files[self.active_pane_id] = path
        if item.target_kind == "json_path":
            target_path = item.target_path or ""

            def select_target() -> None:
                viewer = pane.active_json_navigator()
                if isinstance(viewer, JsonInspector):
                    viewer.select_annotation_path(target_path)

            pane.call_after_refresh(select_target)
        elif item.target_kind == "file":
            pane.set_selected_file_annotation_id(item.annotation_id)
            pane.show_file(path)
        self._show_mode("browse")
        self.exit_file_tree_mode()

    def _open_review_annotation_editor(
        self,
        *,
        file_path: str,
        target_path: str,
        annotation: AnnotationRecord | None,
        heading: str,
    ) -> None:
        """Open the generic annotation editor modal."""
        preview = f"File: {file_path}\nTarget: {target_path}"
        self.push_screen(
            ReviewAnnotationEditor(
                heading=heading,
                file_path=file_path,
                target_path=target_path,
                preview_text=preview,
                annotation=annotation,
                on_submit=lambda result: self._handle_review_annotation_result(
                    file_path=file_path,
                    target_path=target_path,
                    result=result,
                ),
            )
        )

    def _handle_review_annotation_result(
        self,
        *,
        file_path: str,
        target_path: str,
        result: AnnotationEditorResult | None,
    ) -> None:
        """Persist one generic annotation modal result."""
        if result is None:
            return
        source_path = self.browse_path / file_path
        selected_annotation_id: str | None = None
        if result.action == "delete":
            if result.annotation_id is None:
                return
            self.review_store.delete_annotation(source_path, target_path, result.annotation_id)
        elif result.action == "save":
            if result.annotation_id is None:
                saved = self.review_store.add_annotation(
                    source_path,
                    target_path,
                    tags=result.tags,
                    note=result.note,
                )
                selected_annotation_id = saved.id
            else:
                updated = self.review_store.update_annotation(
                    source_path,
                    target_path,
                    result.annotation_id,
                    tags=result.tags,
                    note=result.note,
                )
                selected_annotation_id = updated.id if updated is not None else result.annotation_id
        self.triage_last_annotation_version = self.review_store.annotation_version
        self._refresh_triage_view()
        try:
            pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
        except Exception:
            pane = None
        active_path = (
            pane.current_path if pane is not None else self.pane_files.get(self.active_pane_id)
        )
        if (
            pane is not None
            and active_path is not None
            and active_path.resolve() == source_path.resolve()
        ):
            self.pane_files[self.active_pane_id] = source_path
            if target_path == FILE_ANNOTATION_KEY:
                updated_annotations = self.review_store.annotations_for_path(
                    source_path,
                    FILE_ANNOTATION_KEY,
                )
                if result.action == "delete":
                    selected_annotation_id = (
                        updated_annotations[0].id if updated_annotations else None
                    )
                pane.set_selected_file_annotation_id(selected_annotation_id)
                pane.file_annotation_mode = bool(updated_annotations)
            pane.show_file(source_path)

    def _edit_selected_triage_item(self) -> None:
        """Edit the currently selected triage item."""
        item = self._selected_triage_item()
        if item is None:
            return
        target = item.target_path or FILE_ANNOTATION_KEY
        annotation = next(
            (
                record
                for record in self.review_store.annotations_for_path(
                    self.browse_path / item.file_path,
                    target,
                )
                if record.id == item.annotation_id
            ),
            None,
        )
        self._open_review_annotation_editor(
            file_path=item.file_path,
            target_path=target,
            annotation=annotation,
            heading="Edit Annotation",
        )

    def _delete_selected_triage_item(self) -> None:
        """Delete the currently selected triage item."""
        item = self._selected_triage_item()
        if item is None:
            return
        self.review_store.delete_annotation(
            self.browse_path / item.file_path,
            item.target_path or FILE_ANNOTATION_KEY,
            item.annotation_id,
        )
        self.triage_last_annotation_version = self.review_store.annotation_version
        self._refresh_triage_view()

    def _open_file_annotation_editor_for_active_pane(self) -> bool:
        """Open a file-level annotation editor for the active non-JSON preview."""
        return self._open_file_annotation_editor_for_active_pane_selection(add_new=False)

    def _active_file_annotation_pane(self) -> PreviewPane | None:
        """Return the active non-JSON preview pane when file annotations are available."""
        try:
            pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
        except Exception:
            return None
        if pane.current_path is None:
            return None
        viewer = pane.active_json_navigator()
        if viewer is not None:
            return None
        return pane

    def _active_file_annotations(
        self, pane: PreviewPane | None = None
    ) -> tuple[AnnotationRecord, ...]:
        """Return file-level annotations for the active non-JSON pane."""
        active_pane = pane or self._active_file_annotation_pane()
        if active_pane is None or active_pane.current_path is None:
            return ()
        return self.review_store.annotations_for_path(active_pane.current_path, FILE_ANNOTATION_KEY)

    def _selected_file_annotation(self, pane: PreviewPane | None = None) -> AnnotationRecord | None:
        """Return the selected file-level annotation for the active non-JSON pane."""
        active_pane = pane or self._active_file_annotation_pane()
        annotations = self._active_file_annotations(active_pane)
        if active_pane is None or not annotations:
            return None
        selected_id = active_pane.selected_file_annotation_id(annotations)
        return next(
            (annotation for annotation in annotations if annotation.id == selected_id),
            annotations[0],
        )

    def _set_file_annotation_mode(self, enabled: bool) -> bool:
        """Enter or leave file-annotation selection mode for the active pane."""
        pane = self._active_file_annotation_pane()
        if pane is None or pane.current_path is None:
            return False
        annotations = self._active_file_annotations(pane)
        if enabled and not annotations:
            return False
        pane.file_annotation_mode = enabled
        pane.show_file(pane.current_path)
        return True

    def _move_file_annotation_selection(self, delta: int) -> bool:
        """Move the selected file-level annotation within the active pane."""
        pane = self._active_file_annotation_pane()
        if pane is None or pane.current_path is None or not pane.file_annotation_mode:
            return False
        annotations = self._active_file_annotations(pane)
        if not annotations:
            pane.file_annotation_mode = False
            pane.show_file(pane.current_path)
            return False
        selected_id = pane.selected_file_annotation_id(annotations)
        current = next(
            (index for index, annotation in enumerate(annotations) if annotation.id == selected_id),
            0,
        )
        next_index = max(0, min(len(annotations) - 1, current + delta))
        pane.set_selected_file_annotation_id(annotations[next_index].id)
        pane.show_file(pane.current_path)
        return True

    def _open_file_annotation_editor_for_active_pane_selection(self, *, add_new: bool) -> bool:
        """Open the file-level annotation editor for the active non-JSON preview."""
        pane = self._active_file_annotation_pane()
        if pane is None or pane.current_path is None:
            return False
        annotation = None if add_new else self._selected_file_annotation(pane)
        self._open_review_annotation_editor(
            file_path=self.review_store.relative_file_path(pane.current_path),
            target_path=FILE_ANNOTATION_KEY,
            annotation=annotation,
            heading="File Annotation",
        )
        return True

    def _poll_annotation_updates(self) -> None:
        """Refresh triage when the annotation version changes."""
        version = self.review_store.annotation_version
        if version == self.triage_last_annotation_version:
            return
        self.triage_last_annotation_version = version
        if self.app_mode == "triage":
            self._refresh_triage_view()

    def set_active_pane(self, pane_id: str) -> None:
        """Set the active preview pane by id."""
        self.active_pane_id = pane_id
        self._update_active_indicator()

    def _update_active_indicator(self) -> None:
        """Refresh which pane is visually marked as active."""
        for pane in self.query(PreviewPane):
            pane.remove_class("active-pane")
        try:
            self.query_one(f"#{self.active_pane_id}", PreviewPane).add_class("active-pane")
        except Exception:
            pass

    def _status_text(self) -> str:
        """Return status-bar text for the current app mode."""
        if self.app_mode == "triage":
            return (
                " [bold]q[/] Quit  "
                "[bold]b[/] Browse  "
                "[bold]↑↓[/] Select  "
                "[bold]/[/] Search  "
                "[bold]Tab[/] Focus  "
                "[bold]Enter[/] Open  "
                "[bold]e[/] Edit  "
                "[bold]x[/] Delete  "
                "[bold]r[/] Refresh"
            )
        if self.file_tree_mode:
            return (
                " [bold]q[/] Quit  "
                "[bold]t[/] Triage  "
                "[bold]↑↓[/] Move  "
                "[bold]←→[/] Branch  "
                "[bold]Esc[/] Back  "
                "[bold]s[/]+arrow Split  "
                "[bold]d[/] Close  "
                "[bold]w[/] Next pane"
            )
        return (
            " [bold]q[/] Quit  "
            "[bold]t[/] Triage  "
            "[bold]↑↓[/] Scroll  "
            "[bold]PgUp/Dn[/] Page  "
            "[bold]f[/] Tree  "
            "[bold]s[/]+arrow Split  "
            "[bold]d[/] Close  "
            "[bold]w[/] Next pane"
        )

    def _update_status_bar(self) -> None:
        """Refresh the global status bar text."""
        self.query_one("#status-bar", Static).update(self._status_text())

    def _modal_is_active(self) -> bool:
        """Return whether a modal screen currently owns keyboard interaction."""
        return isinstance(self.screen, ModalScreen)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Refresh triage when one of its filter inputs changes."""
        if event.input.id in {"triage-search", "triage-tag-filter", "triage-kind-filter"}:
            self._refresh_triage_view()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Disable app-level arrow scrolling while a modal owns focus."""
        if self._modal_is_active() and action in {"scroll_up", "scroll_down"}:
            return False
        return super().check_action(action, parameters)

    def action_quit(self) -> None:
        """Quit the app unless a modal screen is active."""
        if self._modal_is_active():
            return
        self.exit()

    def action_focus_file_tree(self) -> None:
        """Toggle focus between the file tree and the active preview pane."""
        if self._modal_is_active():
            return
        if self.app_mode == "triage":
            return
        if self.file_tree_mode:
            self.exit_file_tree_mode()
            return
        self.file_tree_mode = True
        self.query_one(DirectoryTree).focus(scroll_visible=False)
        self._update_status_bar()

    def action_show_triage(self) -> None:
        """Switch into the triage shell without losing browse pane state."""
        if self._modal_is_active():
            return
        self._refresh_triage_view()
        self._show_mode("triage")

    def action_show_browse(self) -> None:
        """Switch back into the browse shell."""
        if self._modal_is_active():
            return
        self._show_mode("browse")

    def exit_file_tree_mode(self) -> None:
        """Leave file-tree focus mode and return to the active preview pane."""
        if self.app_mode == "triage":
            return
        self.file_tree_mode = False
        self._update_active_indicator()
        try:
            self.query_one(f"#{self.active_pane_id}", PreviewPane).focus(scroll_visible=False)
        except Exception:
            pass
        self._update_status_bar()

    def action_scroll_down(self) -> None:
        """Scroll down in the active pane or confirm a downward split."""
        if self._modal_is_active():
            return
        if self.app_mode == "triage":
            if not isinstance(self.focused, Input):
                self._move_triage_selection(1)
            return
        if self._move_file_annotation_selection(1):
            return
        if self.split_mode:
            self.split_mode = False
            self._split("down")
            return
        if self.file_tree_mode:
            self.action_tree_down()
            return
        try:
            pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
            pane.scroll_content(SCROLL_STEP)
        except Exception:
            pass

    def action_scroll_up(self) -> None:
        """Scroll up in the active pane or confirm an upward split."""
        if self._modal_is_active():
            return
        if self.app_mode == "triage":
            if not isinstance(self.focused, Input):
                self._move_triage_selection(-1)
            return
        if self._move_file_annotation_selection(-1):
            return
        if self.split_mode:
            self.split_mode = False
            self._split("up")
            return
        if self.file_tree_mode:
            self.action_tree_up()
            return
        try:
            pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
            pane.scroll_content(-SCROLL_STEP)
        except Exception:
            pass

    def action_tree_up(self) -> None:
        """Move the directory tree cursor up."""
        if self._modal_is_active():
            return
        self.query_one(DirectoryTree).action_cursor_up()

    def action_tree_down(self) -> None:
        """Move the directory tree cursor down."""
        if self._modal_is_active():
            return
        self.query_one(DirectoryTree).action_cursor_down()

    def action_tree_select(self) -> None:
        """Open the currently selected tree item."""
        if self._modal_is_active():
            return
        self.query_one(DirectoryTree).action_select_cursor()

    def action_tree_left(self) -> None:
        """Collapse the current file-tree branch or move to its parent."""
        if self._modal_is_active():
            return
        tree = self.query_one(DirectoryTree)
        node = tree.cursor_node
        if node is None:
            return
        if node.allow_expand and node.is_expanded:
            node.collapse()
            return
        if node.parent is not None:
            tree.move_cursor(node.parent, animate=False)

    def action_tree_right(self) -> None:
        """Expand the current file-tree branch, move into it, or open a file."""
        if self._modal_is_active():
            return
        tree = self.query_one(DirectoryTree)
        node = tree.cursor_node
        if node is None:
            return
        if node.allow_expand:
            if node.is_collapsed:
                node.expand()
                return
            if node.children:
                tree.move_cursor(node.children[0], animate=False)
            return
        self.action_tree_select()

    def action_page_down(self) -> None:
        """Scroll the active content by a page-sized amount."""
        if self._modal_is_active():
            screen = self.screen
            action = getattr(screen, "action_scroll_preview_down", None)
            if callable(action):
                action()
            return
        if self.app_mode == "triage":
            return
        try:
            pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
            viewer = pane.active_json_navigator()
            if isinstance(viewer, JsonInspector):
                viewer.scroll_detail(PAGE_SCROLL_STEP)
                return
            pane.scroll_relative(y=PAGE_SCROLL_STEP, animate=False)
        except Exception:
            pass

    def action_page_up(self) -> None:
        """Scroll the active content up by a page-sized amount."""
        if self._modal_is_active():
            screen = self.screen
            action = getattr(screen, "action_scroll_preview_up", None)
            if callable(action):
                action()
            return
        if self.app_mode == "triage":
            return
        try:
            pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
            viewer = pane.active_json_navigator()
            if isinstance(viewer, JsonInspector):
                viewer.scroll_detail(-PAGE_SCROLL_STEP)
                return
            pane.scroll_relative(y=-PAGE_SCROLL_STEP, animate=False)
        except Exception:
            pass

    def on_key(self, event: Key) -> None:
        """Handle split-mode keys and tree navigation shortcuts."""
        if self._modal_is_active():
            return

        if self.app_mode == "triage":
            if event.key == "/":
                self.query_one("#triage-search", Input).focus(scroll_visible=False)
                event.prevent_default()
                event.stop()
                return
            if event.key == "tab":
                self._cycle_triage_focus()
                event.prevent_default()
                event.stop()
                return
            if event.key == "escape":
                if isinstance(self.focused, Input):
                    self.query_one("#triage-queue", TriageQueue).focus(scroll_visible=False)
                event.prevent_default()
                event.stop()
                return
            if event.key == "enter":
                self._open_triage_item()
                event.prevent_default()
                event.stop()
                return
            if event.key == "e":
                self._edit_selected_triage_item()
                event.prevent_default()
                event.stop()
                return
            if event.key == "x":
                self._delete_selected_triage_item()
                event.prevent_default()
                event.stop()
                return
            if event.key == "r":
                self._refresh_triage_view()
                event.prevent_default()
                event.stop()
                return

        if self.split_mode:
            direction_map = {
                "left": "left",
                "right": "right",
                "up": "up",
                "down": "down",
                "h": "left",
                "l": "right",
                "k": "up",
                "j": "down",
            }
            direction = direction_map.get(event.key)
            self.split_mode = False
            if direction:
                self._split(direction)
            event.prevent_default()
            event.stop()
            return

        if self.file_tree_mode:
            if event.key in {"up", "k"}:
                self.action_tree_up()
                event.prevent_default()
                event.stop()
                return
            if event.key in {"down", "j"}:
                self.action_tree_down()
                event.prevent_default()
                event.stop()
                return
            if event.key == "left":
                self.action_tree_left()
                event.prevent_default()
                event.stop()
                return
            if event.key == "right":
                self.action_tree_right()
                event.prevent_default()
                event.stop()
                return
            if event.key == "enter":
                self.action_tree_select()
                event.prevent_default()
                event.stop()
                return
            if event.key == "escape":
                self.exit_file_tree_mode()
                event.prevent_default()
                event.stop()
                return

        viewer: JsonInspector | TrajectoryViewer | None = None
        try:
            active_pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
            viewer = active_pane.active_json_navigator()
        except Exception:
            active_pane = None
            viewer = None

        if active_pane is not None and viewer is None:
            file_annotations = self._active_file_annotations(active_pane)
            if event.key == "escape" and active_pane.file_annotation_mode:
                if self._set_file_annotation_mode(False):
                    event.prevent_default()
                    event.stop()
                    return
            if event.key == "enter":
                if active_pane.file_annotation_mode:
                    if self._open_file_annotation_editor_for_active_pane():
                        event.prevent_default()
                        event.stop()
                        return
                elif file_annotations and self._set_file_annotation_mode(True):
                    event.prevent_default()
                    event.stop()
                    return

        if viewer is not None and event.key in {"left", "right"}:
            if viewer.handle_horizontal_key(event.key):
                event.prevent_default()
                event.stop()
                return

        if viewer is not None and event.key == "escape":
            if viewer.handle_escape_key():
                event.prevent_default()
                event.stop()
                return

        if viewer is not None and event.key == "enter":
            if viewer.handle_enter_key():
                event.prevent_default()
                event.stop()
                return

        if isinstance(viewer, JsonInspector) and event.key == "a":
            if viewer.handle_annotation_key():
                event.prevent_default()
                event.stop()
                return
        if event.key == "a" and self._open_file_annotation_editor_for_active_pane_selection(
            add_new=True
        ):
            event.prevent_default()
            event.stop()
            return

        if event.key == "shift+down":
            self.action_tree_down()
            event.prevent_default()
            event.stop()
        elif event.key == "shift+up":
            self.action_tree_up()
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            if self.app_mode == "triage":
                return
            self.action_tree_select()
            event.prevent_default()
            event.stop()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Open a selected file in the active preview pane."""
        path = Path(event.path)
        pane = self.query_one(f"#{self.active_pane_id}", PreviewPane)
        pane.show_file(path)
        self.pane_files[self.active_pane_id] = path
        if self.file_tree_mode:
            self.exit_file_tree_mode()

    def action_enter_split(self) -> None:
        """Enter split mode for the next direction key."""
        if self._modal_is_active():
            return
        if self.app_mode == "triage":
            return
        if self._total_panes() >= MAX_ROWS * MAX_COLS:
            self.notify("Maximum 6 panes reached", severity="warning")
            return
        self.split_mode = True
        self.notify("Split: arrow or h/j/k/l, Esc cancel", timeout=2)

    def _split(self, direction: str) -> None:
        row_index, column_index = self._find_pane(self.active_pane_id)
        if row_index is None or column_index is None:
            return

        new_id = self._new_pane_id()
        self.pane_files[new_id] = None

        if direction in ("left", "right"):
            if len(self.grid[row_index]) < MAX_COLS:
                position = column_index + 1 if direction == "right" else column_index
                self.grid[row_index].insert(position, new_id)
            elif not self._try_overflow(new_id):
                return

        elif direction in ("up", "down"):
            target_row = 0 if direction == "up" else 1
            if target_row >= len(self.grid):
                self.grid.append([])
            if len(self.grid[target_row]) < MAX_COLS:
                insert_at = min(column_index, len(self.grid[target_row]))
                self.grid[target_row].insert(insert_at, new_id)
            elif not self._try_overflow(new_id):
                return

        self.active_pane_id = new_id
        self._rebuild_layout()

    def _try_overflow(self, new_id: str) -> bool:
        """Place a new pane in the first available row/column slot."""
        for row_index in range(MAX_ROWS):
            if row_index < len(self.grid) and len(self.grid[row_index]) < MAX_COLS:
                self.grid[row_index].append(new_id)
                return True
            if row_index >= len(self.grid):
                self.grid.append([new_id])
                return True
        self.notify("No room for new pane", severity="warning")
        return False

    def action_close_pane(self) -> None:
        """Close the active pane unless it is the last one."""
        if self._modal_is_active():
            return
        if self._total_panes() <= 1:
            self.notify("Cannot close last pane", severity="warning")
            return

        row_index, column_index = self._find_pane(self.active_pane_id)
        if row_index is None or column_index is None:
            return

        self.pane_files.pop(self.active_pane_id, None)
        self.grid[row_index].pop(column_index)
        if not self.grid[row_index]:
            self.grid.pop(row_index)

        next_row = min(row_index, len(self.grid) - 1)
        next_column = min(column_index, len(self.grid[next_row]) - 1)
        self.active_pane_id = self.grid[next_row][next_column]
        self._rebuild_layout()
        try:
            self.query_one(f"#{self.active_pane_id}", PreviewPane).focus()
        except Exception:
            pass

    def action_cycle_pane(self) -> None:
        """Cycle the active pane through the current grid order."""
        if self._modal_is_active():
            return
        panes = [pane_id for row in self.grid for pane_id in row]
        if len(panes) <= 1:
            return
        index = panes.index(self.active_pane_id)
        self.active_pane_id = panes[(index + 1) % len(panes)]
        self._update_active_indicator()


def main() -> None:
    """Run the app from the command line."""
    import argparse

    parser = argparse.ArgumentParser(description="skim TUI")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--triage", action="store_true")
    args = parser.parse_args()

    app = SkimApp(args.path, triage=args.triage)
    app.run()


def dev() -> None:
    """Run the app through Textual's dev server."""
    subprocess.run(["textual", "run", "--dev", "skim:SkimApp"], check=False)
