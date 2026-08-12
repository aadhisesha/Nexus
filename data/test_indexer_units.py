"""Quick unit tests for indexer core logic (no Ollama / ChromaDB needed)."""
import sys

import indexer

# ── 1. Import ─────────────────────────────────────────────────────────────
print("Import OK")

# ── 2. chunk_text ──────────────────────────────────────────────────────────
chunks = indexer.chunk_text("", chunk_size=50, overlap=10)
assert chunks == [], f"Expected [] got {chunks}"

chunks = indexer.chunk_text("hello", chunk_size=100, overlap=10)
assert chunks == ["hello"], f"Expected ['hello'] got {chunks}"

text   = "abcdefghij" * 20        # 200 chars
chunks = indexer.chunk_text(text, chunk_size=50, overlap=10)
assert all(len(c) <= 50 for c in chunks), "Chunk > chunk_size"
assert len(chunks) > 1, "Should have produced multiple chunks"
assert chunks[1].startswith(chunks[0][40:50]), "Overlap not present"
print(f"chunk_text OK  ({len(chunks)} chunks from 200-char text, size=50 overlap=10)")

# ── 3. SQLite init ────────────────────────────────────────────────────────
conn = indexer._get_db_connection()
indexer._init_db(conn)
cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files'")
assert cur.fetchone() is not None, "files table not created"
print("SQLite init OK — files table exists")

# ── 4. Skip logic  ────────────────────────────────────────────────────────
conn.execute(
    "INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?)",
    ("/fake/path.pdf", "path.pdf", "pdf", "pdf", 1000, 1234567.0, 9999999.0, "id1,id2"),
)
conn.commit()
row = indexer._get_indexed_record(conn, "/fake/path.pdf")
assert row is not None
assert row["modified_time"] == 1234567.0
print("SQLite skip-logic OK — fake record inserted and retrieved")
conn.close()

# ── 5. Chunk ID determinism ───────────────────────────────────────────────
id1 = indexer._make_chunk_id("/a/b/report.pdf", 0)
id2 = indexer._make_chunk_id("/a/b/report.pdf", 0)
id3 = indexer._make_chunk_id("/a/b/report.pdf", 1)
assert id1 == id2, "chunk IDs should be deterministic"
assert id1 != id3, "different chunk_index => different ID"
print(f"Chunk ID determinism OK  ({id1!r} vs {id3!r})")

print()
print("All unit checks passed.")
