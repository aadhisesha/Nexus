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
# Minimal custom CSS — readable, clean, no heavy theming
# ===========================================================================
st.markdown(
    """
    <style>
    /* Result cards */
    .result-card {
        background: var(--secondary-background-color);
        border: 1px solid var(--secondary-background-color);
        border-radius: 10px;
        padding: 1rem 1.25rem;
        margin-bottom: 1rem;
    }
    /* File-type badges */
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-bottom: 0.4rem;
        margin-right: 0.25rem;
    }
    .badge-pdf   { background:#ffdddd; color:#b00020; }
    .badge-docx  { background:#dde8ff; color:#1a4fa0; }
    .badge-xlsx  { background:#d9f0dd; color:#1a6b30; }
    .badge-pptx  { background:#fff0dd; color:#b05a00; }
    .badge-image { background:#ede0ff; color:#5a00a0; }
    .badge-code  { background:#e0f7f4; color:#006b5a; }
    .badge-other { background:#eeeeee; color:#555555; }
    .badge-bm25  { background:#fff3cd; color:#856404; border:1px solid #ffeeba; }
    /* Path text */
    .file-path   { font-size: 0.78rem; color: #888; word-break: break-all; }
    /* Score bar container */
    .score-row   { display:flex; align-items:center; gap:0.75rem; margin:0.5rem 0; }
    .score-bar   { flex:1; height:6px; background:#e0e0e0; border-radius:3px; overflow:hidden; }
    .score-fill  { height:100%; border-radius:3px;
                   background: linear-gradient(90deg, #4f8ef7, #a855f7); }
    .score-pct   { font-size:0.82rem; font-weight:600; color:#555; min-width:40px; }
    /* Section labels */
    .label { font-size:0.75rem; font-weight:700; text-transform:uppercase;
             letter-spacing:0.06em; color:#888; margin-top:0.6rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


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
    """Open *path* in the OS default application, cross-platform."""
    if not Path(path).exists():
        st.warning(
            f"⚠️ **File not found on disk.**  \n"
            f"`{path}`  \n"
            f"The file may have been moved or deleted since it was indexed.  "
            "Re-run **Reindex Now** to refresh the index."
        )
        return

    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(path)                          # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
    except Exception as exc:
        st.warning(f"Could not open file: {exc}")


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
        f'  <div class="score-bar"><div class="score-fill" style="width:{pct:.1f}%"></div></div>'
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
                "⚠️ This file no longer exists on disk and cannot be opened.  "
                "Re-run **Reindex Now** to update the index.",
                icon=None,
            )

        col_title, col_btn = st.columns([5, 1])
        with col_title:
            st.markdown(
                f"{_badge_html(file_type, is_bm25_fallback)}"
                f"<h4 style='margin:0.2rem 0 0 0'>#{rank} &nbsp; {filename}</h4>",
                unsafe_allow_html=True,
            )
            st.markdown(f'<p class="file-path">{path}</p>', unsafe_allow_html=True)

        with col_btn:
            st.write("")
            open_disabled = not file_exists
            open_help     = "Open in default app" if file_exists else "File no longer on disk"
            if st.button(
                "📂 Open",
                key=f"open_{rank}_{path}",
                help=open_help,
                disabled=open_disabled,
            ):
                open_file(path)

        st.markdown('<p class="label">Relevance score</p>', unsafe_allow_html=True)
        st.markdown(_score_bar_html(score), unsafe_allow_html=True)

        if expl:
            st.markdown('<p class="label">Why this matched</p>', unsafe_allow_html=True)
            st.markdown(expl)

        if summ:
            st.markdown('<p class="label">What it contains</p>', unsafe_allow_html=True)
            st.markdown(summ)

        if chunk:
            with st.expander("Matched text snippet", expanded=False):
                st.caption(chunk[:800])

        st.markdown("</div>", unsafe_allow_html=True)


# ===========================================================================
# Sidebar
# ===========================================================================

def render_sidebar() -> None:
    with st.sidebar:
        st.title("🔍 Nexus")
        st.caption("Local Semantic File Search (Two-Phase Indexing)")
        st.divider()

        st.subheader("📁 Indexed Folders")
        if config.INDEX_FOLDERS:
            for folder in config.INDEX_FOLDERS:
                exists = Path(folder).exists()
                icon   = "✅" if exists else "⚠️"
                st.markdown(f"{icon} `{folder}`")
        else:
            st.info("No folders configured. Edit `config.INDEX_FOLDERS` in **config.py**.")

        st.caption("To add folders, edit `config.py` directly.")
        st.divider()

        # ── Index stats ─────────────────────────────────────────────────────
        total, embedded, pending = _get_index_stats()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total files", total)
        with col2:
            st.metric("Embedded", embedded)
        if pending > 0:
            st.caption(f"⚡ **{pending} file(s)** ready for instant BM25 keyword search")
        st.divider()

        # ── Reindex button ──────────────────────────────────────────────────
        st.subheader("⚙️ Indexing")

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
    st.title("What file are you looking for?")
    st.caption(
        "Describe the content, topic, or ask a natural-language question. "
        "Include words like _pdf_, _excel_, _code_, or _image_ to filter by file type."
    )

    col_input, col_btn = st.columns([5, 1])
    with col_input:
        query = st.text_input(
            "Search query",
            placeholder="e.g.  quarterly revenue report   |   Python script for parsing JSON",
            label_visibility="collapsed",
            key="search_query",
        )
    with col_btn:
        st.write("")
        search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)

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
                "### 👆 Enter a query above to start searching",
                help="Type anything describing the file content you're looking for.",
            )
        else:
            _display_results(
                st.session_state["last_query"],
                st.session_state["last_results"],
                st.session_state.get("last_filter"),
            )
        return

    # ── AI Explanation Option ──────────────────────────────────────────────
    enable_ai = st.checkbox("🤖 Generate AI Explanations (Ollama LLM)", value=False, help="Uncheck for instant <0.1s search results")

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
                f"❌ **Search failed:** {exc}  \n\n"
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

    filter_label = f"  ·  filtered to **{file_type_filter}** files" if file_type_filter else ""
    st.markdown(f"### Results for &ldquo;{query}&rdquo;{filter_label}")

    if not results:
        st.warning(
            "🔍 **No matching files found.**  \n"
            "Try rephrasing your search, using different keywords, or removing the file-type hint."
        )
        return

    st.caption(f"{len(results)} file(s) matched · ranked by relevance")
    st.write("")

    for rank, result in enumerate(results, start=1):
        render_result_card(rank, result)


def main() -> None:
    render_sidebar()
    render_main()


main()
