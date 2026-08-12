"""
config.py — Central configuration for the Nexus semantic file search engine.

Edit INDEX_FOLDERS to point to the directories you want indexed.
All other settings have sensible defaults but can be overridden here.
"""

# ---------------------------------------------------------------------------
# Folders to index
# ---------------------------------------------------------------------------
# Add absolute paths to the directories you want Nexus to scan and index.
# Example:
#   INDEX_FOLDERS = [
#       r"C:\Users\YourName\Documents",
#       r"C:\Users\YourName\Desktop",
#       r"C:\Users\YourName\Downloads",
#   ]
INDEX_FOLDERS: list[str] = [
    r"C:\Users\acer\OneDrive\Documents\Aadhisesha",
    
]

# ---------------------------------------------------------------------------
# Directories to skip during discovery
# ---------------------------------------------------------------------------
EXCLUDED_DIR_NAMES: set[str] = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".idea",
    ".vscode",
}

# ---------------------------------------------------------------------------
# Supported file extensions → file-type labels
# ---------------------------------------------------------------------------
# Each key is a lowercase extension (without the leading dot).
# The value is the label used internally to route to the correct parser.
SUPPORTED_EXTENSIONS: dict[str, str] = {
    # Documents
    "pdf":  "pdf",
    "docx": "docx",
    "xlsx": "xlsx",
    "pptx": "pptx",
    # Images (parsed via OCR / vision)
    "png":  "image",
    "jpg":  "image",
    "jpeg": "image",
    # Code / plain-text
    "py":   "code",
    "js":   "code",
    "java": "code",
    "cpp":  "code",
    "c":    "code",
    "ts":   "code",
}

# ---------------------------------------------------------------------------
# Storage paths  (relative to the project root)
# ---------------------------------------------------------------------------
CHROMA_DB_PATH: str  = "data/chroma"       # ChromaDB persistence directory
SQLITE_DB_PATH: str  = "data/metadata.db"  # SQLite file for file metadata

# ---------------------------------------------------------------------------
# Ollama model names
# ---------------------------------------------------------------------------
EMBED_MODEL: str = "nomic-embed-text"   # Text embedding model
LLM_MODEL:   str = "qwen2.5"           # Chat / explanation model
VISION_MODEL: str = "moondream"       # Fast, lightweight vision-language model (1.7 GB)
                                        # Alternatives: "llava", "qwen2.5vl", "llama3.2-vision"
                                        # Pull with: ollama pull moondream
VISION_TIMEOUT_SECONDS: int = 45       # Max seconds to wait for a vision model response

# ---------------------------------------------------------------------------
# Chunking parameters
# ---------------------------------------------------------------------------
CHUNK_SIZE:    int = 512   # Target chunk size in characters
CHUNK_OVERLAP: int = 64    # Overlap between consecutive chunks

# ---------------------------------------------------------------------------
# Concurrency & Batching settings
# ---------------------------------------------------------------------------
OLLAMA_CONCURRENCY: int = 8  # Worker threads for Ollama HTTP requests
EMBED_BATCH_SIZE:   int = 64 # Chunks per Ollama batch embedding call for max throughput

# ---------------------------------------------------------------------------
# Retrieval parameters
# ---------------------------------------------------------------------------
TOP_K: int = 5  # Number of top chunks to retrieve per query

