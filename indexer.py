"""
indexer.py — Phase 3: Discovery → Parsing → Chunking → Batch Embedding → Storage.

Optimized & Hardened Architecture
----------------------------------
1. discovery.discover_files()  →  list of file-record dicts
2. Incremental SQLite check    →  skip if path exists AND modified_time unchanged AND embedded
3. Two-Stage Indexing Pipeline:
   - Phase A (Fast): Parse files (CPU ProcessPool / Vision ThreadPool), split into chunks,
     store chunks & metadata in SQLite with `embedding_status = 'pending'`.
     Search is usable immediately after Phase A via BM25 keyword search!
   - Phase B (Batch Embedding): Batch embed chunks using Ollama (`ollama.embed`),
     upsert vectors into ChromaDB, and mark `embedding_status = 'embedded'`.

Resumability & Crash Safety
---------------------------
- SQLite tracks `embedding_status` ('pending' vs 'embedded') independently per file.
- If interrupted, restarting or running `--embed-only` resumes Phase B without re-parsing.

CLI Arguments
-------------
    python indexer.py [--workers WORKERS] [--embed-only]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import logging
import logging.handlers
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Callable

import config
import discovery
import parsers

# ---------------------------------------------------------------------------
# Logging — console (WARNING+) and rotating file (DEBUG+)
# ---------------------------------------------------------------------------
logging.basicConfig(format="%(levelname)s  %(message)s", level=logging.WARNING)
log = logging.getLogger(__name__)


def _setup_file_logging() -> None:
    """
    Attach a rotating file handler to the root logger so that every WARNING+
    message from any nexus module is written to logs/nexus.log.
    """
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "nexus.log"

    root_logger = logging.getLogger()
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root_logger.handlers):
        return

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=2 * 1024 * 1024,   # 2 MB per file
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root_logger.addHandler(file_handler)
    root_logger.setLevel(min(root_logger.level, logging.DEBUG))


# ---------------------------------------------------------------------------
# Chroma collection name
# ---------------------------------------------------------------------------
COLLECTION_NAME = "nexus_files"


# ===========================================================================
# 1. Chunking
# ===========================================================================

def chunk_text(
    text: str,
    chunk_size: int = config.CHUNK_SIZE,
    overlap: int = config.CHUNK_OVERLAP,
) -> list[str]:
    """
    Split *text* into overlapping character-based chunks.
    """
    text = text.strip()
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    step = max(chunk_size - overlap, 1)
    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start += step

    return chunks


# ===========================================================================
# 2. Embedding (Ollama Batch & Fallback)
# ===========================================================================

def embed_text(text: str) -> list[float]:
    """
    Generate a float embedding vector for single *text* using Ollama.
    """
    try:
        import ollama
    except ImportError as exc:
        raise RuntimeError(
            "ollama package not installed. Run: pip install ollama"
        ) from exc

    try:
        response = ollama.embeddings(model=config.EMBED_MODEL, prompt=text)
        return response["embedding"]
    except Exception as exc:
        raise RuntimeError(
            f"Ollama embedding failed (model={config.EMBED_MODEL!r}): {exc}"
        ) from exc


def embed_text_chunks(
    chunks: list[str],
    batch_size: int = getattr(config, "EMBED_BATCH_SIZE", 32),
) -> list[list[float]]:
    """
    Generate float embedding vectors for a list of text chunks.
    Batches requests to Ollama's `embed` function when supported by client library.
    Falls back to ThreadPoolExecutor if batch embedding is unavailable or fails.

    Explicitly logs embedding throughput (chunks/sec).
    """
    if not chunks:
        return []

    try:
        import ollama
    except ImportError as exc:
        raise RuntimeError("ollama package not installed. Run: pip install ollama") from exc

    can_batch = hasattr(ollama, "embed")
    if can_batch:
        log.info("[embed] Batch embedding mode active (batch_size=%d)", batch_size)
    else:
        log.info("[embed] Single-embedding ThreadPool fallback mode active")

    all_embeddings: list[list[float]] = []
    t0 = time.perf_counter()

    if can_batch:
        try:
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i : i + batch_size]
                response = ollama.embed(model=config.EMBED_MODEL, input=batch)
                all_embeddings.extend(response["embeddings"])
        except Exception as exc:
            log.warning("ollama.embed batch call failed (%s); falling back to ThreadPool", exc)
            can_batch = False
            all_embeddings = []

    if not can_batch:
        ollama_workers = getattr(config, "OLLAMA_CONCURRENCY", 4)
        all_embeddings = [[]] * len(chunks)
        with concurrent.futures.ThreadPoolExecutor(max_workers=ollama_workers) as executor:
            future_to_idx = {executor.submit(embed_text, chunk): idx for idx, chunk in enumerate(chunks)}
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                all_embeddings[idx] = future.result()

    elapsed = time.perf_counter() - t0
    rate = len(chunks) / elapsed if elapsed > 0 else 0.0
    log.info("[embed] Embedded %d chunk(s) in %.2fs (%.1f chunks/sec)", len(chunks), elapsed, rate)
    return all_embeddings


# ===========================================================================
# 3. Process Worker for CPU Parsing
# ===========================================================================

def _parse_file_task(task_args: tuple[str, str]) -> tuple[str, str, str | None]:
    """
    Top-level worker function for ProcessPoolExecutor.
    task_args: (filepath, file_type)
    Returns: (filepath, text, error_message_or_None)
    """
    filepath, file_type = task_args
    try:
        text = parsers.extract_text_by_type(filepath, file_type)
        return filepath, text, None
    except Exception as exc:
        return filepath, "", str(exc)


# ===========================================================================
# 4. SQLite helpers
# ===========================================================================

def _db_path() -> Path:
    return Path(__file__).parent / config.SQLITE_DB_PATH


def _get_db_connection() -> sqlite3.Connection:
    db_file = _db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            path             TEXT PRIMARY KEY,
            filename         TEXT NOT NULL,
            extension        TEXT NOT NULL,
            file_type        TEXT NOT NULL,
            size_bytes       INTEGER NOT NULL,
            modified_time    REAL NOT NULL,
            indexed_at       REAL NOT NULL,
            chroma_ids       TEXT NOT NULL DEFAULT '',
            embedding_status TEXT NOT NULL DEFAULT 'pending'
        )
        """
    )

    # Upgrade schema if embedding_status column is missing
    cur = conn.execute("PRAGMA table_info(files)")
    cols = [r["name"] for r in cur.fetchall()]
    if "embedding_status" not in cols:
        conn.execute("ALTER TABLE files ADD COLUMN embedding_status TEXT NOT NULL DEFAULT 'pending'")

    # Table for parsed text chunks (enables BM25 keyword search & crash-safe Phase B)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id          TEXT PRIMARY KEY,
            path        TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text        TEXT NOT NULL,
            FOREIGN KEY(path) REFERENCES files(path) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)")
    conn.commit()


def _get_indexed_record(conn: sqlite3.Connection, path: str) -> sqlite3.Row | None:
    cur = conn.execute("SELECT * FROM files WHERE path = ?", (path,))
    return cur.fetchone()


def _save_file_chunks(conn: sqlite3.Connection, path: str, chunks: list[str]) -> list[str]:
    """Save parsed text chunks for *path* in SQLite chunks table."""
    conn.execute("DELETE FROM chunks WHERE path = ?", (path,))
    chunk_ids = []
    for idx, text in enumerate(chunks):
        cid = _make_chunk_id(path, idx)
        chunk_ids.append(cid)
        conn.execute(
            "INSERT INTO chunks (id, path, chunk_index, text) VALUES (?, ?, ?, ?)",
            (cid, path, idx, text),
        )
    conn.commit()
    return chunk_ids


def _get_file_chunks(conn: sqlite3.Connection, path: str) -> list[sqlite3.Row]:
    cur = conn.execute("SELECT id, chunk_index, text FROM chunks WHERE path = ? ORDER BY chunk_index ASC", (path,))
    return cur.fetchall()


def _upsert_file_record(
    conn: sqlite3.Connection,
    file_rec: dict,
    chroma_ids: list[str],
    embedding_status: str = "pending",
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO files
            (path, filename, extension, file_type, size_bytes,
             modified_time, indexed_at, chroma_ids, embedding_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            file_rec["path"],
            file_rec["filename"],
            file_rec["extension"],
            file_rec["file_type"],
            file_rec["size_bytes"],
            file_rec["modified_time"],
            time.time(),
            ",".join(chroma_ids),
            embedding_status,
        ),
    )
    conn.commit()


# ===========================================================================
# 5. ChromaDB helpers
# ===========================================================================

def _chroma_path() -> str:
    return str(Path(__file__).parent / config.CHROMA_DB_PATH)


def _get_chroma_collection():
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError(
            "chromadb package not installed. Run: pip install chromadb"
        ) from exc

    client = chromadb.PersistentClient(path=_chroma_path())
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def _make_chunk_id(filepath: str, chunk_index: int) -> str:
    path_hash = hashlib.sha1(filepath.encode("utf-8")).hexdigest()[:12]
    return f"{path_hash}_{chunk_index}"


def _delete_old_chunks(collection, chroma_ids_str: str) -> None:
    if not chroma_ids_str:
        return
    ids = [cid for cid in chroma_ids_str.split(",") if cid]
    if ids:
        try:
            collection.delete(ids=ids)
        except Exception as exc:
            log.warning("Could not delete old Chroma chunks: %s", exc)


# ===========================================================================
# 6. Core Indexing Logic (Two-Phase Pipeline)
# ===========================================================================

def run_phase_a(
    files_to_process: list[dict],
    conn: sqlite3.Connection,
    workers: int | None = None,
) -> tuple[dict[str, str], dict[str, str], dict[str, list[str]], float]:
    """
    Phase A (Fast): Discover + Parse + Chunk + Store chunks in SQLite w/ status='pending'.
    Keyword search (BM25) is usable immediately after this step.
    """
    t_parse_start = time.perf_counter()
    cpu_count = os.cpu_count() or 4
    process_workers = workers if workers is not None else max(1, cpu_count - 1)

    parsed_results: dict[str, str] = {}
    parse_errors: dict[str, str] = {}
    file_chunks: dict[str, list[str]] = {}

    cpu_files = [f for f in files_to_process if f["file_type"] != "image"]
    image_files = [f for f in files_to_process if f["file_type"] == "image"]

    print(f"[Phase A] Parsing {len(files_to_process)} file(s) ({len(cpu_files)} CPU, {len(image_files)} Vision)...")

    # 1a. CPU Parsing
    if cpu_files:
        tasks = [(f["path"], f["file_type"]) for f in cpu_files]
        with concurrent.futures.ProcessPoolExecutor(max_workers=process_workers) as executor:
            future_to_file = {executor.submit(_parse_file_task, task): task[0] for task in tasks}
            for future in concurrent.futures.as_completed(future_to_file):
                filepath = future_to_file[future]
                try:
                    f_path, text, err = future.result()
                    if err:
                        parse_errors[filepath] = err
                    else:
                        parsed_results[filepath] = text
                except Exception as exc:
                    parse_errors[filepath] = str(exc)

    # 1b. Vision Parsing
    if image_files:
        tasks = [(f["path"], f["file_type"]) for f in image_files]
        vision_workers = 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=vision_workers) as executor:
            future_to_file = {executor.submit(_parse_file_task, task): task[0] for task in tasks}
            for future in concurrent.futures.as_completed(future_to_file):
                filepath = future_to_file[future]
                try:
                    f_path, text, err = future.result()
                    if err:
                        parse_errors[filepath] = err
                    else:
                        parsed_results[filepath] = text
                except Exception as exc:
                    parse_errors[filepath] = str(exc)

    # 1c. Chunking and saving chunks to SQLite
    for file_rec in files_to_process:
        path = file_rec["path"]
        if path in parse_errors:
            continue
        text = parsed_results.get(path, "")
        chunks = chunk_text(text) if text else []
        file_chunks[path] = chunks
        _save_file_chunks(conn, path, chunks)
        _upsert_file_record(conn, file_rec, [], embedding_status="pending")

    parsing_time = time.perf_counter() - t_parse_start
    print(
        f"[Phase A] Complete in {parsing_time:.2f}s — "
        f"{len(parsed_results)} file(s) ready for keyword (BM25) search."
    )
    return parsed_results, parse_errors, file_chunks, parsing_time


def run_phase_b(
    conn: sqlite3.Connection,
    collection: Any,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """
    Phase B (Slower, Backgroundable): Batch embed chunks for 'pending' files,
    upsert vectors into ChromaDB, and mark embedding_status = 'embedded'.
    """
    t_embed_start = time.perf_counter()

    cur = conn.execute("SELECT * FROM files WHERE embedding_status = 'pending'")
    pending_records = [dict(r) for r in cur.fetchall()]
    total_pending = len(pending_records)

    if total_pending == 0:
        print("[Phase B] No pending files to embed.")
        return {"embedded": 0, "failed": 0, "embedding_time": 0.0, "total_chunks": 0}

    print(f"[Phase B] Embedding {total_pending} file(s) in batches (batch_size={config.EMBED_BATCH_SIZE})...")

    embedded_count = 0
    failed_count = 0
    total_chunks_processed = 0

    for idx, file_rec in enumerate(pending_records, start=1):
        path = file_rec["path"]
        filename = file_rec["filename"]
        file_type = file_rec["file_type"]

        chunk_rows = _get_file_chunks(conn, path)
        chunks = [r["text"] for r in chunk_rows]

        if not chunks:
            _upsert_file_record(conn, file_rec, [], embedding_status="embedded")
            embedded_count += 1
            if progress_callback:
                progress_callback(idx, total_pending, filename)
            continue

        try:
            chunk_embeddings = embed_text_chunks(chunks)
            chunk_ids = [_make_chunk_id(path, ci) for ci in range(len(chunks))]
            metadatas = [
                {
                    "path": path,
                    "filename": filename,
                    "file_type": file_type,
                    "chunk_index": ci,
                }
                for ci in range(len(chunks))
            ]

            if file_rec.get("chroma_ids"):
                _delete_old_chunks(collection, file_rec["chroma_ids"])

            collection.upsert(
                ids=chunk_ids,
                embeddings=chunk_embeddings,
                documents=chunks,
                metadatas=metadatas,
            )

            _upsert_file_record(conn, file_rec, chunk_ids, embedding_status="embedded")
            embedded_count += 1
            total_chunks_processed += len(chunks)
            print(f"  [Phase B] [{idx}/{total_pending}] EMBEDDED {filename} ({len(chunks)} chunks)")

        except Exception as exc:
            log.error("Phase B FAIL %s — %s", filename, exc)
            print(f"  [Phase B] [{idx}/{total_pending}] FAIL     {filename} — {exc}")
            failed_count += 1

        if progress_callback:
            progress_callback(idx, total_pending, filename)

    embed_time = time.perf_counter() - t_embed_start
    rate = total_chunks_processed / embed_time if embed_time > 0 else 0.0
    print(
        f"[Phase B] Complete in {embed_time:.2f}s — "
        f"{embedded_count} file(s) embedded ({total_chunks_processed} chunks total at {rate:.1f} chunks/sec)."
    )

    return {
        "embedded": embedded_count,
        "failed": failed_count,
        "embedding_time": embed_time,
        "total_chunks": total_chunks_processed,
    }


def index_files(
    discovered_files: list[dict],
    workers: int | None = None,
    embed_only: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """
    Orchestrate discovery → Phase A (Fast keyword) → Phase B (Batch embed & semantic upgrade).
    """
    t_start = time.perf_counter()

    conn = _get_db_connection()
    _init_db(conn)

    collection = _get_chroma_collection()

    # ── Prune stale records (files deleted from disk or removed from INDEX_FOLDERS) ──
    if not embed_only:
        cur = conn.execute("SELECT path, chroma_ids FROM files")
        stored_rows = cur.fetchall()
        discovered_paths = {f["path"] for f in discovered_files}
        prune_count = 0

        for row in stored_rows:
            p = row["path"]
            if p not in discovered_paths or not Path(p).exists():
                log.info("Pruning missing/deleted file from index: %s", p)
                if row["chroma_ids"]:
                    _delete_old_chunks(collection, row["chroma_ids"])
                conn.execute("DELETE FROM chunks WHERE path = ?", (p,))
                conn.execute("DELETE FROM files WHERE path = ?", (p,))
                prune_count += 1

        if prune_count > 0:
            conn.commit()
            print(f"[indexer] Pruned {prune_count} missing/deleted file(s) from index.")


    # ── Embed-only mode (--embed-only CLI flag) ─────────────────────────────
    if embed_only:
        print("[indexer] Running in --embed-only mode: resuming Phase B for pending files.")
        summary_b = run_phase_b(conn, collection, progress_callback=progress_callback)
        conn.close()
        return {
            "indexed": summary_b["embedded"],
            "skipped": 0,
            "failed": summary_b["failed"],
            "by_type": {},
            "failed_files": [],
            "parsing_time": 0.0,
            "embedding_time": summary_b["embedding_time"],
            "total_time": time.perf_counter() - t_start,
        }

    # ── Standard pipeline ───────────────────────────────────────────────────
    files_to_process: list[dict] = []
    skipped_count = 0

    for file_rec in discovered_files:
        path = file_rec["path"]
        existing = _get_indexed_record(conn, path)
        if existing and existing["modified_time"] == file_rec["modified_time"] and existing["embedding_status"] == "embedded":
            skipped_count += 1
        else:
            files_to_process.append(file_rec)

    if not files_to_process:
        # Check if any files were left pending from an interrupted run
        pending_check = conn.execute("SELECT COUNT(*) FROM files WHERE embedding_status = 'pending'").fetchone()[0]
        if pending_check > 0:
            print(f"[indexer] All {len(discovered_files)} files discovered, but {pending_check} file(s) are pending embeddings. Resuming Phase B...")
            summary_b = run_phase_b(conn, collection, progress_callback=progress_callback)
            conn.close()
            return {
                "indexed": summary_b["embedded"],
                "skipped": skipped_count,
                "failed": summary_b["failed"],
                "by_type": {},
                "failed_files": [],
                "parsing_time": 0.0,
                "embedding_time": summary_b["embedding_time"],
                "total_time": time.perf_counter() - t_start,
            }

        print(f"[indexer] All {len(discovered_files)} file(s) are up to date and embedded — skipping.")
        conn.close()
        return {
            "indexed": 0,
            "skipped": skipped_count,
            "failed": 0,
            "by_type": {},
            "failed_files": [],
            "parsing_time": 0.0,
            "embedding_time": 0.0,
            "total_time": time.perf_counter() - t_start,
        }

    # ── Execute Phase A ─────────────────────────────────────────────────────
    parsed_results, parse_errors, file_chunks, parsing_time = run_phase_a(files_to_process, conn, workers=workers)

    # ── Execute Phase B ─────────────────────────────────────────────────────
    summary_b = run_phase_b(conn, collection, progress_callback=progress_callback)

    by_type: dict[str, int] = {}
    for f in files_to_process:
        if f["path"] not in parse_errors:
            ft = f["file_type"]
            by_type[ft] = by_type.get(ft, 0) + 1

    failed_files = [(Path(p).name, err) for p, err in parse_errors.items()]

    total_time = time.perf_counter() - t_start
    conn.close()

    return {
        "indexed": summary_b["embedded"],
        "skipped": skipped_count,
        "failed": len(parse_errors) + summary_b["failed"],
        "by_type": by_type,
        "failed_files": failed_files,
        "parsing_time": parsing_time,
        "embedding_time": summary_b["embedding_time"],
        "total_time": total_time,
    }


# ===========================================================================
# 7. CLI Entry Point
# ===========================================================================

def main() -> None:
    """CLI entry point for Nexus Indexer."""
    _setup_file_logging()

    parser = argparse.ArgumentParser(description="Nexus Two-Phase Semantic Indexer")
    parser.add_argument(
        "-w", "--workers", type=int, default=None,
        help="Override CPU process pool worker counts"
    )
    parser.add_argument(
        "--embed-only", action="store_true",
        help="Skip discovery & parsing; resume Phase B embedding for pending files in SQLite"
    )
    args = parser.parse_args()

    if not config.INDEX_FOLDERS and not args.embed_only:
        print(
            "\n[indexer] INDEX_FOLDERS is empty.\n"
            "Open config.py and add at least one folder path to INDEX_FOLDERS.\n"
        )
        return

    log.info("=== Indexer run started (workers=%s, embed_only=%s) ===", args.workers, args.embed_only)

    if args.embed_only:
        summary = index_files([], workers=args.workers, embed_only=True)
    else:
        print(f"\n[indexer] Starting discovery across {len(config.INDEX_FOLDERS)} folder(s)...")
        t0 = time.perf_counter()
        discovered = discovery.discover_files(config.INDEX_FOLDERS)
        log.info("Discovery complete: %d file(s) found", len(discovered))
        print(f"[indexer] Discovered {len(discovered)} supported file(s) in {time.perf_counter() - t0:.2f}s\n")
        summary = index_files(discovered, workers=args.workers, embed_only=False)

    print()
    print("=" * 60)
    print("  Nexus Indexer — Summary")
    print("=" * 60)
    print(f"  Indexed (embedded)     : {summary['indexed']:>4}")
    print(f"  Skipped (unchanged)    : {summary['skipped']:>4}")
    print(f"  Failed                 : {summary['failed']:>4}")

    if summary.get("by_type"):
        print("\n  Indexed Breakdown by File Type:")
        for ft, count in sorted(summary["by_type"].items()):
            print(f"    • {ft:<10} : {count:>4} file(s)")

    if summary.get("failed_files"):
        print("\n  Failed Files List:")
        for fn, reason in summary["failed_files"]:
            print(f"    ❌ {fn:<25} — {reason}")

    print("\n  Performance & Timing Breakdown:")
    print(f"    • Parsing stage (Phase A): {summary.get('parsing_time', 0.0):>6.2f}s")
    print(f"    • Embedding stage (Phase B): {summary.get('embedding_time', 0.0):>6.2f}s")
    print(f"    • Total time elapsed     : {summary.get('total_time', 0.0):>6.2f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
