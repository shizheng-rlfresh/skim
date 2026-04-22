"""Compatibility alias for the web preview serializer module."""

import sys

from .webui import preview_serializer as _preview_serializer

sys.modules[__name__] = _preview_serializer
