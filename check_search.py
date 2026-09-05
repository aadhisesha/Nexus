import sqlite3, query_engine, config
from pathlib import Path

conn = sqlite3.connect("data/metadata.db")
conn.row_factory = sqlite3.Row

print("=== FILES IN INDEX ===")
for row in conn.execute("SELECT filename, file_type, embedding_status FROM files ORDER BY file_type"):
    print(f"  [{row['file_type']:6}] [{row['embedding_status']:8}] {row['filename']}")

print("\n=== CHUNKS PER FILE TYPE ===")
for row in conn.execute("SELECT f.file_type, COUNT(c.id) as cnt FROM chunks c JOIN files f ON c.path=f.path GROUP BY f.file_type"):
    print(f"  {row['file_type']:10}: {row['cnt']} chunks")

conn.close()

print("\n=== SEARCH TESTS ===")
queries = [
    ("passport", None),
    ("photo", None),
    ("ID card", None),
    ("resume", None),
    ("application", None),
    ("college", None),
    ("schedule", None),
    ("photo", "image"),
]

for q, ftype in queries:
    results = query_engine.search(q, top_k=5, file_type_filter=ftype)
    label = f"'{q}'" + (f" [filter={ftype}]" if ftype else "")
    print(f"\n  {label} -> {len(results)} results")
    for r in results:
        print(f"    {r['filename']:40} type={r['file_type']:6}  score={r['similarity_score']:.3f}  bm25={r['is_bm25_fallback']}")
