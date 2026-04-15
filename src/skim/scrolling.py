"""Scroll and mouse-interaction helpers for skim.

This module owns reusable scrollable widget behavior, especially the drag-to-scroll
support used by panes and trees. It does not know about preview routing or trajectory
semantics; higher-level modules compose these widgets into the app.
"""

from __future__ import annotations

from typing import Any

from textual import events
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import DirectoryTree as TextualDirectoryTree
from textual.widgets import Tree as TextualTree

DRAG_SCROLL_THRESHOLD = 2


class DragScrollMixin:
    """Add thresholded click-and-drag vertical scrolling to a scrollable widget."""

    _drag_scroll_start_y: float | None
    _drag_scroll_origin_y: int | None
    _drag_scrolling: bool

    def _init_drag_scroll(self) -> None:
        """Initialize internal drag-scroll state."""
        self._drag_scroll_start_y = None
        self._drag_scroll_origin_y = None
        self._drag_scrolling = False

    def _drag_scroll_requires_self_target(self) -> bool:
        """Return whether drag-scrolling should only start from the container itself."""
        return False

    def _can_start_drag_scroll(self, event: events.MouseDown) -> bool:
        """Return whether a drag-scroll gesture should start for this event."""
        if event.button != 1 or self.max_scroll_y <= 0:  # type: ignore[attr-defined]
            return False
        if self._drag_scroll_requires_self_target() and event.widget is not self:
            return False
        return True

    async def on_mouse_down(self, event: events.MouseDown) -> None:
        """Capture mouse input so a vertical drag can scroll the widget."""
        if not self._can_start_drag_scroll(event):
            return
        self._drag_scroll_start_y = self.scroll_y  # type: ignore[attr-defined]
        self._drag_scroll_origin_y = event.screen_y
        self._drag_scrolling = False
        self.capture_mouse()  # type: ignore[attr-defined]

    async def on_mouse_move(self, event: events.MouseMove) -> None:
        """Translate vertical mouse movement into vertical scrolling."""
        if self.app.mouse_captured is not self or self._drag_scroll_origin_y is None:
            return
        delta = event.screen_y - self._drag_scroll_origin_y
        if not self._drag_scrolling and abs(delta) < DRAG_SCROLL_THRESHOLD:
            return
        self._drag_scrolling = True
        start_y = self._drag_scroll_start_y or 0
        self.scroll_to(  # type: ignore[attr-defined]
            y=start_y - delta,
            animate=False,
            force=True,
            immediate=True,
        )
        event.stop()

    async def on_mouse_up(self, event: events.MouseUp) -> None:
        """Release captured drag-scroll state."""
        if self.app.mouse_captured is self:
            self.release_mouse()  # type: ignore[attr-defined]
        if self._drag_scrolling:
            event.stop()
        self._drag_scroll_start_y = None
        self._drag_scroll_origin_y = None
        self._drag_scrolling = False

    def on_hide(self) -> None:
        """Release mouse capture if the widget hides mid-drag."""
        if self.app.mouse_captured is self:
            self.release_mouse()  # type: ignore[attr-defined]
        self._drag_scroll_start_y = None
        self._drag_scroll_origin_y = None
        self._drag_scrolling = False


class DirectoryTree(DragScrollMixin, TextualDirectoryTree):
    """Directory tree with drag-to-scroll support."""

    def __init__(self, path: str, **kwargs: Any) -> None:
        """Initialize the directory tree."""
        super().__init__(path, **kwargs)
        self._init_drag_scroll()


class DragTree(DragScrollMixin, TextualTree[Any]):
    """Generic tree widget with drag-to-scroll support."""

    def __init__(self, label: str, **kwargs: Any) -> None:
        """Initialize the drag-scroll tree."""
        super().__init__(label, **kwargs)
        self._init_drag_scroll()


class FocusableDetailWrap(DragScrollMixin, VerticalScroll, can_focus=True):
    """Focusable scroll container for trajectory detail rendering."""

    def __init__(self, *children: Widget, **kwargs: Any) -> None:
        """Initialize the detail wrapper."""
        super().__init__(*children, **kwargs)
        self._init_drag_scroll()

    def _drag_scroll_requires_self_target(self) -> bool:
        """Only start drag-scroll from the detail container background."""
        return True
