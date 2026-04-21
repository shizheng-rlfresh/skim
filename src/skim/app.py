"""Compatibility alias for the Textual app shell module."""

import sys

from .tui import app as _app

sys.modules[__name__] = _app
