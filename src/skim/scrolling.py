"""Compatibility alias for Textual scrolling helpers."""

import sys

from .tui import scrolling as _scrolling

sys.modules[__name__] = _scrolling
