import sqlite3
import chromadb
from pathlib import Path

# Step 1: open connections
conn = sqlite3.connect("data/metadata.db")
conn.row_factory = sqlite3.Row

images = conn.execute("SELECT path, filename, chroma_ids FROM files WHERE file_type='image'").fetchall()
print(f"Found {len(images)} image files to reset")

# Step 2: delete their vectors from ChromaDB
col = chromadb.PersistentClient(path="data/chroma").get_collection("nexus_files")
for row in images:
    if row["chroma_ids"]:
        ids = [i for i in row["chroma_ids"].split(",") if i]
        if ids:
            try:
                col.delete(ids=ids)
            except Exception as e:
                print(f"  chroma delete error: {e}")

# Step 3: delete their chunks from SQLite chunks table
for row in images:
    conn.execute("DELETE FROM chunks WHERE path=?", (row["path"],))

# Step 4: mark as pending so Phase B picks them up
conn.execute("UPDATE files SET embedding_status='pending', chroma_ids='' WHERE file_type='image'")
conn.commit()
conn.close()
print("Done — images reset to pending.")

# Step 5: Run Phase B to re-embed with synthetic chunks
import indexer
conn2 = indexer._get_db_connection()
indexer._init_db(conn2)
collection = indexer._get_chroma_collection()
print("\nRunning Phase B...")
summary = indexer.run_phase_b(conn2, collection)
conn2.close()
print(f"\nPhase B done: {summary}")

# Step 6: verify
import query_engine
print("\n=== POST-FIX SEARCH TEST ===")
for q in ["passport photo", "ID card", "college", "resume"]:
    results = query_engine.search(q, top_k=5)
    print(f"\n'{q}' -> {len(results)} results")
    for r in results:
        print(f"  {r['filename']:40} type={r['file_type']:6}  score={r['similarity_score']:.3f}")
