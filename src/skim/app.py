"""Compatibility alias for the Textual app shell module."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tui import app as _app

    ReviewAnnotationEditor = _app.ReviewAnnotationEditor
    SkimApp = _app.SkimApp
    TriageDetail = _app.TriageDetail
    TriageQueue = _app.TriageQueue
    dev = _app.dev
    main = _app.main
else:
    from .tui import app as _app

    sys.modules[__name__] = _app
