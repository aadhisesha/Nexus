"""Unit tests for query_engine logic that does NOT require Ollama/ChromaDB."""
import sys, re
sys.path.insert(0, ".")

import query_engine as qe

# ── 1. Import ─────────────────────────────────────────────────────────────
print("Import OK")

# ── 2. detect_file_type_filter ────────────────────────────────────────────
cases = [
    ("find the PDF about machine learning",         "pdf"),
    ("what does the excel spreadsheet say",         "xlsx"),
    ("show me the word document about budget",      "docx"),
    ("search the presentation slides on AI",        "pptx"),
    ("any image with a company logo",               "image"),
    ("python script that parses JSON",              "code"),
    ("general search with no type hint",            None),
    ("SHOW ME EXCEL FILES",                         "xlsx"),  # case-insensitive
]
for query, expected in cases:
    got = qe.detect_file_type_filter(query)
    status = "OK" if got == expected else f"FAIL (expected {expected!r}, got {got!r})"
    print(f"  filter '{query[:45]:<45}'  → {got!r:<8}  {status}")

print("detect_file_type_filter OK")

# ── 3. Cosine distance → similarity conversion ────────────────────────────
# dist=0 means identical → score=1.0
# dist=2 means opposite  → score=0.0
assert round(max(0.0, 1.0 - 0   / 2.0), 4) == 1.0
assert round(max(0.0, 1.0 - 2   / 2.0), 4) == 0.0
assert round(max(0.0, 1.0 - 1   / 2.0), 4) == 0.5
assert round(max(0.0, 1.0 - 0.4 / 2.0), 4) == 0.8
print("Score conversion OK")

# ── 4. explain_result response parsing ────────────────────────────────────
# Simulate a good LLM response
raw = (
    "EXPLANATION: This file matches because it contains detailed revenue data "
    "aligned with the user's query about sales figures.\n"
    "SUMMARY: The document is an Excel workbook with sales data across multiple "
    "regions. It includes columns for date, product, and revenue. The sheet covers "
    "quarterly performance for FY 2024."
)

exp_match = re.search(r"EXPLANATION:\s*(.+?)(?=SUMMARY:|$)", raw, re.DOTALL | re.IGNORECASE)
sum_match = re.search(r"SUMMARY:\s*(.+?)$",                  raw, re.DOTALL | re.IGNORECASE)

assert exp_match, "EXPLANATION not found"
assert sum_match, "SUMMARY not found"
exp = exp_match.group(1).strip()
summ = sum_match.group(1).strip()
assert "revenue" in exp,  f"Expected 'revenue' in explanation: {exp!r}"
assert "Excel"   in summ, f"Expected 'Excel' in summary: {summ!r}"
print(f"  Explanation: {exp[:80]}")
print(f"  Summary:     {summ[:80]}")
print("explain_result parsing OK")

# ── 5. explain_result fallback on bad LLM response ────────────────────────
# Monkey-patch ollama to simulate a failure
import types, sys
fake_ollama = types.ModuleType("ollama")
def _fail(*a, **kw): raise ConnectionError("Ollama not running")
fake_ollama.chat = _fail
fake_ollama.embeddings = _fail
sys.modules["ollama"] = fake_ollama

result = {"filename": "test.pdf", "file_type": "pdf",
          "matched_chunk_text": "some content", "path": "/test.pdf"}
qe.explain_result("my query", result)
assert result["explanation"] == "Matched based on content similarity.", result["explanation"]
assert result["summary"] == "", result["summary"]
print("explain_result fallback OK")

# ── 6. _wrap helper ───────────────────────────────────────────────────────
wrapped = qe._wrap("The quick brown fox jumps over the lazy dog and runs away fast", 20)
assert "\n" in wrapped, "Expected line break"
print(f"  Wrapped: {wrapped!r}")
print("_wrap OK")

print()
print("All unit checks passed.")
