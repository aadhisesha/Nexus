"""
parsers/pdf_parser.py — PDF text extraction via PyMuPDF (fitz).

Public API
----------
extract_text(filepath) -> tuple[str, int]
    Returns (full_text, page_count).
    On any error returns ("", 0) — never raises.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def extract_text(filepath: str) -> tuple[str, int]:
    """
    Extract plain text from every page of a PDF.

    Parameters
    ----------
    filepath : str
        Absolute or relative path to the .pdf file.

    Returns
    -------
    (text, page_count) : tuple[str, int]
        *text*       — all pages joined with "\n\n--- Page N ---\n"
        *page_count* — total number of pages in the document
    """
    try:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            log.error("PyMuPDF (fitz) is not installed. Run: pip install pymupdf")
            return "", 0

        try:
            doc = fitz.open(filepath)
        except Exception as exc:
            log.warning("Cannot open PDF '%s' (corrupted or unreadable): %s", filepath, exc)
            return "", 0

        try:
            page_count = len(doc)
            if doc.is_encrypted:
                log.warning("PDF '%s' is encrypted / password-protected — skipping.", filepath)
                doc.close()
                return "", page_count

            parts: list[str] = []
            for i, page in enumerate(doc, start=1):
                try:
                    page_text = page.get_text("text").strip()
                except Exception as exc:
                    log.warning("Error reading page %d of '%s': %s", i, filepath, exc)
                    page_text = ""

                if page_text:
                    parts.append(f"--- Page {i} ---\n{page_text}")

            doc.close()
            full_text = "\n\n".join(parts)

            # Detect scanned PDFs (no text layer)
            raw_content_len = len("".join(parts))
            if page_count > 0 and raw_content_len < 20:
                log.warning(
                    "PDF '%s' (%d pages) has near-empty text layer (%d chars) — likely scanned document.",
                    filepath, page_count, raw_content_len
                )

            return full_text, page_count

        except Exception as exc:
            log.warning("Error processing PDF '%s': %s", filepath, exc)
            try:
                doc.close()
            except Exception:
                pass
            return "", 0

    except Exception as exc:
        log.warning("Unhandled exception in pdf_parser for '%s': %s", filepath, exc)
        return "", 0
