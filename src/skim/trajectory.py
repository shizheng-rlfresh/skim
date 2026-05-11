"""Compatibility alias for the TUI trajectory module."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tui import trajectory as _trajectory

    AnnotationEditor = _trajectory.AnnotationEditor
    AnnotationEditorResult = _trajectory.AnnotationEditorResult
    AnnotationStore = _trajectory.AnnotationStore
    JsonInspector = _trajectory.JsonInspector
    JsonInspectorItem = _trajectory.JsonInspectorItem
    StepTimelineItem = _trajectory.StepTimelineItem
    TrajectoryEvent = _trajectory.TrajectoryEvent
    TrajectoryTreeItem = _trajectory.TrajectoryTreeItem
    TrajectoryViewer = _trajectory.TrajectoryViewer
    extract_trajectory = _trajectory.extract_trajectory
    normalize_events = _trajectory.normalize_events
    normalize_step_events = _trajectory.normalize_step_events
    normalize_step_overlay = _trajectory.normalize_step_overlay
    normalize_step_timeline = _trajectory.normalize_step_timeline
else:
    from .tui import trajectory as _trajectory

    sys.modules[__name__] = _trajectory
