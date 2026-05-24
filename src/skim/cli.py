"""Console entrypoints for skim."""

from __future__ import annotations

import sys

from . import annotate_cli
from .tui.app import dev
from .tui.app import main as tui_main
from .webui.server import main as web

__all__ = ["dev", "main", "web"]


def main(argv: list[str] | None = None) -> int | None:
    """Dispatch the main ``skim`` command."""
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["annotate"]:
        return annotate_cli.main(args[1:])
    if argv is None:
        tui_main()
        return None

    original_argv = sys.argv
    try:
        sys.argv = [original_argv[0], *argv]
        tui_main()
    finally:
        sys.argv = original_argv
    return None
