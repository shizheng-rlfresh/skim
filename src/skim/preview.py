"""Compatibility alias for the TUI preview module."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tui import preview as _preview

    JSON_EXTENSIONS = _preview.JSON_EXTENSIONS
    MARKDOWN_EXTENSIONS = _preview.MARKDOWN_EXTENSIONS
    MAX_CSV_CELL_WIDTH = _preview.MAX_CSV_CELL_WIDTH
    MAX_CSV_COLS = _preview.MAX_CSV_COLS
    MAX_CSV_ROWS = _preview.MAX_CSV_ROWS
    MAX_FILE_SIZE = _preview.MAX_FILE_SIZE
    MAX_JSON_FILE_SIZE = _preview.MAX_JSON_FILE_SIZE
    NOTEBOOK_EXTENSIONS = _preview.NOTEBOOK_EXTENSIONS
    SYNTAX_MAP = _preview.SYNTAX_MAP
    XLSX_EXTENSIONS = _preview.XLSX_EXTENSIONS
    CsvPreview = _preview.CsvPreview
    FileAnnotationStatus = _preview.FileAnnotationStatus
    PreviewPane = _preview.PreviewPane
    XlsxPreview = _preview.XlsxPreview
    XlsxPreviewData = _preview.XlsxPreviewData
    XlsxSheetPreviewData = _preview.XlsxSheetPreviewData
    _xlsx_sheet_preview_data = _preview._xlsx_sheet_preview_data
    render_file = _preview.render_file
else:
    from .tui import preview as _preview

    sys.modules[__name__] = _preview
