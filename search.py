"""
Search engine - queries SQLite FTS5 for instant file search.
"""
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import List, Optional

from indexer import DEFAULT_DB, get_db


@dataclass
class SearchResult:
    name: str
    path: str
    ext: str
    size: int
    modified: float
    is_dir: bool


def format_size(size: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


# Sort options
SORT_OPTIONS = {
    "relevance": None,  # default FTS ranking
    "name_asc": lambda r: r.name.lower(),
    "name_desc": lambda r: r.name.lower(),
    "size_asc": lambda r: r.size,
    "size_desc": lambda r: r.size,
    "modified_newest": lambda r: -r.modified,
    "modified_oldest": lambda r: r.modified,
    "type": lambda r: r.ext.lower(),
}


def search(
    query: str,
    db_path: str = DEFAULT_DB,
    limit: int = 50,
    ext_filter: Optional[str] = None,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
    dirs_only: bool = False,
    files_only: bool = False,
    path_filter: Optional[str] = None,
    use_regex: bool = False,
    sort_by: str = "relevance",
    modified_after: Optional[float] = None,
    modified_before: Optional[float] = None,
) -> dict:
    """
    Search indexed files.

    Args:
        query: Search query (supports FTS5 syntax: prefix*, "exact phrase")
        db_path: Path to database
        limit: Max results
        ext_filter: Filter by extension (e.g., ".py", ".txt")
        min_size: Minimum file size in bytes
        max_size: Maximum file size in bytes
        dirs_only: Only return directories
        files_only: Only return files
        path_filter: Filter results where path contains this string
        use_regex: Treat query as regex instead of FTS
        sort_by: Sort order (relevance, name_asc, name_desc, size_asc, size_desc, modified_newest, modified_oldest, type)
        modified_after: Only files modified after this timestamp
        modified_before: Only files modified before this timestamp
    """
    if not os.path.exists(db_path):
        return {"results": [], "count": 0, "error": "No index found. Run: quickfind index <path>"}

    start = time.perf_counter()
    conn = get_db(db_path)
    conn.row_factory = sqlite3.Row

    results = []

    if use_regex:
        # Convert common glob patterns to regex
        regex_query = query
        if not any(c in query for c in ('(', '[', '{', '\\', '^', '$', '+')):
            # Looks like a glob, convert: * -> .*, ? -> .
            regex_query = query.replace('.', r'\.').replace('*', '.*').replace('?', '.')
            if not regex_query.startswith('.*'):
                regex_query = '.*' + regex_query

        rows = conn.execute(
            "SELECT name, path, ext, size, modified, is_dir FROM files"
        ).fetchall()
        try:
            pattern = re.compile(regex_query, re.IGNORECASE)
        except re.error as e:
            return {"results": [], "count": 0, "error": f"Invalid regex: {e}"}
        for row in rows:
            if pattern.search(row["name"]) or pattern.search(row["path"]):
                results.append(row)
                if len(results) >= limit * 3:
                    break
    elif query.strip() in ("*", ""):
        rows = conn.execute(
            "SELECT name, path, ext, size, modified, is_dir FROM files LIMIT ?", (limit * 3,)
        ).fetchall()
        results = rows
    else:
        fts_query = query
        if not any(c in query for c in ('"', '*', 'OR', 'AND', 'NOT')):
            terms = query.split()
            fts_query = " ".join(f"{t}*" for t in terms)

        try:
            rows = conn.execute("""
                SELECT f.name, f.path, f.ext, f.size, f.modified, f.is_dir
                FROM files f
                JOIN files_fts fts ON f.id = fts.rowid
                WHERE files_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, limit * 3)).fetchall()
        except sqlite3.OperationalError as e:
            return {"results": [], "count": 0, "error": f"Search error: {e}"}
        results = rows

    # Apply filters
    filtered = []
    for row in results:
        if ext_filter and row["ext"] != ext_filter.lower():
            continue
        if min_size is not None and (row["size"] or 0) < min_size:
            continue
        if max_size is not None and (row["size"] or 0) > max_size:
            continue
        if dirs_only and not row["is_dir"]:
            continue
        if files_only and row["is_dir"]:
            continue
        if path_filter and path_filter.lower() not in row["path"].lower():
            continue
        if modified_after is not None and (row["modified"] or 0) < modified_after:
            continue
        if modified_before is not None and (row["modified"] or 0) > modified_before:
            continue
        filtered.append(SearchResult(
            name=row["name"],
            path=row["path"],
            ext=row["ext"],
            size=row["size"] or 0,
            modified=row["modified"] or 0,
            is_dir=bool(row["is_dir"]),
        ))

    # Apply sorting
    sort_key = SORT_OPTIONS.get(sort_by)
    if sort_key:
        reverse = sort_by.endswith("_desc") or sort_by == "modified_newest"
        filtered.sort(key=sort_key, reverse=reverse)

    filtered = filtered[:limit]

    elapsed = time.perf_counter() - start

    return {
        "results": filtered,
        "count": len(filtered),
        "elapsed_ms": round(elapsed * 1000, 1),
        "error": None,
    }


def get_stats(db_path: str = DEFAULT_DB) -> dict:
    """Get index statistics."""
    if not os.path.exists(db_path):
        return {"error": "No index found."}
    conn = get_db(db_path)
    total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    files = conn.execute("SELECT COUNT(*) FROM files WHERE is_dir=0").fetchone()[0]
    dirs = conn.execute("SELECT COUNT(*) FROM files WHERE is_dir=1").fetchone()[0]
    db_size = os.path.getsize(db_path)
    return {
        "total_entries": total,
        "files": files,
        "directories": dirs,
        "db_size": format_size(db_size),
        "db_path": db_path,
    }
