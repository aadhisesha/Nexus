# Nexus 🔍 — Local Semantic File Search

Nexus lets you index your local files (PDFs, Word docs, spreadsheets, presentations,
images, and source code) and search them with natural-language queries powered by
locally-running LLMs via [Ollama](https://ollama.com/).

---

## Architecture Overview

| Phase | Module | Responsibility |
|-------|--------|---------------|
| 1 | `discovery.py` | Recursive folder scan + watchdog file-watcher |
| 2 | `parsers/` | Format-specific text extraction |
| 3 | `indexer.py` | Chunk → embed → store (ChromaDB + SQLite) |
| 4 | `query_engine.py` | Embed query → retrieve → LLM explanation |
| 5 | `app.py` | Streamlit UI |

---

## Prerequisites

### 1 — Install Ollama

Download and install Ollama for your platform from <https://ollama.com/download>.

After installation, verify it works:

```bash
ollama --version
```

### 2 — Pull the Required Models

Nexus uses two models:

| Purpose | Model | Pull command |
|---------|-------|-------------|
| Text embeddings | `nomic-embed-text` | `ollama pull nomic-embed-text` |
| Chat / explanations | `qwen2.5` | `ollama pull qwen2.5` |

```bash
ollama pull nomic-embed-text
ollama pull qwen2.5
```

> **Note:** `qwen2.5` (default 7 B) requires ~5 GB of free disk space.
> You can swap in any other model you have locally by editing `LLM_MODEL` in `config.py`.

Confirm both models are available:

```bash
ollama list
```

### 3 — Optimize Ollama Throughput (Recommended)

To achieve maximum parallel throughput when embedding chunks or processing vision calls concurrently, set these environment variables before starting Ollama:

| Variable | Recommended Value | Description |
|----------|-------------------|-------------|
| `OLLAMA_NUM_PARALLEL` | `4` | Max concurrent requests processed in parallel per model |
| `OLLAMA_MAX_LOADED_MODELS` | `2` | Max models kept loaded in memory simultaneously (e.g. embed + chat model) |

#### Setting on Windows (PowerShell) before starting `ollama serve`:
```powershell
$env:OLLAMA_NUM_PARALLEL = 4
$env:OLLAMA_MAX_LOADED_MODELS = 2
ollama serve
```

#### Setting permanently on Windows:
1. Search **"Edit the system environment variables"** in the Windows Start menu.
2. Click **Environment Variables** → Under **User variables**, click **New**.
3. Add `OLLAMA_NUM_PARALLEL` = `4` and `OLLAMA_MAX_LOADED_MODELS` = `2`.

#### Setting on macOS / Linux:
```bash
export OLLAMA_NUM_PARALLEL=4
export OLLAMA_MAX_LOADED_MODELS=2
ollama serve
```

### 3 — Install Tesseract OCR (for image files)

Tesseract is required for extracting text from `.png` / `.jpg` / `.jpeg` files.

#### Windows

1. Download the installer from <https://github.com/UB-Mannheim/tesseract/wiki>.
2. Run the installer (default path: `C:\Program Files\Tesseract-OCR\`).
3. Add the install directory to your system `PATH`, **or** set the path explicitly
   in `parsers/image_parser.py` (Phase 2):
   ```python
   import pytesseract
   pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
   ```

#### macOS

```bash
brew install tesseract
```

#### Linux (Debian/Ubuntu)

```bash
sudo apt-get install tesseract-ocr
```

Verify:

```bash
tesseract --version
```

---

## Installation

### 1 — (Optional) Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 2 — Install Python dependencies

```bash
pip install -r requirements.txt
```

---

## Configuration

Open `config.py` and fill in `INDEX_FOLDERS` with the absolute paths you
want Nexus to monitor:

```python
INDEX_FOLDERS = [
    r"C:\Users\YourName\Documents",
    r"C:\Users\YourName\Desktop",
    r"C:\Users\YourName\Downloads",
]
```

All other settings (`EMBED_MODEL`, `LLM_MODEL`, `CHUNK_SIZE`, `TOP_K`, …) have
sensible defaults and can be tuned in the same file.

---

## Running Nexus

```bash
streamlit run app.py
```

Streamlit will open the UI in your default browser at `http://localhost:8501`.

---

## Data Storage

| Path | Contents |
|------|----------|
| `data/chroma/` | ChromaDB vector store (auto-created on first index run) |
| `data/metadata.db` | SQLite file metadata cache (auto-created on first run) |

Both paths are listed in `data/.gitignore` and will not be committed to version control.

---

## Supported File Types

| Extension(s) | Parser | Notes |
|---|---|---|
| `.pdf` | PyMuPDF | OCR fallback for scanned pages |
| `.docx` | python-docx | Headings, paragraphs, tables |
| `.xlsx` | openpyxl + pandas | Per-sheet extraction |
| `.pptx` | python-pptx | Slide text + speaker notes |
| `.png`, `.jpg`, `.jpeg` | pytesseract + Pillow | Full OCR pipeline |
| `.py`, `.js`, `.java`, `.cpp`, `.c`, `.ts` | plain reader | UTF-8 with encoding fallback |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ollama: command not found` | Ensure Ollama is installed and on your `PATH` |
| `TesseractNotFoundError` | Set `tesseract_cmd` path in `image_parser.py` (see §3 above) |
| ChromaDB import errors | Upgrade: `pip install --upgrade chromadb` |
| Model not found in Ollama | Run `ollama pull <model-name>` |
