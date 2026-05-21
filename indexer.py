"""
Filesystem indexer - crawls directories concurrently and stores in SQLite FTS5.
"""
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".findfast.db")

SKIP_DIRS = {
    # Windows
    "$Recycle.Bin", "System Volume Information", "Windows", "ProgramData",
    # Linux
    "proc", "sys", "dev", "run", "snap",
    # Common
    "node_modules", ".git", "__pycache__", ".cache", ".venv", "venv",
}


def get_db(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    """Get database connection, create tables if needed."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            path TEXT NOT NULL UNIQUE,
            ext TEXT,
            size INTEGER,
            modified REAL,
            is_dir INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS files_fts
        USING fts5(name, path, ext, content=files, content_rowid=id)
    """)
    # Triggers to keep FTS in sync
    conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
            INSERT INTO files_fts(rowid, name, path, ext)
            VALUES (new.id, new.name, new.path, new.ext);
        END;
        CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
            INSERT INTO files_fts(files_fts, rowid, name, path, ext)
            VALUES ('delete', old.id, old.name, old.path, old.ext);
        END;
        CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
            INSERT INTO files_fts(files_fts, rowid, name, path, ext)
            VALUES ('delete', old.id, old.name, old.path, old.ext);
            INSERT INTO files_fts(rowid, name, path, ext)
            VALUES (new.id, new.name, new.path, new.ext);
        END;
    """)
    conn.commit()
    return conn


def walk_directory(root: str) -> List[tuple]:
    """Walk a single directory tree and collect file entries."""
    entries = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip unwanted directories
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

            for name in filenames:
                filepath = os.path.join(dirpath, name)
                try:
                    stat = os.stat(filepath)
                    ext = os.path.splitext(name)[1].lower()
                    entries.append((name, filepath, ext, stat.st_size, stat.st_mtime, 0))
                except (OSError, PermissionError):
                    continue

            for name in dirnames:
                dirfullpath = os.path.join(dirpath, name)
                try:
                    stat = os.stat(dirfullpath)
                    entries.append((name, dirfullpath, "", stat.st_size, stat.st_mtime, 1))
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        pass
    return entries


def index_paths(
    paths: List[str],
    db_path: str = DEFAULT_DB,
    num_workers: int = 4,
    callback=None,
) -> dict:
    """
    Index filesystem paths into the database.

    Args:
        paths: List of root directories to index
        db_path: Path to SQLite database
        num_workers: Number of concurrent crawlers
        callback: Optional function called with (message, count) for progress

    Returns:
        Dict with stats about the indexing operation.
    """
    start = time.perf_counter()
    conn = get_db(db_path)

    # Clear existing data for fresh index
    conn.execute("DELETE FROM files")
    conn.execute("DELETE FROM files_fts")
    conn.commit()

    # Gather top-level subdirectories for parallel crawling
    crawl_roots = []
    for path in paths:
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            continue
        try:
            for entry in os.scandir(path):
                if entry.is_dir() and entry.name not in SKIP_DIRS:
                    crawl_roots.append(entry.path)
        except (OSError, PermissionError):
            pass
        # Also index files in the root itself
        crawl_roots.append(path)

    # Deduplicate (root path added alongside its children)
    # We'll handle root-level files separately
    total_files = 0

    if callback:
        callback("Crawling filesystem...", 0)

    # Crawl in parallel
    all_entries = []
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(walk_directory, root): root for root in crawl_roots}
        for future in as_completed(futures):
            entries = future.result()
            all_entries.extend(entries)
            if callback and len(all_entries) % 10000 < len(entries):
                callback("Indexing...", len(all_entries))

    # Deduplicate by path
    seen = set()
    unique_entries = []
    for entry in all_entries:
        if entry[1] not in seen:
            seen.add(entry[1])
            unique_entries.append(entry)

    # Bulk insert
    if callback:
        callback("Writing to database...", len(unique_entries))

    conn.executemany(
        "INSERT OR IGNORE INTO files (name, path, ext, size, modified, is_dir) VALUES (?,?,?,?,?,?)",
        unique_entries,
    )
    conn.commit()

    elapsed = time.perf_counter() - start
    total_files = len(unique_entries)

    if callback:
        callback("Done!", total_files)

    return {
        "total_files": total_files,
        "paths_indexed": paths,
        "elapsed_seconds": round(elapsed, 2),
        "db_path": db_path,
        "files_per_second": int(total_files / elapsed) if elapsed > 0 else 0,
    }
