"""
debug_image_pipeline.py — Standalone step-by-step diagnostic script for Nexus image pipeline.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

# Add project root to sys.path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
import discovery
import indexer
from parsers import image_parser


def main():
    print("============================================================")
    print("  STEP 1 — Image Pipeline Standalone Diagnostic")
    print("============================================================")

    # Check ollama package version
    try:
        import ollama
        version = getattr(ollama, "__version__", "unknown")
        print(f"[env] ollama Python package version: {version}")
    except ImportError:
        print("[env] FATAL: ollama package not installed in current environment!")
        return

    # Find first image file in config.INDEX_FOLDERS
    records = discovery.discover_files(config.INDEX_FOLDERS)
    image_records = [r for r in records if r["file_type"] == "image"]

    if not image_records:
        # Fallback to test_tree if no images in index folders
        test_dir = [r"data\test_tree\folder_a"]
        records = discovery.discover_files(test_dir)
        image_records = [r for r in records if r["file_type"] == "image"]

    if not image_records:
        print("[step 1a] FATAL: No image files (.png/.jpg/.jpeg) found in INDEX_FOLDERS!")
        return

    sample = image_records[0]
    filepath = sample["path"]
    filename = sample["filename"]
    ext = sample["extension"]

    print("\n--- Step 1a: File Detection & Mapping ---")
    print(f"  Sample image path : {filepath}")
    print(f"  Extension         : .{ext}")
    print(f"  Mapped file_type  : {sample['file_type']!r}")
    mapped_type = config.SUPPORTED_EXTENSIONS.get(ext.lower())
    print(f"  Config mapping    : SUPPORTED_EXTENSIONS['{ext.lower()}'] = {mapped_type!r}")
    if mapped_type != "image":
        print("  [FAIL] Extension not correctly mapped to 'image' in config!")
        return
    else:
        print("  [PASS] Extension correctly mapped to 'image'")

    print("\n--- Step 1b: Direct Ollama VLM Call (bypassing parser) ---")
    print(f"  Target VLM Model   : {config.VISION_MODEL!r}")
    print(f"  Timeout threshold  : {config.VISION_TIMEOUT_SECONDS}s")
    t0 = time.perf_counter()
    raw_vlm_content = None
    try:
        path_obj = Path(filepath).resolve()
        response = ollama.chat(
            model=config.VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": "Describe this image and transcribe any visible text.",
                    "images": [str(path_obj)],
                }
            ],
        )
        elapsed = time.perf_counter() - t0
        raw_vlm_content = response["message"]["content"]
        print(f"  [PASS] Ollama VLM responded in {elapsed:.2f}s")
        print("  --- RAW UNPARSED RESPONSE START ---")
        print(raw_vlm_content)
        print("  --- RAW UNPARSED RESPONSE END ---")
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"  [FAIL] Direct Ollama VLM call raised exception after {elapsed:.2f}s!")
        print("  --- FULL TRACEBACK ---")
        traceback.print_exc()
        print("  ----------------------")

    print("\n--- Step 1c & 1d: Call image_parser.extract_text() ---")
    t1 = time.perf_counter()
    extracted_text = ""
    try:
        extracted_text = image_parser.extract_text(filepath)
        elapsed_parser = time.perf_counter() - t1
        print(f"  extract_text() completed in {elapsed_parser:.2f}s")
        print(f"  Extracted text length: {len(extracted_text)} chars")
        print("  --- EXTRACT_TEXT() RETURN VALUE START ---")
        print(extracted_text if extracted_text else "(EMPTY STRING RETURNED)")
        print("  --- EXTRACT_TEXT() RETURN VALUE END ---")

        # Compare against 1b
        if raw_vlm_content and not extracted_text:
            print("  [FAIL] Direct VLM call produced text in 1b, but image_parser.extract_text() returned EMPTY!")
        elif extracted_text:
            print("  [PASS] image_parser produced non-empty text")
    except Exception as exc:
        print("  [FAIL] image_parser.extract_text() raised unhandled exception!")
        traceback.print_exc()

    print("\n--- Step 1e: Chunking Verification ---")
    if not extracted_text:
        print("  [SKIP] No text extracted from image, cannot chunk.")
    else:
        chunks = indexer.chunk_text(extracted_text)
        print(f"  Chunk count generated: {len(chunks)}")
        for idx, chk in enumerate(chunks, start=1):
            snippet = chk[:100].replace("\n", " ")
            print(f"    Chunk #{idx} ({len(chk)} chars): {snippet!r}...")

    print("\n--- Step 1f: ChromaDB Verification ---")
    try:
        collection = indexer._get_chroma_collection()
        all_items = collection.get(include=["metadatas", "documents"])
        metadatas = all_items.get("metadatas", [])
        documents = all_items.get("documents", [])
        ids = all_items.get("ids", [])

        image_items = [
            (id_, meta, doc)
            for id_, meta, doc in zip(ids, metadatas, documents)
            if meta and meta.get("file_type") == "image"
        ]

        file_items = [
            (id_, meta, doc)
            for id_, meta, doc in zip(ids, metadatas, documents)
            if meta and meta.get("path") == filepath
        ]

        print(f"  Total items in Chroma collection : {len(ids)}")
        print(f"  Total 'image' type items stored  : {len(image_items)}")
        print(f"  Items stored for target file     : {len(file_items)}")

        if file_items:
            print("  [PASS] Target image chunks found in ChromaDB:")
            for id_, meta, doc in file_items:
                print(f"    • ID: {id_} | Chunk: {meta.get('chunk_index')} | Text: {doc[:80]!r}...")
        else:
            print(f"  [FAIL] Target image '{filename}' has ZERO chunks stored in ChromaDB!")

    except Exception as exc:
        print("  ❌ FAIL: ChromaDB query raised exception!")
        traceback.print_exc()

    print("\n============================================================")
    print("  Diagnostic Step 1 Completed")
    print("============================================================")


if __name__ == "__main__":
    main()
