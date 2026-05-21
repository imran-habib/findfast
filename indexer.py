"""
Filesystem indexer - fast concurrent crawling with incremental updates.
Only re-indexes files that are new or modified since last scan.
"""
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Callable

DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".quickfind.db")

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
    conn.execute("PRAGMA cache_size=-64000")
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
    # Metadata table for tracking index state
    conn.execute("""
        CREATE TABLE IF NOT EXISTS index_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
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


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM index_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO index_meta (key, value) VALUES (?,?)", (key, str(value)))
    conn.commit()


def walk_fast(root: str) -> List[tuple]:
    """Walk directory using scandir for speed."""
    entries = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
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
    """Get subdirectories for parallel crawling."""
    roots = []
    for path in paths:
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            continue
        _collect_dirs(path, depth, roots)
    return roots if roots else paths


def _collect_dirs(path: str, depth: int, result: List[str]):
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
    callback: Optional[Callable] = None,
    incremental: bool = True,
) -> dict:
    """
    Index filesystem paths.

    Args:
        paths: Directories to index
        db_path: Database path
        num_workers: Concurrent crawlers
        callback: Called with (message, files_done, total_estimate) for progress
        incremental: If True, only update changed files (much faster on re-index)
    """
    start = time.perf_counter()
    conn = get_db(db_path)

    last_index_time = float(get_meta(conn, "last_index_time", "0"))
    is_reindex = last_index_time > 0 and incremental

    if not is_reindex:
        # Full index: drop everything and rebuild
        conn.executescript("""
            DROP TRIGGER IF EXISTS files_ai;
            DROP TRIGGER IF EXISTS files_ad;
            DROP TRIGGER IF EXISTS files_au;
            DELETE FROM files;
            DELETE FROM files_fts;
        """)
        conn.commit()

    crawl_roots = get_crawl_roots(paths, depth=2)
    total_roots = len(crawl_roots)

    if callback:
        callback("Scanning filesystem...", 0, 0)

    files_processed = 0
    new_files = 0
    updated_files = 0
    removed_files = 0
    roots_done = 0

    if is_reindex:
        # Incremental: only insert/update files newer than last index
        seen_paths = set()

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {executor.submit(walk_fast, root): root for root in crawl_roots}

            for future in as_completed(futures):
                entries = future.result()
                roots_done += 1
                batch_new = []
                batch_update = []

                for entry in entries:
                    name, path, ext, size, mtime, is_dir = entry
                    seen_paths.add(path)
                    files_processed += 1

                    # Check if file exists and is unchanged
                    existing = conn.execute(
                        "SELECT modified FROM files WHERE path=?", (path,)
                    ).fetchone()

                    if existing is None:
                        batch_new.append(entry)
                        new_files += 1
                    elif abs(existing[0] - mtime) > 0.01:
                        batch_update.append(entry)
                        updated_files += 1

                # Batch insert new files
                if batch_new:
                    conn.executemany(
                        "INSERT OR IGNORE INTO files (name,path,ext,size,modified,is_dir) VALUES (?,?,?,?,?,?)",
                        batch_new,
                    )

                # Batch update modified files
                for entry in batch_update:
                    conn.execute(
                        "UPDATE files SET name=?,ext=?,size=?,modified=?,is_dir=? WHERE path=?",
                        (entry[0], entry[2], entry[3], entry[4], entry[5], entry[1]),
                    )

                conn.commit()

                # Progress with ETA
                if callback:
                    elapsed = time.perf_counter() - start
                    eta = (elapsed / roots_done) * (total_roots - roots_done) if roots_done > 0 else 0
                    callback(
                        f"Scanning... ({new_files} new, {updated_files} updated)",
                        files_processed, eta
                    )

        # Remove files that no longer exist
        if callback:
            callback("Cleaning deleted files...", files_processed, 0)

        all_indexed = conn.execute("SELECT path FROM files").fetchall()
        to_remove = [row[0] for row in all_indexed if row[0] not in seen_paths]
        if to_remove:
            removed_files = len(to_remove)
            for batch_start in range(0, len(to_remove), BATCH_SIZE):
                batch = to_remove[batch_start:batch_start + BATCH_SIZE]
                placeholders = ",".join("?" * len(batch))
                conn.execute(f"DELETE FROM files WHERE path IN ({placeholders})", batch)
            conn.commit()

    else:
        # Full index: fast bulk insert
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {executor.submit(walk_fast, root): root for root in crawl_roots}

            batch = []
            for future in as_completed(futures):
                entries = future.result()
                batch.extend(entries)
                roots_done += 1

                if len(batch) >= BATCH_SIZE:
                    conn.executemany(
                        "INSERT OR IGNORE INTO files (name,path,ext,size,modified,is_dir) VALUES (?,?,?,?,?,?)",
                        batch,
                    )
                    conn.commit()
                    files_processed += len(batch)
                    batch = []

                    if callback:
                        elapsed = time.perf_counter() - start
                        eta = (elapsed / roots_done) * (total_roots - roots_done) if roots_done > 0 else 0
                        callback(f"Indexing...", files_processed, eta)

            if batch:
                conn.executemany(
                    "INSERT OR IGNORE INTO files (name,path,ext,size,modified,is_dir) VALUES (?,?,?,?,?,?)",
                    batch,
                )
                conn.commit()
                files_processed += len(batch)

        # Rebuild FTS in one shot
        if callback:
            callback("Building search index...", files_processed, 0)

        conn.executescript("""
            INSERT INTO files_fts(rowid, name, path, ext)
            SELECT id, name, path, ext FROM files;
        """)

        # Recreate triggers
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

    # Save index timestamp and paths
    set_meta(conn, "last_index_time", time.time())
    set_meta(conn, "indexed_paths", "|".join(paths))

    elapsed = time.perf_counter() - start
    total_files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    if callback:
        callback("Done!", total_files, 0)

    return {
        "total_files": total_files,
        "new_files": new_files,
        "updated_files": updated_files,
        "removed_files": removed_files,
        "paths_indexed": paths,
        "elapsed_seconds": round(elapsed, 2),
        "db_path": db_path,
        "files_per_second": int(files_processed / elapsed) if elapsed > 0 else 0,
        "was_incremental": is_reindex,
    }


def get_indexed_paths(db_path: str = DEFAULT_DB) -> List[str]:
    """Get previously indexed paths for background re-indexing."""
    conn = get_db(db_path)
    paths_str = get_meta(conn, "indexed_paths", "")
    return paths_str.split("|") if paths_str else []
