"""
query_engine.py — Phase 4: Hybrid Query Engine (Dense ChromaDB + BM25 Fallback) → LLM Explanation.

Pipeline
--------
1. detect_file_type_filter(query)  →  optional file_type string or None
2. Dense Vector Search             →  ChromaDB cosine similarity for 'embedded' files
3. BM25 Keyword Search (Fallback)  →  rank_bm25 keyword match for 'pending' files
4. Combine & Deduplicate          →  one result dict per unique file
5. explain_result(query, result)   →  LLM-written explanation + summary
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

import config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(format="%(levelname)s  %(message)s", level=logging.WARNING)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared constants (keep in sync with indexer.py)
# ---------------------------------------------------------------------------
COLLECTION_NAME = "nexus_files"


# ===========================================================================
# 1. Embedding
# ===========================================================================

def embed_text(text: str) -> list[float]:
    """
    Embed *text* using Ollama + config.EMBED_MODEL.
    """
    try:
        import ollama
    except ImportError as exc:
        raise RuntimeError("ollama package not installed. Run: pip install ollama") from exc

    try:
        response = ollama.embeddings(model=config.EMBED_MODEL, prompt=text)
        return response["embedding"]
    except Exception as exc:
        raise RuntimeError(
            f"Ollama embedding failed (model={config.EMBED_MODEL!r}): {exc}"
        ) from exc


# ===========================================================================
# 2. Keyword → file_type planner
# ===========================================================================

_KEYWORD_MAP: list[tuple[list[str], str]] = [
    (["pdf"],                                    "pdf"),
    (["excel", "spreadsheet", "xlsx", "sheet",
      "worksheet", "workbook", "csv"],           "xlsx"),
    (["word", "docx", "document", "doc"],        "docx"),
    (["powerpoint", "pptx", "presentation",
      "slide", "deck"],                          "pptx"),
    (["image", "picture", "photo", "png",
      "jpg", "jpeg", "scan", "ocr"],             "image"),
    (["code", "script", "python", "javascript",
      "java", "typescript", "source", ".py",
      ".js", ".ts", ".java", ".cpp", ".c"],      "code"),
]


def detect_file_type_filter(query: str) -> str | None:
    """
    Scan *query* for file-type keywords and return the matching file_type label.
    """
    q_lower = query.lower()
    for keywords, file_type in _KEYWORD_MAP:
        if any(kw in q_lower for kw in keywords):
            return file_type
    return None


# ===========================================================================
# 3. Database & ChromaDB Helpers
# ===========================================================================

def _db_path() -> Path:
    return Path(__file__).parent / config.SQLITE_DB_PATH


def _get_db_connection() -> sqlite3.Connection | None:
    db_file = _db_path()
    if not db_file.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_file), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def _chroma_path() -> str:
    return str(Path(__file__).parent / config.CHROMA_DB_PATH)


def _get_chroma_collection():
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError("chromadb package not installed. Run: pip install chromadb") from exc

    client = chromadb.PersistentClient(path=_chroma_path())
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


# ===========================================================================
# 4. Fast BM25 Keyword Searcher
# ===========================================================================

class BM25Searcher:
    """
    In-memory BM25 index over text chunks stored in SQLite.
    Provides instant keyword search results for files pending dense embedding.
    """
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.bm25 = None
        self.records: list[dict] = []
        self._build_index()

    def _build_index(self) -> None:
        try:
            cur = self.conn.execute("""
                SELECT c.id, c.path, c.chunk_index, c.text, f.filename, f.file_type, f.embedding_status
                FROM chunks c
                JOIN files f ON c.path = f.path
            """)
            rows = cur.fetchall()
        except Exception:
            return

        if not rows:
            return

        corpus: list[list[str]] = []
        self.records = []

        for r in rows:
            tokens = re.findall(r"\w+", r["text"].lower())
            corpus.append(tokens)
            self.records.append({
                "chunk_id": r["id"],
                "path": r["path"],
                "filename": r["filename"],
                "file_type": r["file_type"],
                "chunk_index": r["chunk_index"],
                "text": r["text"],
                "embedding_status": r["embedding_status"],
            })

        if corpus:
            try:
                from rank_bm25 import BM25Okapi
                self.bm25 = BM25Okapi(corpus)
            except Exception as exc:
                log.warning("Could not initialize BM25Okapi: %s", exc)

    def search(
        self,
        query: str,
        top_k: int = config.TOP_K,
        file_type_filter: str | None = None,
        pending_only: bool = False,
    ) -> list[dict]:
        if not self.bm25 or not self.records:
            return []

        tokens = re.findall(r"\w+", query.lower())
        if not tokens:
            return []

        scores = self.bm25.get_scores(tokens)
        candidates = []

        for idx, score in enumerate(scores):
            if score <= 0:
                continue
            rec = self.records[idx]
            if file_type_filter and rec["file_type"] != file_type_filter:
                continue
            if pending_only and rec["embedding_status"] != "pending":
                continue
            candidates.append((score, rec))

        candidates.sort(key=lambda x: x[0], reverse=True)

        seen: dict[str, dict] = {}
        for score, rec in candidates:
            path = rec["path"]
            normalized_score = round(min(0.99, float(score) / 15.0), 4)
            if path not in seen or score > seen[path]["bm25_score"]:
                seen[path] = {
                    "path": rec["path"],
                    "filename": rec["filename"],
                    "file_type": rec["file_type"],
                    "matched_chunk_text": rec["text"],
                    "similarity_score": max(0.1, normalized_score),
                    "bm25_score": float(score),
                    "is_bm25_fallback": True,
                    "embedding_status": rec["embedding_status"],
                }

        results = sorted(seen.values(), key=lambda r: r["bm25_score"], reverse=True)
        return results[:top_k]


# ===========================================================================
# 5. Hybrid Search (Dense Chroma + BM25 Fallback)
# ===========================================================================

def _get_valid_sqlite_paths(conn: sqlite3.Connection) -> set[str]:
    """Return the set of all file paths currently in the SQLite files table."""
    try:
        cur = conn.execute("SELECT path FROM files")
        return {row[0] for row in cur.fetchall()}
    except Exception:
        return set()


def purge_stale_chroma_vectors() -> int:
    """
    Remove ChromaDB chunks whose path metadata is not present in the SQLite
    files table (e.g. old paths after folder moves/renames).  Returns the
    number of chunk IDs deleted.
    """
    conn = _get_db_connection()
    if conn is None:
        return 0

    valid_paths = _get_valid_sqlite_paths(conn)
    conn.close()

    if not valid_paths:
        return 0

    try:
        collection = _get_chroma_collection()
        # Fetch ALL chunk IDs + their path metadata from ChromaDB
        all_data = collection.get(include=["metadatas"])
        ids: list[str]   = all_data.get("ids", [])
        metas: list[dict] = all_data.get("metadatas", []) or []

        stale_ids = [
            chunk_id
            for chunk_id, meta in zip(ids, metas)
            if meta.get("path", "") not in valid_paths
        ]

        if stale_ids:
            # ChromaDB delete accepts up to ~5 000 IDs per call; batch it
            BATCH = 500
            for i in range(0, len(stale_ids), BATCH):
                collection.delete(ids=stale_ids[i : i + BATCH])
            log.info("Purged %d stale ChromaDB chunk(s) with outdated paths.", len(stale_ids))

        return len(stale_ids)
    except Exception as exc:
        log.warning("purge_stale_chroma_vectors error: %s", exc)
        return 0


def search(
    query: str,
    top_k: int = config.TOP_K,
    file_type_filter: str | None = None,
) -> list[dict]:
    """
    Search indexed files using dense ChromaDB vector search + BM25 keyword fallback.
    ChromaDB results are validated against SQLite so stale/moved-path vectors
    are silently skipped rather than surfaced as missing files.
    """
    results_by_path: dict[str, dict] = {}

    conn = _get_db_connection()

    # Build authoritative path set from SQLite so we can filter stale Chroma hits
    valid_sqlite_paths: set[str] = _get_valid_sqlite_paths(conn) if conn else set()

    # ── 5a. Dense ChromaDB Search ───────────────────────────────────────────
    query_embedding = None
    try:
        query_embedding = embed_text(query)
    except Exception as exc:
        log.warning("Query embedding failed (%s); falling back to BM25 search", exc)

    if query_embedding:
        try:
            collection = _get_chroma_collection()
            where: dict | None = {"file_type": {"$eq": file_type_filter}} if file_type_filter else None
            n_results = min(top_k * 4, 100)

            query_kwargs: dict = {
                "query_embeddings": [query_embedding],
                "n_results": n_results,
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                query_kwargs["where"] = where

            raw = collection.query(**query_kwargs)

            docs  = raw.get("documents", [[]])[0]
            metas = raw.get("metadatas", [[]])[0]
            dists = raw.get("distances", [[]])[0]

            for doc, meta, dist in zip(docs, metas, dists):
                path = meta.get("path", "")

                # ── skip stale vectors whose path is no longer in SQLite ──
                if valid_sqlite_paths and path not in valid_sqlite_paths:
                    log.debug("Skipping stale ChromaDB hit: %s", path)
                    continue

                score = max(0.0, 1.0 - dist / 2.0)

                if path not in results_by_path or score > results_by_path[path]["similarity_score"]:
                    results_by_path[path] = {
                        "path": path,
                        "filename": meta.get("filename", Path(path).name),
                        "file_type": meta.get("file_type", ""),
                        "matched_chunk_text": doc,
                        "similarity_score": round(score, 4),
                        "is_bm25_fallback": False,
                        "embedding_status": "embedded",
                    }
        except Exception as exc:
            log.warning("ChromaDB query error: %s", exc)

    # ── 5b. BM25 Keyword Search Fallback ────────────────────────────────────
    # When dense embedding failed entirely, run BM25 over ALL chunks so the
    # user always gets results (Ollama may be starting up or model not loaded).
    if conn:
        try:
            bm25_searcher = BM25Searcher(conn)
            # pending_only=False when embedding failed so we search everything
            bm25_results = bm25_searcher.search(
                query,
                top_k=top_k * 2,
                file_type_filter=file_type_filter,
                pending_only=(query_embedding is not None),  # full corpus fallback when embed failed
            )

            for b_res in bm25_results:
                path = b_res["path"]
                if path not in results_by_path:
                    results_by_path[path] = b_res
        except Exception as exc:
            log.warning("BM25 search error: %s", exc)
        finally:
            conn.close()

    # Dense results (is_bm25_fallback=False) ranked first, then BM25; both by score desc
    final_results = sorted(
        results_by_path.values(),
        key=lambda r: (not r.get("is_bm25_fallback"), r["similarity_score"]),
        reverse=True,
    )
    return final_results[:top_k]


# ===========================================================================
# 6. LLM Explanation
# ===========================================================================

_EXPLAIN_PROMPT = """\
You are a search assistant helping a user understand why a file matches their query.

USER QUERY: {query}

MATCHED FILE: {filename}
FILE TYPE: {file_type}
MATCHED CONTENT:
{chunk_text}

Please respond in exactly this format (no extra text before or after):
EXPLANATION: <1-2 sentences explaining specifically why this file is relevant to the query>
SUMMARY: <2-3 sentences summarising what this file appears to contain based on the matched content>"""


def _call_ollama_chat_timeout(prompt: str, timeout: int = 3) -> str:
    import concurrent.futures
    import ollama

    def _do_chat():
        res = ollama.chat(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return res["message"]["content"].strip()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_do_chat)
        return future.result(timeout=timeout)


def explain_result(query: str, result: dict, timeout: int = 3) -> dict:
    fallback_explanation = "Matched based on content similarity."
    fallback_summary = ""

    prompt = _EXPLAIN_PROMPT.format(
        query=query,
        filename=result.get("filename", ""),
        file_type=result.get("file_type", ""),
        chunk_text=result.get("matched_chunk_text", "")[:400],
    )

    try:
        raw_text = _call_ollama_chat_timeout(prompt, timeout=timeout)
    except Exception as exc:
        log.debug("LLM explain skipped/timed out for '%s': %s", result.get("filename"), exc)
        result["explanation"] = fallback_explanation
        result["summary"] = fallback_summary
        return result

    explanation = fallback_explanation
    summary = fallback_summary

    exp_match = re.search(r"EXPLANATION:\s*(.+?)(?=SUMMARY:|$)", raw_text, re.DOTALL | re.IGNORECASE)
    sum_match = re.search(r"SUMMARY:\s*(.+?)$", raw_text, re.DOTALL | re.IGNORECASE)

    if exp_match:
        explanation = exp_match.group(1).strip()
    if sum_match:
        summary = sum_match.group(1).strip()

    result["explanation"] = explanation
    result["summary"] = summary
    return result


def run_query(query: str, top_k: int = config.TOP_K) -> list[dict]:
    file_type_filter = detect_file_type_filter(query)
    if file_type_filter:
        print(f"  [query] Detected file-type filter: {file_type_filter!r}")

    try:
        results = search(query, top_k=top_k, file_type_filter=file_type_filter)
    except Exception as exc:
        print(f"\n  [ERROR] Search failed: {exc}")
        return []

    if not results:
        print("  No results found.")
        return []

    print(f"  [query] {len(results)} file(s) matched — generating explanations…")
    for i, result in enumerate(results, start=1):
        print(f"  [explain {i}/{len(results)}] {result['filename']}", end="\r", flush=True)
        explain_result(query, result)
    print()

    return results


def _fmt_score(score: float) -> str:
    filled = round(score * 10)
    bar = "█" * filled + "░" * (10 - filled)
    pct = f"{score * 100:.1f}%"
    return f"{bar} {pct}"


def _print_result(rank: int, result: dict) -> None:
    width = 70
    sep = "-" * width
    fallback_tag = " [BM25 KEYWORD MATCH]" if result.get("is_bm25_fallback") else ""
    print(f"\n{sep}")
    print(f"  #{rank}  {result['filename']}  [{result['file_type'].upper()}]{fallback_tag}")
    print(f"  Score : {_fmt_score(result['similarity_score'])}")
    print(f"  Path  : {result['path']}")

    explanation = result.get("explanation", "")
    summary = result.get("summary", "")

    if explanation:
        print(f"\n  WHY RELEVANT:\n  {explanation}")
    if summary:
        print(f"\n  WHAT IT CONTAINS:\n  {summary}")

    snippet = result.get("matched_chunk_text", "")
    if snippet:
        short = snippet[:200].replace("\n", " ↵ ")
        if len(snippet) > 200:
            short += "…"
        print(f"\n  MATCHED SNIPPET:\n  {short}")

    print(sep)


def main() -> None:
    print("\n" + "=" * 70)
    print("  Nexus — Semantic File Search (w/ BM25 Fallback)")
    print("  Type a query and press Enter. Empty query to quit.")
    print("=" * 70)

    while True:
        try:
            query = input("\nEnter your search: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not query:
            print("Goodbye.")
            break

        results = run_query(query)
        if not results:
            continue

        print(f"\n  Found {len(results)} result(s) for: \"{query}\"")
        for rank, result in enumerate(results, start=1):
            _print_result(rank, result)


if __name__ == "__main__":
    main()
