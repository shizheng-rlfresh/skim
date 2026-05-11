"""Compatibility alias for the web preview serializer module."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .webui import preview_serializer as _preview_serializer

    serialize_json_inspector_preview = _preview_serializer.serialize_json_inspector_preview
    serialize_preview = _preview_serializer.serialize_preview
else:
    from .webui import preview_serializer as _preview_serializer

    sys.modules[__name__] = _preview_serializer
