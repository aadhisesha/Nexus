"""
parsers/xlsx_parser.py — Excel spreadsheet extraction via openpyxl.

Public API
----------
extract_text(filepath) -> str
    Returns a human-readable text representation of every sheet:
      sheet name → column headers → first SAMPLE_ROWS data rows.
    On any error returns "" — never raises.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Maximum data rows to sample per sheet to avoid huge text sizes
SAMPLE_ROWS = 200


def extract_text(filepath: str) -> str:
    """
    Extract a textual summary of an Excel workbook.

    Parameters
    ----------
    filepath : str
        Absolute or relative path to the .xlsx file.

    Returns
    -------
    str
        Multi-sheet text summary, or "" on failure.
    """
    try:
        try:
            import openpyxl
        except ImportError:
            log.error("openpyxl is not installed. Run: pip install openpyxl")
            return ""

        try:
            wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        except Exception as exc:
            log.warning("Cannot open XLSX '%s' (corrupted, password-protected, or invalid): %s", filepath, exc)
            return ""

        sheet_parts: list[str] = []

        try:
            sheet_names = wb.sheetnames
        except Exception as exc:
            log.warning("Cannot read sheet names in XLSX '%s': %s", filepath, exc)
            sheet_names = []

        for sheet_name in sheet_names:
            try:
                ws = wb[sheet_name]
                # Cap reading at SAMPLE_ROWS + 1 (header + data rows) to avoid loading huge sheets into memory
                rows_iter = ws.iter_rows(max_row=SAMPLE_ROWS + 5, values_only=True)
                rows = []
                for idx, row in enumerate(rows_iter):
                    rows.append(row)
                    if idx >= SAMPLE_ROWS + 1:
                        break
            except Exception as exc:
                log.warning("Error reading sheet '%s' in '%s': %s", sheet_name, filepath, exc)
                continue

            if not rows:
                sheet_parts.append(f"=== Sheet: {sheet_name} ===\n(empty sheet)")
                continue

            # First row → headers
            header_row = rows[0] if rows else ()
            headers = [str(h).strip() if h is not None else "" for h in header_row]
            col_header_str = " | ".join(headers)

            lines: list[str] = [
                f"=== Sheet: {sheet_name} ===",
                f"Columns: {col_header_str}",
            ]

            # Data rows (up to SAMPLE_ROWS)
            data_rows = rows[1 : SAMPLE_ROWS + 1]
            non_empty_data_rows = 0
            for row_num, row in enumerate(data_rows, start=1):
                if row is None:
                    continue
                cells = [str(v).strip() if v is not None else "" for v in row]
                if any(cells):
                    non_empty_data_rows += 1
                    lines.append(f"Row {row_num}: {' | '.join(cells)}")

            if len(rows) > SAMPLE_ROWS:
                lines.append(f"... (additional rows capped at {SAMPLE_ROWS})")

            sheet_parts.append("\n".join(lines))

        try:
            wb.close()
        except Exception:
            pass

        result = "\n\n".join(sheet_parts).strip()
        if not result:
            log.warning("XLSX '%s' contains no extractable data.", filepath)

        return result

    except Exception as exc:
        log.warning("Unhandled exception in xlsx_parser for '%s': %s", filepath, exc)
        return ""
