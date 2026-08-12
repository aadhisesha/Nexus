"""
parsers/code_parser.py — Source-code file reader with binary detection and AST symbol extraction.

Public API
----------
extract_text(filepath) -> str
    Reads the file as plain UTF-8 text (ignoring decode errors).
    For .py files an AST-derived symbol summary is prepended.
    On any error returns "" — never raises.

Size cap: files larger than MAX_BYTES are truncated to avoid indexing
huge generated or binary-adjacent files.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Files larger than this are read only up to this limit.
MAX_BYTES = 200_000  # 200 KB


def _is_binary_content(raw_head: bytes) -> bool:
    """Detect if raw bytes appear to be binary rather than plain text."""
    if not raw_head:
        return False
    if b"\x00" in raw_head:
        return True
    # Count non-printable control characters (excluding tab, newline, carriage return)
    non_text = sum(1 for byte in raw_head if byte < 9 or (byte > 13 and byte < 32))
    return (non_text / len(raw_head)) > 0.10


def extract_text(filepath: str) -> str:
    """
    Read a source-code file and return its content as plain text.

    Parameters
    ----------
    filepath : str
        Absolute or relative path to the source file.

    Returns
    -------
    str
        File content (possibly truncated), or "" on failure.
    """
    try:
        path = Path(filepath)

        try:
            size = path.stat().st_size
        except OSError as exc:
            log.warning("Cannot stat '%s': %s", filepath, exc)
            return ""

        # Binary check on initial bytes
        try:
            with path.open("rb") as f_bin:
                head = f_bin.read(8192)
                if _is_binary_content(head):
                    log.warning("Code file '%s' contains binary data (misleading extension) — skipping.", filepath)
                    return ""
        except Exception as exc:
            log.warning("Cannot inspect header bytes of '%s': %s", filepath, exc)
            return ""

        # Plain text read with size cap
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as fh:
                source = fh.read(MAX_BYTES)
        except Exception as exc:
            log.warning("Cannot read text from '%s': %s", filepath, exc)
            return ""

        if not source.strip():
            log.warning("Code file '%s' is empty.", filepath)
            return ""

        truncated = size > MAX_BYTES
        parts: list[str] = []

        # --- Python-specific AST symbol summary ----------------------------------
        if path.suffix.lower() == ".py":
            summary = _python_symbol_summary(source, filepath)
            if summary:
                parts.append(summary)

        # --- Raw source ----------------------------------------------------------
        parts.append(source)

        if truncated:
            parts.append(
                f"\n... [truncated — file is {size:,} bytes; "
                f"only first {MAX_BYTES:,} bytes indexed]"
            )

        return "\n".join(parts)

    except Exception as exc:
        log.warning("Unhandled exception in code_parser for '%s': %s", filepath, exc)
        return ""


def _python_symbol_summary(source: str, filepath: str) -> str:
    """
    Parse *source* with the ast module and return a brief symbol inventory.
    Returns an empty string if parsing fails (e.g. syntax errors in the file).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        log.debug("AST parse failed for '%s' (SyntaxError: %s) — skipping symbol summary", filepath, exc)
        return ""
    except Exception as exc:
        log.debug("AST parse failed for '%s': %s — skipping symbol summary", filepath, exc)
        return ""

    classes: list[str] = []
    functions: list[str] = []

    try:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)

        if not classes and not functions:
            return ""

        lines = ["[Python symbols]"]
        if classes:
            lines.append(f"Classes   : {', '.join(classes)}")
        if functions:
            lines.append(f"Functions : {', '.join(functions)}")

        return "\n".join(lines)
    except Exception:
        return ""
