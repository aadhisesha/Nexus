import sqlite3
from pathlib import Path
import config

db = Path("data/metadata.db")
conn = sqlite3.connect(str(db))

total    = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
embedded = conn.execute("SELECT COUNT(*) FROM files WHERE embedding_status='embedded'").fetchone()[0]
pending  = conn.execute("SELECT COUNT(*) FROM files WHERE embedding_status='pending'").fetchone()[0]
chunks   = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
print(f"Files : {total} total | {embedded} embedded | {pending} pending")
print(f"Chunks: {chunks}")

print("\nSample paths:")
for row in conn.execute("SELECT path, embedding_status FROM files LIMIT 5"):
    p = Path(row[0])
    print(f"  exists={p.exists()} status={row[1]}  {row[0]}")

conn.close()

# Check ChromaDB
import chromadb
client = chromadb.PersistentClient(path="data/chroma")
try:
    col = client.get_collection("nexus_files")
    print(f"\nChromaDB count: {col.count()} vectors")
except Exception as e:
    print(f"\nChromaDB error: {e}")

# Quick search test
import query_engine
print("\nRunning test search for 'document'...")
try:
    results = query_engine.search("document", top_k=3)
    print(f"Results: {len(results)}")
    for r in results:
        print(f"  {r.get('filename')} | score={r.get('similarity_score')} | bm25={r.get('is_bm25_fallback')}")
except Exception as e:
    print(f"Search error: {e}")
