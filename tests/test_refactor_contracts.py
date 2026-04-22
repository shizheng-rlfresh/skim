"""Architecture and compatibility tests for the refactored skim package."""

from __future__ import annotations

import runpy

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


def test_legacy_review_module_reexports_extension_constants() -> None:
    """Legacy review imports should keep the old extension constant surface."""
    assert legacy_review.MARKDOWN_EXTENSIONS is previewing.MARKDOWN_EXTENSIONS
    assert legacy_review.JSON_EXTENSIONS is previewing.JSON_EXTENSIONS
    assert legacy_review.NOTEBOOK_EXTENSIONS is previewing.NOTEBOOK_EXTENSIONS
    assert legacy_review.CSV_EXTENSIONS is previewing.CSV_EXTENSIONS
    assert legacy_review.XLSX_EXTENSIONS is previewing.XLSX_EXTENSIONS
    assert legacy_review.CODE_EXTENSIONS is previewing.CODE_EXTENSIONS
    assert legacy_review.TEXT_EXTENSIONS is previewing.TEXT_EXTENSIONS


def test_python_m_skim_server_executes_web_entrypoint(monkeypatch) -> None:
    """Running ``python -m skim.server`` should still dispatch to the web entrypoint."""
    called: list[str] = []

    monkeypatch.setattr(server, "main", lambda: called.append("called"))

    runpy.run_module("skim.server", run_name="__main__", alter_sys=True)

    assert called == ["called"]


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
    assert 'aria-label="Search files"' in (static_dir / "index.html").read_text()


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


def test_shared_notebook_detection_rejects_malformed_payloads() -> None:
    """Shared notebook detection should reject partial notebook-shaped JSON."""
    assert not previewing.looks_like_notebook({"cells": []})
    assert not previewing.looks_like_notebook(
        {
            "cells": [{"cell_type": "markdown", "metadata": "bad", "source": ["# Title\n"]}],
            "nbformat": 4,
        }
    )
