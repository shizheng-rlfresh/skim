"""Public package entrypoint for skim.

This module intentionally stays thin. It re-exports the main app shell, preview
widgets, and trajectory viewer types so callers can continue using simple
`from skim import ...` imports while the implementation lives in focused modules.
"""

from .app import SkimApp, dev, main
from .preview import PreviewPane, SubmissionSummary, render_file
from .trajectory import TrajectoryViewer, normalize_events

__all__ = [
    "PreviewPane",
    "SkimApp",
    "SubmissionSummary",
    "TrajectoryViewer",
    "dev",
    "main",
    "normalize_events",
    "render_file",
]
