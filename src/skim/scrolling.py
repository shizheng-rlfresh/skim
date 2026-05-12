"""Compatibility alias for Textual scrolling helpers."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tui import scrolling as _scrolling

    AnnotationStatusWrap = _scrolling.AnnotationStatusWrap
    DirectoryTree = _scrolling.DirectoryTree
    DragScrollMixin = _scrolling.DragScrollMixin
    DragTree = _scrolling.DragTree
    FocusableDetailWrap = _scrolling.FocusableDetailWrap
else:
    from .tui import scrolling as _scrolling

    sys.modules[__name__] = _scrolling
