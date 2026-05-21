"""
Filesystem indexer - fast concurrent crawling with optimized SQLite writes.
"""
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".findfast.db")

SKIP_DIRS = {
    "$Recycle.Bin", "System Volume Information", "Windows", "ProgramData",
    "proc", "sys", "dev", "run", "snap",
    "node_modules", ".git", "__pycache__", ".cache", ".venv", "venv",
}

BATCH_SIZE = 5000


def get_db(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    """Get database connection, create tables if needed."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    conn.execute("PRAGMA temp_store=MEMORY")
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


def walk_fast(root: str) -> List[tuple]:
    """Walk directory using scandir for speed. Skip stat when possible."""
    entries = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

            # Use scandir for the current directory to get DirEntry objects
            # which cache stat info on Windows (free metadata)
            try:
                with os.scandir(dirpath) as scanner:
                    for entry in scanner:
                        try:
                            is_dir = entry.is_dir(follow_symlinks=False)
                            if is_dir and entry.name in SKIP_DIRS:
                                continue
                            stat = entry.stat(follow_symlinks=False)
                            ext = "" if is_dir else os.path.splitext(entry.name)[1].lower()
                            entries.append((
                                entry.name, entry.path, ext,
                                stat.st_size, stat.st_mtime,
                                1 if is_dir else 0
                            ))
                        except (OSError, PermissionError):
                            continue
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        pass
    return entries


def get_crawl_roots(paths: List[str], depth: int = 2) -> List[str]:
    """Get subdirectories up to given depth for better work distribution."""
    roots = []
    for path in paths:
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            continue
        _collect_dirs(path, depth, roots)
    return roots if roots else paths


def _collect_dirs(path: str, depth: int, result: List[str]):
    """Recursively collect directories up to depth for parallel crawling."""
    if depth == 0:
        result.append(path)
        return
    try:
        has_subdirs = False
        with os.scandir(path) as scanner:
            for entry in scanner:
                if entry.is_dir(follow_symlinks=False) and entry.name not in SKIP_DIRS:
                    has_subdirs = True
                    _collect_dirs(entry.path, depth - 1, result)
        if not has_subdirs:
            result.append(path)
    except (OSError, PermissionError):
        result.append(path)


def index_paths(
    paths: List[str],
    db_path: str = DEFAULT_DB,
    num_workers: int = 8,
    callback=None,
) -> dict:
    """Index filesystem paths into the database."""
    start = time.perf_counter()
    conn = get_db(db_path)

    # Drop triggers and FTS during bulk insert for speed
    conn.executescript("""
        DROP TRIGGER IF EXISTS files_ai;
        DROP TRIGGER IF EXISTS files_ad;
        DROP TRIGGER IF EXISTS files_au;
        DELETE FROM files;
        DELETE FROM files_fts;
    """)
    conn.commit()

    # Get well-distributed crawl roots
    crawl_roots = get_crawl_roots(paths, depth=2)

    if callback:
        callback("Crawling filesystem...", 0)

    total_inserted = 0

    # Crawl in parallel, insert in batches as results come in
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(walk_fast, root): root for root in crawl_roots}

        batch = []
        for future in as_completed(futures):
            entries = future.result()
            batch.extend(entries)

            if len(batch) >= BATCH_SIZE:
                conn.executemany(
                    "INSERT OR IGNORE INTO files (name, path, ext, size, modified, is_dir) VALUES (?,?,?,?,?,?)",
                    batch,
                )
                conn.commit()
                total_inserted += len(batch)
                batch = []
                if callback:
                    callback("Indexing...", total_inserted)

        # Insert remaining
        if batch:
            conn.executemany(
                "INSERT OR IGNORE INTO files (name, path, ext, size, modified, is_dir) VALUES (?,?,?,?,?,?)",
                batch,
            )
            conn.commit()
            total_inserted += len(batch)

    # Rebuild FTS index in one shot (much faster than per-row triggers)
    if callback:
        callback("Building search index...", total_inserted)

    conn.executescript("""
        INSERT INTO files_fts(rowid, name, path, ext)
        SELECT id, name, path, ext FROM files;
    """)

    # Recreate triggers for future incremental updates
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

    elapsed = time.perf_counter() - start
    total_files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    if callback:
        callback("Done!", total_files)

    return {
        "total_files": total_files,
        "paths_indexed": paths,
        "elapsed_seconds": round(elapsed, 2),
        "db_path": db_path,
        "files_per_second": int(total_files / elapsed) if elapsed > 0 else 0,
    }
