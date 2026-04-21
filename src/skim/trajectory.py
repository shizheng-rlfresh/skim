"""Compatibility alias for the TUI trajectory module."""

import sys

from .tui import trajectory as _trajectory

sys.modules[__name__] = _trajectory
