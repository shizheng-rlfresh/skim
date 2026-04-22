"""Public package entrypoint for skim."""

from . import cli
from .cli import dev, main
from .tui.app import SkimApp
from .tui.preview import PreviewPane, render_file
from .tui.trajectory import JsonInspector, TrajectoryViewer, normalize_events

__all__ = [
    "JsonInspector",
    "PreviewPane",
    "SkimApp",
    "TrajectoryViewer",
    "cli",
    "dev",
    "main",
    "normalize_events",
    "render_file",
]
