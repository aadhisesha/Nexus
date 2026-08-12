# Nexus — Demo Guide

> A local semantic file search prototype. All data stays on your machine.
> No cloud APIs, no subscriptions — just Ollama + ChromaDB running locally.

---

## 1. Prerequisites

| Dependency | Install |
|------------|---------|
| Python 3.10+ | [python.org](https://www.python.org/downloads/) |
| Ollama | [ollama.com/download](https://ollama.com/download) |
| Tesseract OCR | See §1c below (only needed for image OCR) |

### 1a — Install Ollama and pull models

```bash
# After installing Ollama, pull the two required models:
ollama pull nomic-embed-text   # ~274 MB — text embedding model
ollama pull qwen2.5            # ~4.7 GB — local LLM for explanations

# Verify both are available:
ollama list
```

Keep Ollama running in a terminal during the demo:
```bash
ollama serve
```

### 1b — Install Python dependencies

```bash
cd nexus/
pip install -r requirements.txt
```

### 1c — Install Tesseract OCR (for image files only)

- **Windows:** Download from [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki),
  run installer, then add `C:\Program Files\Tesseract-OCR\` to your system `PATH`.
- **macOS:** `brew install tesseract`
- **Linux:** `sudo apt-get install tesseract-ocr`

Verify: `tesseract --version`

---

## 2. Create a Curated Demo Folder

For a reliable demo, use a **small, hand-picked test folder** rather than your
entire Documents directory. Create `demo_files/` somewhere convenient and place
exactly **one clearly identifiable file of each type**:

```
demo_files/
  revenue_report_q4.pdf        ← a real PDF with readable text (not scanned)
  meeting_notes.docx           ← a Word doc with paragraphs and a table
  sales_data.xlsx              ← an Excel sheet with column headers + data rows
  project_overview.pptx        ← a PowerPoint with slide titles and bullet points
  company_logo.png             ← an image with visible text (e.g. a letterhead scan)
  data_pipeline.py             ← a Python script with classes and functions
```

> **Tip:** Keep each file small (< 1 MB). Larger files index fine but slow the
> first run. The demo works best when each file has distinctive content that
> won't collide with the others.

---

## 3. Configure Nexus

Open `config.py` and set `INDEX_FOLDERS` to point at your demo folder:

```python
INDEX_FOLDERS = [
    r"C:\Users\YourName\demo_files",   # Windows
    # "/Users/yourname/demo_files",    # macOS / Linux
]
```

All other settings can stay at their defaults.

---

## 4. Index the Demo Folder

```bash
# From the nexus/ directory:
python indexer.py
```

Expected output (first run):
```
[indexer] Starting discovery across 1 folder(s)...
[indexer] Discovered 6 supported file(s) in 0.01s

[1/6] INDEX     revenue_report_q4.pdf   (8 chunks)
[2/6] INDEX     meeting_notes.docx      (3 chunks)
[3/6] INDEX     sales_data.xlsx         (2 chunks)
[4/6] INDEX     project_overview.pptx   (4 chunks)
[5/6] INDEX     company_logo.png        (1 chunks)
[6/6] INDEX     data_pipeline.py        (3 chunks)

==================================================
  Indexer Summary
  Indexed (new/updated) :    6
  Skipped (unchanged)   :    0
  Failed                :    0
==================================================
```

Run it a second time — **all 6 files should be SKIPPED** (incremental indexing confirmed).

---

## 5. Launch the UI

```bash
streamlit run app.py
```

The browser opens at **http://localhost:8501** automatically.

---

## 6. Suggested Demo Queries

Run these queries in the UI (or via `python query_engine.py`) against the demo folder above.
Each is designed to hit a specific file unambiguously.

| Query | Expected top result | What to highlight |
|-------|--------------------|--------------------|
| `quarterly revenue figures` | `revenue_report_q4.pdf` | Score bar, explanation referencing "revenue", "Q4" |
| `action items from the team meeting` | `meeting_notes.docx` | Table content extracted, snippet shows meeting structure |
| `excel spreadsheet with sales numbers` | `sales_data.xlsx` | File-type filter auto-detected as `xlsx`; column headers in snippet |
| `slide deck about the project roadmap` | `project_overview.pptx` | Filter auto-detected as `pptx`; slide titles in snippet |
| `Python class that processes data` | `data_pipeline.py` | AST symbol summary ("Classes: DataProcessor") visible in snippet |

### Additional queries to demonstrate filter detection:

```
"show me the PDF with financial data"
"word document about budget planning"
"any Python scripts with utility functions"
"presentation about strategy"
```

### Image OCR demo query (if Tesseract is installed):

```
"image with company name"
```

---

## 7. "Reindex Now" Live Demo

1. Open the app at http://localhost:8501
2. Show the **sidebar** — indexed folder paths, file count metric, model names
3. Click **"Reindex Now"** → spinner runs → success banner shows Indexed/Skipped/Failed
4. Show the collapsible **"View indexer log"** expander for transparency
5. Expand **"💡 How it works"** in the sidebar for the plain-language pipeline explanation

---

## 8. Debugging After the Demo

All WARNING+ events from every run are written to:

```
nexus/logs/nexus.log
```

The log rotates at 2 MB (keeps 3 backups). Entries include timestamps, module name,
and the full error message — useful if a file silently failed to embed.

```bash
# Tail the log during a live run:
Get-Content logs\nexus.log -Wait   # Windows PowerShell
tail -f logs/nexus.log             # macOS / Linux
```

---

## 9. Known Limitations & Phase 2 Roadmap

The following are **intentional scope decisions for this prototype**, not bugs.
They represent the next layer of research and engineering:

| Limitation | Phase 2 Direction |
|------------|------------------|
| **No live file-watching** | `discovery.py` already scaffolds `start_watcher()` using `watchdog`; Phase 2 wires it to auto-reindex on file create/modify/delete |
| **No duplicate / version detection** | Two copies of the same report both get indexed independently; Phase 2 adds content-hash comparison and version clustering |
| **No contradiction detection** | If two documents make conflicting claims, results are ranked purely by similarity; Phase 2 adds an LLM cross-document reasoning pass |
| **No knowledge graph reasoning** | Results are retrieved by vector similarity, not by entity or relationship; Phase 2 integrates a local knowledge graph (e.g. Graphiti or Neo4j) for multi-hop queries |
| **Single-agent pipeline** | Each step (parse, embed, explain) is sequential; Phase 2 explores a multi-agent architecture where a planner agent dispatches specialist sub-agents per file type |
| **Native desktop UI** | The Streamlit interface requires a browser and a running server; Phase 2 targets a native desktop wrapper (e.g. Tauri or PyQt) for single-binary distribution |
| **No access control** | All indexed files are searchable by anyone who can reach `localhost:8501`; Phase 2 adds per-user access tagging derived from filesystem ACLs |

---

## Quick Reference

```bash
# Full setup in one block:
ollama pull nomic-embed-text && ollama pull qwen2.5
pip install -r requirements.txt
# Edit config.py → set INDEX_FOLDERS
python indexer.py
streamlit run app.py
```
