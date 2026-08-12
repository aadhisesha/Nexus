"""
parsers/test_parsers.py — Sanity-check each parser against real sample files.

Usage
-----
    # From the nexus/ project root:
    python parsers/test_parsers.py

The script auto-generates sample files for every type it can create
programmatically (docx, xlsx, pptx, py).  For PDF and image it looks for
existing files in data/test_samples/ — place one there if you want to test
those parsers.  Instructions are printed if a sample is missing.

Alternatively, pass a directory of your own sample files:
    python parsers/test_parsers.py path/to/samples/
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make sure imports resolve from the nexus/ root regardless of cwd
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent   # nexus/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import parsers  # noqa: E402  (after sys.path fix)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PREVIEW_CHARS = 300
SAMPLES_DIR   = _ROOT / "data" / "test_samples"

# ---------------------------------------------------------------------------
# Sample-file generators (for types that don't need real binaries)
# ---------------------------------------------------------------------------

def _make_docx(path: Path) -> None:
    from docx import Document
    doc = Document()
    doc.add_heading("Test Document Heading", level=1)
    doc.add_paragraph("This is the first paragraph of the test document.")
    doc.add_paragraph("Second paragraph with more sample content.")
    table = doc.add_table(rows=2, cols=3)
    table.cell(0, 0).text = "Name"
    table.cell(0, 1).text = "Score"
    table.cell(0, 2).text = "Grade"
    table.cell(1, 0).text = "Alice"
    table.cell(1, 1).text = "95"
    table.cell(1, 2).text = "A"
    doc.save(str(path))


def _make_xlsx(path: Path) -> None:
    import openpyxl
    wb = openpyxl.Workbook()

    ws1 = wb.active
    ws1.title = "Sales"
    ws1.append(["Date", "Product", "Revenue", "Units"])
    ws1.append(["2024-01-01", "Widget A", 1200.0, 50])
    ws1.append(["2024-01-02", "Widget B", 850.5,  30])
    ws1.append(["2024-01-03", "Widget A", 975.0,  40])

    ws2 = wb.create_sheet("Inventory")
    ws2.append(["SKU", "Name", "Stock"])
    ws2.append(["W-001", "Widget A", 200])
    ws2.append(["W-002", "Widget B", 150])

    wb.save(str(path))


def _make_pptx(path: Path) -> None:
    from pptx import Presentation
    from pptx.util import Inches, Pt

    prs = Presentation()
    layout = prs.slide_layouts[1]   # Title and Content

    slide1 = prs.slides.add_slide(prs.slide_layouts[0])
    slide1.shapes.title.text = "Nexus Parser Test Presentation"
    slide1.placeholders[1].text = "Subtitle: automated test sample"

    slide2 = prs.slides.add_slide(layout)
    slide2.shapes.title.text = "Key Findings"
    tf = slide2.placeholders[1].text_frame
    tf.text = "Finding one: parsers work correctly."
    tf.add_paragraph().text = "Finding two: extraction is complete."
    notes = slide2.notes_slide.notes_text_frame
    notes.text = "Speaker note: remember to mention the demo."

    prs.save(str(path))


def _make_py(path: Path) -> None:
    path.write_text(
        '''\
"""Sample Python module for parser testing."""

import os


class DataProcessor:
    """Processes incoming data records."""

    def __init__(self, source: str):
        self.source = source

    def process(self, records: list) -> list:
        """Apply transformations to each record."""
        return [self._transform(r) for r in records]

    def _transform(self, record):
        return str(record).strip()


def load_data(filepath: str) -> list:
    """Load raw data from a file."""
    with open(filepath) as fh:
        return fh.readlines()


def main():
    proc = DataProcessor("example")
    data = load_data("input.txt")
    result = proc.process(data)
    print(f"Processed {len(result)} records.")


if __name__ == "__main__":
    main()
''',
        encoding="utf-8",
    )


def _make_image_with_text(path: Path) -> None:
    """Generate a simple PNG with readable text via Pillow (no external font needed)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (600, 200), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        # Use default bitmap font — always available in Pillow
        draw.text((20, 40),  "Nexus OCR Test Image",    fill=(0, 0, 0))
        draw.text((20, 80),  "Hello from pytesseract!", fill=(0, 0, 0))
        draw.text((20, 120), "Line three: 1234567890",  fill=(0, 0, 0))
        img.save(str(path))
    except Exception as exc:
        print(f"  [warn] Could not auto-generate test image: {exc}")
        print("  Place a real image with text at:", path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _preview(text: str, n: int = PREVIEW_CHARS) -> str:
    if not text:
        return "(no text extracted)"
    snippet = text[:n].replace("\n", " \\ ")
    if len(text) > n:
        snippet += f"  ... [{len(text):,} chars total]"
    return snippet


def _section(title: str) -> None:
    bar = "-" * 60
    print(f"\n{bar}")
    print(f"  {title}")
    print(bar)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(sample_dir: str | None = None) -> None:
    base = Path(sample_dir) if sample_dir else SAMPLES_DIR
    base.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("  Nexus Parser Test Suite")
    print(f"  Sample dir: {base}")
    print(f"{'='*60}")

    # ── DOCX ────────────────────────────────────────────────────────────────
    docx_path = base / "sample.docx"
    _section("DOCX parser")
    if not docx_path.exists():
        print(f"  Generating: {docx_path.name}")
        try:
            _make_docx(docx_path)
        except Exception as e:
            print(f"  ERROR generating docx: {e}")
    text = parsers.extract_text_by_type(str(docx_path), "docx")
    print(f"  {_preview(text)}")

    # ── XLSX ────────────────────────────────────────────────────────────────
    xlsx_path = base / "sample.xlsx"
    _section("XLSX parser")
    if not xlsx_path.exists():
        print(f"  Generating: {xlsx_path.name}")
        try:
            _make_xlsx(xlsx_path)
        except Exception as e:
            print(f"  ERROR generating xlsx: {e}")
    text = parsers.extract_text_by_type(str(xlsx_path), "xlsx")
    print(f"  {_preview(text)}")

    # ── PPTX ────────────────────────────────────────────────────────────────
    pptx_path = base / "sample.pptx"
    _section("PPTX parser")
    if not pptx_path.exists():
        print(f"  Generating: {pptx_path.name}")
        try:
            _make_pptx(pptx_path)
        except Exception as e:
            print(f"  ERROR generating pptx: {e}")
    text = parsers.extract_text_by_type(str(pptx_path), "pptx")
    print(f"  {_preview(text)}")

    # ── CODE (.py) ──────────────────────────────────────────────────────────
    py_path = base / "sample.py"
    _section("CODE parser (.py with AST summary)")
    if not py_path.exists():
        print(f"  Generating: {py_path.name}")
        _make_py(py_path)
    text = parsers.extract_text_by_type(str(py_path), "code")
    print(f"  {_preview(text)}")

    # ── PDF ─────────────────────────────────────────────────────────────────
    pdf_path = base / "sample.pdf"
    _section("PDF parser")
    if not pdf_path.exists():
        print(f"  [!] No sample PDF found at {pdf_path}")
        print("  Place a real .pdf file there to test this parser.")
        print("  Skipping.")
    else:
        from parsers import pdf_parser
        text, pages = pdf_parser.extract_text(str(pdf_path))
        print(f"  Pages: {pages}")
        print(f"  {_preview(text)}")

    # ── IMAGE ────────────────────────────────────────────────────────────────
    img_path = base / "sample.png"
    _section("IMAGE parser (VLM + OCR Fallback)")
    if not img_path.exists():
        print(f"  Generating synthetic test image: {img_path.name}")
        _make_image_with_text(img_path)
    if img_path.exists():
        from parsers import image_parser
        try:
            extracted_text, description = image_parser._call_ollama_vision(str(img_path))
            print("  --- VLM Output Breakdown ---")
            print(f"  [TEXT]        : {_preview(extracted_text if extracted_text else '(none)')}")
            print(f"  [DESCRIPTION] : {_preview(description if description else '(none)')}")
            print("\n  --- Combined extract_text() Output ---")
            combined = image_parser.extract_text(str(img_path))
            print(f"  {_preview(combined)}")
        except Exception as exc:
            print(f"  Ollama Vision not available or failed ({exc}). Running fallback extract_text()...")
            text = parsers.extract_text_by_type(str(img_path), "image")
            if not text:
                print("  (empty) — Tesseract may not be installed or on PATH.")
                print("  Install: https://github.com/UB-Mannheim/tesseract/wiki")
            else:
                print(f"  {_preview(text)}")
    else:
        print("  Skipping — could not generate test image.")

    print(f"\n{'='*60}")
    print("  Done.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(arg)
