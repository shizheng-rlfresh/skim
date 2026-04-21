"""Architecture and compatibility tests for the refactored skim package."""

from __future__ import annotations

import skim
import skim.app as legacy_app
import skim.preview as legacy_preview
import skim.review as legacy_review
import skim.scrolling as legacy_scrolling
import skim.server as legacy_server
import skim.trajectory as legacy_trajectory
import skim.web_preview as legacy_web_preview
from skim import cli
from skim.core import previewing, review
from skim.tui import app, preview, scrolling, trajectory
from skim.webui import preview_serializer, server


def test_cli_module_exposes_console_entrypoints() -> None:
    """The package should provide one CLI wiring surface for all console scripts."""
    assert callable(cli.main)
    assert callable(cli.dev)
    assert callable(cli.web)
    assert skim.main is cli.main
    assert skim.dev is cli.dev


def test_legacy_python_modules_are_thin_compatibility_shims() -> None:
    """Top-level modules should re-export symbols from the new adapter/core packages."""
    assert legacy_app.SkimApp is app.SkimApp
    assert legacy_preview.PreviewPane is preview.PreviewPane
    assert legacy_trajectory.TrajectoryViewer is trajectory.TrajectoryViewer
    assert legacy_review.AnnotationStore is review.AnnotationStore
    assert legacy_scrolling.DirectoryTree is scrolling.DirectoryTree
    assert legacy_server.serve is server.serve
    assert legacy_web_preview.serialize_preview is preview_serializer.serialize_preview


def test_web_static_assets_are_packaged_under_webui_static() -> None:
    """The browser shell assets should live under the packaged web UI adapter."""
    static_dir = server.static_dir()

    assert static_dir.name == "static"
    assert (static_dir / "index.html").is_file()
    assert (static_dir / "styles.css").is_file()
    assert (static_dir / "main.js").is_file()
    assert (static_dir / "state.js").is_file()
    assert (static_dir / "workspace.js").is_file()
    assert (static_dir / "previews.js").is_file()
    assert (static_dir / "fonts" / "JetBrainsMono-Regular.ttf").is_file()


def test_shared_preview_kind_contract_lives_in_core() -> None:
    """Shared file-kind classification should come from the pure core layer."""
    assert previewing.preview_kind_for_path("docs/spec.md") == "markdown"
    assert previewing.preview_kind_for_path("output.json") == "json"
    assert previewing.preview_kind_for_path("notebook.ipynb") == "notebook"
    assert previewing.preview_kind_for_path("table.csv") == "csv"
    assert previewing.preview_kind_for_path("workbook.xlsx") == "xlsx"
    assert previewing.preview_kind_for_path("src/app.py") == "code"
    assert previewing.preview_kind_for_path("README") == "text"
    assert previewing.preview_kind_for_path("artifact.foo") == "other"
    assert review.triage_preview_kind("docs/spec.md") == previewing.preview_kind_for_path(
        "docs/spec.md"
    )
