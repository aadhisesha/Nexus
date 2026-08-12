"""
discovery.py — Phase 1: Recursive file-system discovery for Nexus.

Public API
----------
discover_files(folders) -> list[dict]
    Walk each folder, skip excluded dirs and unsupported extensions,
    and return a list of file-record dicts ready for indexing.

Each file-record dict contains:
    path            str   — absolute, normalised path
    filename        str   — bare filename with extension
    extension       str   — lowercase extension WITHOUT the leading dot
    file_type       str   — label from config.SUPPORTED_EXTENSIONS
    size_bytes      int   — file size in bytes at discovery time
    modified_time   float — os.path.getmtime() epoch timestamp
    discovered_at   float — epoch timestamp when this record was created

The `modified_time` field is intentionally preserved so Phase 3 (indexer)
can diff "already indexed" vs "currently discovered" records cheaply by
comparing stored vs. live modified_time values.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from pathlib import Path

import config

# ---------------------------------------------------------------------------
# Module-level logger — callers can set level/handlers as needed
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(levelname)s  %(message)s",
    level=logging.WARNING,
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core discovery function
# ---------------------------------------------------------------------------

def _scan_directory_fast(
    folder_path: str,
    discovered_at: float,
    records: list[dict],
) -> None:
    """
    High-performance recursive scanner using os.scandir.
    Leverages dirent stat caching on Windows/Linux to eliminate extra stat/resolve syscalls.
    """
    try:
        with os.scandir(folder_path) as iterator:
            for entry in iterator:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in config.EXCLUDED_DIR_NAMES:
                            _scan_directory_fast(entry.path, discovered_at, records)
                    elif entry.is_file(follow_symlinks=False):
                        filename = entry.name
                        ext = _get_extension(filename)
                        if ext in config.SUPPORTED_EXTENSIONS:
                            try:
                                stat = entry.stat()
                                abs_path = os.path.abspath(entry.path)
                                records.append({
                                    "path":          abs_path,
                                    "filename":      filename,
                                    "extension":     ext,
                                    "file_type":     config.SUPPORTED_EXTENSIONS[ext],
                                    "size_bytes":    stat.st_size,
                                    "modified_time": stat.st_mtime,
                                    "discovered_at": discovered_at,
                                })
                            except (PermissionError, OSError) as exc:
                                log.warning("Cannot stat file (%s), skipping: %s", exc, entry.path)
                except (PermissionError, OSError) as exc:
                    log.warning("Cannot access entry (%s): %s", exc, entry.path)
    except (PermissionError, OSError) as exc:
        log.warning("Cannot open directory (%s): %s", exc, folder_path)


def discover_files(folders: list[str]) -> list[dict]:
    """
    Recursively walk *folders*, returning a list of file-record dicts for
    every supported, readable file found using fast os.scandir().
    """
    records: list[dict] = []
    discovered_at = time.time()

    for root_folder in folders:
        root_path = os.path.abspath(root_folder)
        if not os.path.exists(root_path):
            log.warning("Folder does not exist, skipping: %s", root_folder)
            continue
        if not os.path.isdir(root_path):
            log.warning("Path is not a directory, skipping: %s", root_folder)
            continue

        log.info("Scanning: %s", root_path)
        _scan_directory_fast(root_path, discovered_at, records)

    return records


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _get_extension(filename: str) -> str:
    """Return the lowercase extension of *filename* WITHOUT the leading dot.

    Returns an empty string if there is no extension.
    """
    _, dot_ext = os.path.splitext(filename)
    return dot_ext.lstrip(".").lower()


def _walk_error(exc: OSError) -> None:
    """os.walk error handler — log and continue rather than raise."""
    log.warning("Cannot access directory (%s): %s", exc.strerror, exc.filename)


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def summarise(records: list[dict]) -> dict:
    """
    Build a summary dict from a list of file-record dicts.

    Returns
    -------
    dict with keys:
        total_files   int
        total_bytes   int
        by_type       dict[str, dict] — per file_type: {count, bytes}
        by_ext        dict[str, int]  — per extension: count
    """
    by_type: dict[str, dict] = defaultdict(lambda: {"count": 0, "bytes": 0})
    by_ext:  dict[str, int]  = defaultdict(int)

    for rec in records:
        ft = rec["file_type"]
        by_type[ft]["count"] += 1
        by_type[ft]["bytes"] += rec["size_bytes"]
        by_ext[rec["extension"]] += 1

    return {
        "total_files": len(records),
        "total_bytes": sum(r["size_bytes"] for r in records),
        "by_type":     dict(by_type),
        "by_ext":      dict(by_ext),
    }


def _fmt_bytes(n: int) -> str:
    """Human-readable file size (B / KB / MB / GB)."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def print_summary(records: list[dict], folders: list[str]) -> None:
    """Print a human-readable discovery summary to stdout."""
    s = summarise(records)

    print("\n" + "=" * 60)
    print("  Nexus — Discovery Summary")
    print("=" * 60)

    print(f"\nScanned folders ({len(folders)}):")
    for f in folders:
        print(f"  • {f}")

    print(f"\nTotal files found : {s['total_files']:,}")
    print(f"Total size        : {_fmt_bytes(s['total_bytes'])}")

    if s["by_type"]:
        print("\nBreakdown by file type:")
        col_w = max(len(k) for k in s["by_type"]) + 2
        for ftype, info in sorted(s["by_type"].items()):
            exts = sorted(
                ext for ext, ft in config.SUPPORTED_EXTENSIONS.items() if ft == ftype
            )
            ext_str = "  [." + ", .".join(exts) + "]"
            print(
                f"  {ftype:<{col_w}} {info['count']:>6,} files   "
                f"{_fmt_bytes(info['bytes']):>10}{ext_str}"
            )

        print("\nBreakdown by extension:")
        for ext, count in sorted(s["by_ext"].items(), key=lambda x: -x[1]):
            print(f"  .{ext:<8} {count:>6,} files")

    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run discovery on config.INDEX_FOLDERS and print a summary."""
    if not config.INDEX_FOLDERS:
        print(
            "\n[nexus] INDEX_FOLDERS is empty.\n"
            "Open config.py and add at least one folder path to INDEX_FOLDERS.\n"
        )
        return

    # Lower the log level to INFO when running as a script so the user sees
    # which folders are being scanned in real time.
    logging.getLogger().setLevel(logging.INFO)
    log.setLevel(logging.INFO)

    print(f"\n[nexus] Starting discovery across {len(config.INDEX_FOLDERS)} folder(s)…")
    t0 = time.perf_counter()

    records = discover_files(config.INDEX_FOLDERS)

    elapsed = time.perf_counter() - t0
    print(f"[nexus] Discovery completed in {elapsed:.2f}s")

    print_summary(records, config.INDEX_FOLDERS)


if __name__ == "__main__":
    main()
