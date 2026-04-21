"""Compatibility alias for the localhost web server module."""

import sys

from .webui import server as _server

sys.modules[__name__] = _server
