"""
parsers/__init__.py — Unified parser dispatch for Nexus.

Public API
----------
extract_text_by_type(filepath, file_type) -> str
    Route *filepath* to the correct parser based on *file_type* label
    (as defined in config.SUPPORTED_EXTENSIONS) and return the extracted
    plain text.  Returns "" on any failure — never raises.

Note: pdf_parser returns (text, page_count).  This dispatcher unwraps
the tuple so callers always receive a plain str regardless of file type.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Mapping from file_type label → parser module import path.
# Intentionally lazy-imported inside the function to avoid loading every
# library (fitz, PIL, etc.) at startup.
_PARSER_MAP: dict[str, str] = {
    "pdf":   "parsers.pdf_parser",
    "docx":  "parsers.docx_parser",
    "xlsx":  "parsers.xlsx_parser",
    "pptx":  "parsers.pptx_parser",
    "image": "parsers.image_parser",
    "code":  "parsers.code_parser",
}


def extract_text_by_type(filepath: str, file_type: str) -> str:
    """
    Extract plain text from *filepath* using the parser for *file_type*.

    Parameters
    ----------
    filepath : str
        Absolute or relative path to the file.
    file_type : str
        One of: "pdf", "docx", "xlsx", "pptx", "image", "code".

    Returns
    -------
    str
        Extracted text, or "" if the file type is unsupported or an
        error occurs during extraction.
    """
    module_path = _PARSER_MAP.get(file_type)
    if module_path is None:
        log.warning("No parser registered for file_type '%s' (file: %s)", file_type, filepath)
        return ""

    try:
        import importlib
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        log.error("Cannot import parser module '%s': %s", module_path, exc)
        return ""

    try:
        result = mod.extract_text(filepath)
    except Exception as exc:
        # Parsers are expected to catch internally — this is a last-resort safety net.
        log.error("Unexpected error in parser '%s' for '%s': %s", module_path, filepath, exc)
        return ""

    # pdf_parser returns (text, page_count) — unwrap if needed.
    if isinstance(result, tuple):
        return result[0]

    return result or ""
