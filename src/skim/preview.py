"""Compatibility alias for the TUI preview module."""

import sys

from .tui import preview as _preview

sys.modules[__name__] = _preview
