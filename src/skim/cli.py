"""Console entrypoints for skim."""

from __future__ import annotations

from .tui.app import dev, main
from .webui.server import main as web

__all__ = ["dev", "main", "web"]
