"""
app.py — Phase 5: Streamlit UI for Nexus semantic file search.

Run
---
    streamlit run app.py
"""

from __future__ import annotations

import contextlib
import io
import os
import platform
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Ensure nexus/ project root is on sys.path when launched via streamlit
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
import discovery
import indexer
import query_engine

# ===========================================================================
# Page config  (must be the very first Streamlit call)
# ===========================================================================
st.set_page_config(
    page_title="Nexus — Semantic File Search",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ===========================================================================
# Rich Animated CSS — Colour-guaranteed, overrides Streamlit theme layer
# ===========================================================================
_CSS = """<style>
/* ── Sidebar-specific overrides ───────────────────────────────────────────── */
section[data-testid="stSidebar"] code {
    background: rgba(255,255,255,0.1) !important;
    color: #c7d2fe !important;
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 0.75rem;
}
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
    color: rgba(255,255,255,0.5) !important;
}
section[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) {
    background: rgba(255,255,255,0.08) !important;
    color: #e2e8f0 !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
}
section[data-testid="stSidebar"] .stButton > button:not([kind="primary"]):hover {
    background: rgba(255,255,255,0.15) !important;
    border-color: rgba(165,180,252,0.5) !important;
}
section[data-testid="stSidebar"] .stExpander {
    border-color: rgba(255,255,255,0.15) !important;
    background: rgba(255,255,255,0.05) !important;
}
section[data-testid="stSidebar"] .stExpander summary {
    color: #e2e8f0 !important;
}
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root {
    --indigo:    #6366f1;
    --indigo-d:  #4338ca;
    --violet:    #8b5cf6;
    --rose:      #f43f5e;
    --teal:      #0d9488;
    --teal-l:    #14b8a6;
    --amber:     #f59e0b;
    --slate-900: #0f172a;
    --slate-700: #334155;
    --slate-500: #64748b;
    --slate-200: #e2e8f0;
    --slate-100: #f1f5f9;
    --slate-50:  #f8fafc;
    --card-bg:   #ffffff;
}
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}
.stApp { background-color: #ffffff !important; }
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1e1b4b 0%, #0f172a 100%) !important;
}
section[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
section[data-testid="stSidebar"] .stMarkdown h3,
section[data-testid="stSidebar"] .stMarkdown p { color: #ffffff !important; }
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.12) !important; }
section[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    color: #a5b4fc !important; font-size: 1.6rem !important; font-weight: 800 !important;
}
section[data-testid="stSidebar"] [data-testid="stMetricLabel"] {
    color: rgba(255,255,255,0.55) !important; font-size: 0.7rem !important;
    text-transform: uppercase !important; letter-spacing: 0.06em !important;
}
@keyframes scan-line {
    0%   { transform: translateY(-100%); opacity: 0; }
    10%  { opacity: 1; }
    90%  { opacity: 1; }
    100% { transform: translateY(3000%); opacity: 0; }
}
@keyframes pulse-ring {
    0%   { transform: translate(-50%,-50%) scale(0.85); opacity: 0.9; }
    50%  { transform: translate(-50%,-50%) scale(1.15); opacity: 0.3; }
    100% { transform: translate(-50%,-50%) scale(0.85); opacity: 0.9; }
}
@keyframes orbit {
    0%   { transform: rotate(0deg)   translateX(30px) rotate(0deg); }
    100% { transform: rotate(360deg) translateX(30px) rotate(-360deg); }
}
@keyframes shimmer {
    0%   { background-position: -600px 0; }
    100% { background-position: 600px 0; }
}
@keyframes gradient-shift {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
@keyframes float-dot {
    0%, 100% { transform: translateY(0px) scale(1); opacity: 0.18; }
    50%       { transform: translateY(-10px) scale(1.05); opacity: 0.28; }
}
@keyframes bar-grow {
    0%   { width: 0%; }
    100% { width: var(--bar-width, 0%); }
}
@keyframes fade-up {
    0%   { opacity: 0; transform: translateY(14px); }
    100% { opacity: 1; transform: translateY(0); }
}
@keyframes glow-pulse {
    0%, 100% { box-shadow: 0 0 15px rgba(99,102,241,0.5); }
    50%       { box-shadow: 0 0 30px rgba(99,102,241,0.85), 0 0 60px rgba(139,92,246,0.3); }
}
.nexus-hero {
    position: relative;
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 45%, #134e4a 100%);
    background-size: 300% 300%;
    animation: gradient-shift 10s ease infinite;
    border-radius: 18px;
    padding: 2.75rem 2.25rem 2.25rem 2.25rem;
    margin-bottom: 1.75rem;
    overflow: hidden;
    box-shadow: 0 20px 60px rgba(99,102,241,0.2), 0 4px 16px rgba(0,0,0,0.15);
}
.nexus-hero::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #6366f1, #8b5cf6, #f43f5e, #f59e0b, #14b8a6, #6366f1);
    background-size: 300% 100%;
    animation: shimmer 4s linear infinite;
    z-index: 2;
}
.nexus-hero::after {
    content: '';
    position: absolute;
    left: 0; right: 0; top: 0;
    height: 3px;
    background: linear-gradient(90deg, transparent 0%, rgba(165,180,252,0.8) 50%, transparent 100%);
    animation: scan-line 5s ease-in-out infinite;
    pointer-events: none;
    z-index: 3;
}
.nexus-hero-title {
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: -0.035em;
    margin: 0 0 0.4rem 0;
    background: linear-gradient(90deg, #ffffff 0%, #a5b4fc 40%, #5eead4 80%, #fbbf24 100%);
    background-size: 200% 100%;
    animation: shimmer 6s linear infinite;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.2;
}
.nexus-hero-sub {
    font-size: 0.9rem;
    color: rgba(255,255,255,0.62);
    margin: 0;
    font-weight: 400;
}
.nexus-hero-chips {
    margin-top: 1.1rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
}
.nexus-chip {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    border: 1px solid rgba(255,255,255,0.15);
    color: rgba(255,255,255,0.75);
    background: rgba(255,255,255,0.07);
    backdrop-filter: blur(4px);
}
.search-orb-wrapper {
    position: absolute;
    right: 2.5rem;
    top: 50%;
    transform: translateY(-50%);
    width: 90px;
    height: 90px;
}
.search-orb-core {
    position: absolute;
    top: 50%; left: 50%;
    width: 30px; height: 30px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 35%, #c7d2fe, #6366f1);
    transform: translate(-50%, -50%);
    animation: pulse-ring 2.5s ease-in-out infinite, glow-pulse 3s ease-in-out infinite;
}
.search-orb-ring {
    position: absolute;
    top: 50%; left: 50%;
    width: 78px; height: 78px;
    border-radius: 50%;
    border: 1.5px solid rgba(99,102,241,0.3);
    transform: translate(-50%, -50%);
}
.search-orb-ring2 {
    position: absolute;
    top: 50%; left: 50%;
    width: 56px; height: 56px;
    border-radius: 50%;
    border: 1px dashed rgba(20,184,166,0.35);
    transform: translate(-50%, -50%);
    animation: orbit 8s linear infinite reverse;
}
.search-orb-dot {
    position: absolute;
    top: 50%; left: 50%;
    width: 7px; height: 7px;
    border-radius: 50%;
    margin: -3.5px;
    background: var(--teal-l);
    box-shadow: 0 0 8px var(--teal-l);
    animation: orbit 3.2s linear infinite;
}
.search-orb-dot:nth-child(4) { animation-delay: -1.07s; background: #a5b4fc; box-shadow: 0 0 8px #a5b4fc; }
.search-orb-dot:nth-child(5) { animation-delay: -2.13s; background: #f0abfc; box-shadow: 0 0 8px #f0abfc; }
.float-dot {
    position: absolute;
    border-radius: 50%;
    animation: float-dot 3s ease-in-out infinite;
    filter: blur(2px);
}
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 3rem !important;
    max-width: 1100px !important;
}
.result-card {
    background: #ffffff !important;
    border: 1.5px solid #e2e8f0 !important;
    border-radius: 14px !important;
    padding: 1.35rem 1.6rem !important;
    margin-bottom: 1.1rem !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.18s ease;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    animation: fade-up 0.35s ease both;
    position: relative;
    overflow: hidden;
}
.result-card::before {
    content: '';
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 4px;
    background: linear-gradient(180deg, var(--indigo), var(--teal-l));
    border-radius: 3px 0 0 3px;
    opacity: 0;
    transition: opacity 0.22s ease;
}
.result-card:hover {
    border-color: #a5b4fc !important;
    box-shadow: 0 8px 32px rgba(99,102,241,0.13) !important;
    transform: translateY(-2px);
}
.result-card:hover::before { opacity: 1; }
.badge {
    display: inline-flex;
    align-items: center;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    margin-bottom: 0.4rem;
    margin-right: 0.35rem;
    border: 1.5px solid transparent;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.badge:hover { transform: scale(1.07); box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
.badge-pdf   { background: #fef2f2; color: #be123c !important; border-color: #fecaca; }
.badge-docx  { background: #eff6ff; color: #1d4ed8 !important; border-color: #bfdbfe; }
.badge-xlsx  { background: #f0fdf4; color: #15803d !important; border-color: #86efac; }
.badge-pptx  { background: #fff7ed; color: #c2410c !important; border-color: #fdba74; }
.badge-image { background: #fdf4ff; color: #7e22ce !important; border-color: #d8b4fe; }
.badge-code  { background: #f0fdfa; color: #0f766e !important; border-color: #5eead4; }
.badge-other { background: #f8fafc; color: #475569 !important; border-color: #cbd5e1; }
.badge-bm25  { background: #fffbeb; color: #92400e !important; border-color: #fcd34d; }
.file-path {
    font-size: 0.74rem;
    font-family: ui-monospace, 'Cascadia Code', Menlo, monospace;
    color: #64748b !important;
    word-break: break-all;
    margin: 0.15rem 0 0.5rem 0;
}
.score-row { display: flex; align-items: center; gap: 0.75rem; margin: 0.4rem 0 0.9rem 0; }
.score-bar { flex: 1; height: 7px; background: #f1f5f9; border-radius: 99px; overflow: hidden; }
.score-fill {
    height: 100%;
    border-radius: 99px;
    background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 40%, #14b8a6 80%, #6366f1 100%);
    background-size: 300% 100%;
    animation: shimmer 3s linear infinite, bar-grow 0.9s cubic-bezier(.2,.8,.4,1) both;
    width: var(--bar-width, 0%);
}
.score-pct {
    font-size: 0.8rem; font-weight: 800; color: #6366f1 !important;
    min-width: 46px; font-family: ui-monospace, monospace;
}
.label {
    font-size: 0.67rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.09em; color: #64748b !important;
    margin-top: 0.85rem; margin-bottom: 0.25rem;
}
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #c7d2fe; border-radius: 99px; }
::-webkit-scrollbar-thumb:hover { background: #6366f1; }
</style>"""
st.markdown(_CSS, unsafe_allow_html=True)



# ===========================================================================
# Cached resources
# ===========================================================================

@st.cache_resource
def get_chroma_collection():
    """Open the ChromaDB collection once and reuse across reruns."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(_ROOT / config.CHROMA_DB_PATH))
        return client.get_or_create_collection(
            name=query_engine.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    except Exception:
        return None  # handled gracefully in UI


@st.cache_resource
def get_db_connection():
    """Open the SQLite connection once and reuse across reruns."""
    try:
        import sqlite3
        db_path = _ROOT / config.SQLITE_DB_PATH
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


# ===========================================================================
# Helpers
# ===========================================================================

def open_file(path: str) -> None:
    """Open *path* in the OS default application."""
    if not Path(path).exists():
        st.warning(
            f"⚠️ **File not found on disk.**  \n"
            f"`{path}`  \n"
            "Re-run **Full Reindex** to refresh the index."
        )
        return

    try:
        system = platform.system()
        if system == "Windows":
            # subprocess.Popen with shell=True correctly launches the file
            # in the user's desktop session (os.startfile fails inside Streamlit server)
            subprocess.Popen(f'start "" "{path}"', shell=True)
        elif system == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:
        st.warning(f"Could not open file: {exc}")


def open_folder(path: str) -> None:
    """Reveal *path* in the OS file explorer (shows containing folder)."""
    if not Path(path).exists():
        st.warning(f"⚠️ File not found: `{path}`")
        return
    try:
        system = platform.system()
        if system == "Windows":
            # /select highlights the specific file in Explorer
            subprocess.Popen(f'explorer /select,"{path}"', shell=True)
        elif system == "Darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", str(Path(path).parent)])
    except Exception as exc:
        st.warning(f"Could not open folder: {exc}")


def _badge_html(file_type: str, is_bm25_fallback: bool = False) -> str:
    cls = f"badge-{file_type}" if file_type in {"pdf","docx","xlsx","pptx","image","code"} else "badge-other"
    html = f'<span class="badge {cls}">{file_type}</span>'
    if is_bm25_fallback:
        html += '<span class="badge badge-bm25">BM25 Fallback</span>'
    return html


def _score_bar_html(score: float) -> str:
    pct = score * 100
    return (
        f'<div class="score-row">'
        f'  <div class="score-bar"><div class="score-fill" style="--bar-width:{pct:.1f}%; width:{pct:.1f}%"></div></div>'
        f'  <span class="score-pct">{pct:.1f}%</span>'
        f'</div>'
    )


def _get_index_stats() -> tuple[int, int, int]:
    """Return (total_files, embedded_files, pending_files) from SQLite."""
    conn = get_db_connection()
    if conn is None:
        return (0, 0, 0)
    try:
        cur = conn.execute("SELECT COUNT(*), SUM(CASE WHEN embedding_status = 'embedded' THEN 1 ELSE 0 END), SUM(CASE WHEN embedding_status = 'pending' THEN 1 ELSE 0 END) FROM files")
        row = cur.fetchone()
        if row:
            total = row[0] or 0
            embedded = row[1] or 0
            pending = row[2] or 0
            return (total, embedded, pending)
        return (0, 0, 0)
    except Exception:
        return (0, 0, 0)


# ===========================================================================
# Result card rendering
# ===========================================================================

def render_result_card(rank: int, result: dict) -> None:
    file_type        = result.get("file_type", "other")
    filename         = result.get("filename", "Unknown")
    path             = result.get("path", "")
    score            = result.get("similarity_score", 0.0)
    expl             = result.get("explanation", "")
    summ             = result.get("summary", "")
    chunk            = result.get("matched_chunk_text", "")
    is_bm25_fallback = result.get("is_bm25_fallback", False)
    file_exists      = Path(path).exists() if path else False

    with st.container():
        st.markdown('<div class="result-card">', unsafe_allow_html=True)

        if path and not file_exists:
            st.warning(
                "This file no longer exists on disk and cannot be opened. "
                "Re-run **Reindex Now** to update the index.",
                icon=None,
            )

        col_title, col_btn = st.columns([5, 1])
        with col_title:
            st.markdown(
                f"{_badge_html(file_type, is_bm25_fallback)}"
                f"<h4 style='margin:0.25rem 0 0 0; font-size:1.05rem; font-weight:600; color:#0f172a;'>#{rank} &nbsp; {filename}</h4>",
                unsafe_allow_html=True,
            )
            st.markdown(f'<p class="file-path">{path}</p>', unsafe_allow_html=True)

        with col_btn:
            st.write("")
            if file_exists:
                try:
                    file_bytes = Path(path).read_bytes()
                    _mime_map = {
                        "pdf": "application/pdf",
                        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        "png": "image/png",
                        "jpg": "image/jpeg",
                        "jpeg": "image/jpeg",
                        "py": "text/plain",
                        "js": "text/plain",
                        "ts": "text/plain",
                        "java": "text/plain",
                        "cpp": "text/plain",
                        "c": "text/plain",
                    }
                    ext = Path(path).suffix.lstrip(".").lower()
                    mime = _mime_map.get(ext, "application/octet-stream")
                    st.download_button(
                        label="Download / Open",
                        data=file_bytes,
                        file_name=filename,
                        mime=mime,
                        key=f"dl_{rank}_{path}",
                        help="Downloads the file to open in your default application",
                        use_container_width=True,
                    )
                except Exception as exc:
                    st.warning(f"Cannot read file: {exc}")
            else:
                st.button(
                    "Download / Open",
                    key=f"dl_{rank}_{path}",
                    disabled=True,
                    help="File no longer on disk",
                    use_container_width=True,
                )

        st.markdown('<p class="label">Relevance Score</p>', unsafe_allow_html=True)
        st.markdown(_score_bar_html(score), unsafe_allow_html=True)

        if expl:
            st.markdown('<p class="label">Why this matched</p>', unsafe_allow_html=True)
            st.markdown(expl)

        if summ:
            st.markdown('<p class="label">Summary</p>', unsafe_allow_html=True)
            st.markdown(summ)

        if chunk:
            with st.expander("Matched snippet", expanded=False):
                st.caption(chunk[:800])

        st.markdown("</div>", unsafe_allow_html=True)


# ===========================================================================
# Sidebar
# ===========================================================================

def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            "<div style='margin-bottom: 1rem;'>"
            "<h3 style='font-size: 1.25rem; font-weight: 700; letter-spacing: -0.02em; color: #ffffff; margin: 0;'>NEXUS</h3>"
            "<p style='font-size: 0.72rem; font-weight: 500; color: rgba(165,180,252,0.85); text-transform: uppercase; letter-spacing: 0.05em; margin: 0.1rem 0 0 0;'>Local Semantic Search</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.divider()

        st.markdown("<p class='label' style='margin-top:0;'>Indexed Folders</p>", unsafe_allow_html=True)
        if config.INDEX_FOLDERS:
            for folder in config.INDEX_FOLDERS:
                exists = Path(folder).exists()
                status_icon = "✓" if exists else "✗"
                dot_color = "#34d399" if exists else "#f87171"
                st.markdown(
                    f"<div style='display:flex;align-items:flex-start;gap:6px;margin:4px 0;'>"
                    f"<span style='color:{dot_color};font-weight:700;font-size:0.85rem;margin-top:1px;flex-shrink:0;'>{status_icon}</span>"
                    f"<span style='color:#c7d2fe;font-size:0.75rem;font-family:ui-monospace,monospace;word-break:break-all;'>{folder}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No folders configured. Edit `config.INDEX_FOLDERS` in **config.py**.")

        st.caption("Edit `config.py` to add or remove folders.")
        st.divider()

        # ── Index stats ─────────────────────────────────────────────────────
        total, embedded, pending = _get_index_stats()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Files", total)
        with col2:
            st.metric("Embedded", embedded)
        if pending > 0:
            st.caption(f"⚡ **{pending} file(s)** indexed via keyword search (BM25)")
        st.divider()

        # ── Reindex button ──────────────────────────────────────────────────
        st.markdown("<p class='label' style='margin-top:0;'>Indexing Actions</p>", unsafe_allow_html=True)

        if not config.INDEX_FOLDERS:
            st.warning("Add folders to `config.INDEX_FOLDERS` before indexing.")
        else:
            col_a, col_b = st.columns([1, 1])
            with col_a:
                if st.button("🔄 Full Reindex", use_container_width=True, type="primary"):
                    _run_reindex(embed_only=False)
            with col_b:
                if st.button("⚡ Resume Embed", use_container_width=True, help="Resume embedding pending files"):
                    _run_reindex(embed_only=True)

            if st.button(
                "🧹 Purge Stale Vectors",
                use_container_width=True,
                help="Remove ChromaDB vectors whose paths no longer exist in the index (fixes 'file not found' warnings)",
            ):
                with st.spinner("Scanning ChromaDB for stale vectors…"):
                    n = query_engine.purge_stale_chroma_vectors()
                if n > 0:
                    st.success(f"✅ Removed **{n}** stale vector(s). Search results will now be accurate.")
                else:
                    st.info("✅ No stale vectors found — index is clean.")

        st.divider()
        with st.expander("💡 How it works", expanded=False):
            st.markdown(
                """
**Nexus** is a local two-phase semantic file search engine:

1. **Phase A (Fast Keyword Search)** — Discovers, parses, and chunks files.
   Text chunks are indexed immediately using **BM25 keyword search** — search is usable in seconds!
2. **Phase B (Dense Semantic Upgrade)** — Batches chunks into Ollama (`nomic-embed-text`)
   and stores vectors in ChromaDB, upgrading search quality to semantic matching as it completes.

No data leaves your computer at any step.
                """
            )

        st.divider()
        st.subheader("🤖 Models")
        st.markdown(
            f"**Embed:** `{config.EMBED_MODEL}` (batch={config.EMBED_BATCH_SIZE})  \n"
            f"**LLM:** `{config.LLM_MODEL}`"
        )
        st.caption("Make sure Ollama is running: `ollama serve`")


def _run_reindex(embed_only: bool = False) -> None:
    """Execute two-phase indexer reporting Phase A and Phase B progress explicitly."""
    status_placeholder  = st.empty()
    progress_bar        = st.empty()
    log_placeholder     = st.empty()

    buf = io.StringIO()

    if not config.INDEX_FOLDERS and not embed_only:
        st.warning("INDEX_FOLDERS is empty.")
        return

    with contextlib.redirect_stdout(buf):
        t0 = time.perf_counter()

        conn = indexer._get_db_connection()
        indexer._init_db(conn)

        if not embed_only:
            status_placeholder.info("🔎 **Phase A in progress:** Discovering, parsing & chunking files…")
            discovered = discovery.discover_files(config.INDEX_FOLDERS)

            # Filter files for Phase A
            files_to_process = []
            for file_rec in discovered:
                existing = indexer._get_indexed_record(conn, file_rec["path"])
                if not (existing and existing["modified_time"] == file_rec["modified_time"] and existing["embedding_status"] == "embedded"):
                    files_to_process.append(file_rec)

            if files_to_process:
                parsed_res, parse_errs, file_chunks, parse_time = indexer.run_phase_a(files_to_process, conn)
                status_placeholder.success(f"⚡ **Phase A complete** in {parse_time:.2f}s — keyword search (BM25) ready for {len(parsed_res)} file(s)!")
                time.sleep(1.2)

        # ── Phase B Progress Tracking ────────────────────────────────────────
        status_placeholder.info("🧬 **Phase B in progress:** Batch embedding chunks & upgrading to dense semantic search…")

        collection = indexer._get_chroma_collection()

        def progress_cb(current: int, total: int, filename: str):
            pct = current / total if total > 0 else 1.0
            progress_bar.progress(pct)
            status_placeholder.info(f"🧬 **Phase B in progress:** Embedding `{filename}` ({current}/{total} files)…")

        summary_b = indexer.run_phase_b(conn, collection, progress_callback=progress_cb)
        elapsed = time.perf_counter() - t0
        conn.close()

    progress_bar.empty()
    status_placeholder.empty()

    get_chroma_collection.clear()
    get_db_connection.clear()

    log_text = buf.getvalue()

    st.success(
        f"**Done!** &nbsp;"
        f"Embedded: **{summary_b['embedded']}** &nbsp;|&nbsp;"
        f"Failed: **{summary_b['failed']}** &nbsp;|&nbsp;"
        f"Time: **{elapsed:.1f}s**"
    )

    with st.expander("View indexer log", expanded=False):
        st.code(log_text or "(no output)", language=None)

    st.rerun()


# ===========================================================================
# Main search area
# ===========================================================================

def render_main() -> None:
    hero_html = (
        '<div class="nexus-hero">'
        '<div class="float-dot" style="width:90px;height:90px;background:#6366f1;top:-20px;left:3%;animation-delay:0s;"></div>'
        '<div class="float-dot" style="width:50px;height:50px;background:#14b8a6;top:55%;left:10%;animation-delay:0.8s;"></div>'
        '<div class="float-dot" style="width:35px;height:35px;background:#8b5cf6;bottom:5%;left:28%;animation-delay:1.6s;"></div>'
        '<div class="float-dot" style="width:20px;height:20px;background:#f43f5e;top:15%;left:45%;animation-delay:0.4s;"></div>'
        '<div class="float-dot" style="width:25px;height:25px;background:#f59e0b;top:70%;left:55%;animation-delay:1.2s;"></div>'
        '<div class="search-orb-wrapper">'
        '<div class="search-orb-ring"></div>'
        '<div class="search-orb-ring2"></div>'
        '<div class="search-orb-core"></div>'
        '<div class="search-orb-dot"></div>'
        '<div class="search-orb-dot"></div>'
        '<div class="search-orb-dot"></div>'
        '</div>'
        '<h2 class="nexus-hero-title">Semantic File Search</h2>'
        '<p class="nexus-hero-sub">Search documents, spreadsheets, slides, PDFs, code, and images &mdash; in natural language.</p>'
        '<div class="nexus-hero-chips">'
        '<span class="nexus-chip">&#x1F4C4; PDF</span>'
        '<span class="nexus-chip">&#x1F4DD; DOCX</span>'
        '<span class="nexus-chip">&#x1F4CA; XLSX</span>'
        '<span class="nexus-chip">&#x1F4F8; Images</span>'
        '<span class="nexus-chip">&#x1F4BB; Code</span>'
        '<span class="nexus-chip">&#x1F4D1; PPTX</span>'
        '</div>'
        '</div>'
    )
    st.markdown(hero_html, unsafe_allow_html=True)


    col_input, col_btn = st.columns([5, 1])
    with col_input:
        query = st.text_input(
            "Search query",
            placeholder="e.g. quarterly revenue report, Python JSON parser, architecture diagram...",
            label_visibility="collapsed",
            key="search_query",
        )
    with col_btn:
        st.write("")
        search_clicked = st.button("Search", type="primary", use_container_width=True)

    should_search = search_clicked and bool(query)

    total, embedded, pending = _get_index_stats()
    if total == 0:
        st.divider()
        st.info(
            "🗃️ **No files indexed yet.**  \n"
            "Click **Full Reindex** in the sidebar to scan your folders and build the search index."
        )
        return

    if not should_search:
        if "last_results" not in st.session_state:
            st.divider()
            st.markdown(
                "<div style='border: 1px dashed #cbd5e1; border-radius: 8px; padding: 2.5rem; text-align: center; background: #f8fafc; margin-top: 1.5rem;'>"
                "<p style='font-size: 0.95rem; font-weight: 600; color: #334155; margin-bottom: 0.25rem;'>Ready to Search</p>"
                "<p style='font-size: 0.82rem; color: #64748b; margin: 0;'>Enter any topic, keyword, or query in the box above to find matching files.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            _display_results(
                st.session_state["last_query"],
                st.session_state["last_results"],
                st.session_state.get("last_filter"),
            )
        return

    # ── AI Explanation Option ──────────────────────────────────────────────
    enable_ai = st.checkbox("Generate AI Explanations (Ollama LLM)", value=False, help="Uncheck for instant search results")

    with st.spinner("Searching…"):
        file_type_filter = query_engine.detect_file_type_filter(query)
        try:
            results = query_engine.search(
                query,
                top_k=config.TOP_K,
                file_type_filter=file_type_filter,
            )
        except RuntimeError as exc:
            st.error(
                f"Search failed: {exc}  \n\n"
                "Make sure Ollama is running (`ollama serve`)."
            )
            return

    if results and enable_ai:
        import concurrent.futures
        with st.spinner("Generating AI explanations…"):
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(results), 5)) as executor:
                futures = [executor.submit(query_engine.explain_result, query, result, timeout=3) for result in results]
                concurrent.futures.wait(futures)

    st.session_state["last_query"]   = query
    st.session_state["last_results"] = results
    st.session_state["last_filter"]  = file_type_filter

    _display_results(query, results, file_type_filter)


def _display_results(query: str, results: list[dict], file_type_filter: str | None) -> None:
    st.divider()

    filter_label = f" <span style='font-size: 0.8rem; font-weight: 500; color: #64748b;'>(filtered: {file_type_filter})</span>" if file_type_filter else ""
    st.markdown(
        f"<h3 style='font-size: 1.15rem; font-weight: 600; color: #0f172a; margin-bottom: 0.2rem;'>Results for &ldquo;{query}&rdquo;{filter_label}</h3>",
        unsafe_allow_html=True,
    )

    if not results:
        st.warning(
            "No matching files found. "
            "Try rephrasing your search or removing file-type keywords."
        )
        return

    st.caption(f"{len(results)} matching file(s) ranked by relevance")
    st.write("")

    for rank, result in enumerate(results, start=1):
        render_result_card(rank, result)


def main() -> None:
    render_sidebar()
    render_main()


main()
