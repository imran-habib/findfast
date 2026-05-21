# findfast

Instant file search for Windows & Linux. Inspired by [Everything](https://www.voidtools.com/) — indexes your filesystem and provides sub-millisecond search results.

Built in Python with SQLite FTS5 (full-text search) and concurrent filesystem crawling. Zero external dependencies.

## Features

- **Instant search** — sub-millisecond query times using SQLite FTS5
- **Concurrent indexing** — crawls filesystem in parallel using multiple threads
- **Cross-platform** — works on Windows and Linux
- **Multiple search modes** — prefix, exact phrase, boolean (AND/OR/NOT), regex
- **Filters** — by extension, size, type (file/directory), path
- **Interactive mode** — real-time search as you type
- **Lightweight** — single SQLite file, no external dependencies
- **Scalable** — handles millions of files efficiently

## Installation

```bash
git clone https://github.com/imran-habib/findfast.git
cd findfast
```

Requires Python 3.7+. No pip install needed.

## Quick Start

```bash
# 1. Index your filesystem (run once)
python findfast.py index C:\          # Windows - index C: drive
python findfast.py index /home        # Linux - index home directory
python findfast.py index C:\ D:\      # Multiple drives

# 2. Search instantly
python findfast.py search "report"
python findfast.py search "budget.xlsx"

# 3. Interactive mode (real-time search)
python findfast.py interactive
```

## Usage

```
usage: findfast [-h] [--db DB] {index,search,interactive,stats} ...

Instant file search for Windows & Linux

positional arguments:
  {index,search,interactive,i,stats}
    index               Index filesystem paths
    search              Search indexed files
    interactive (i)     Interactive search mode
    stats               Show index statistics

options:
  -h, --help            show this help message and exit
  --db DB               Database path (default: ~/.findfast.db)
```

### index

Build or rebuild the file index.

```
findfast index [paths...] [-w WORKERS]

  paths       Directories to index (default: all drives on Windows, / on Linux)
  -w, --workers N   Number of concurrent crawlers (default: 4)
```

### search

One-shot search with filters.

```
findfast search <query> [options]

  query               Search query
  -n, --max N         Max results (default: 50)
  -e, --ext EXT       Filter by extension (e.g., .py, .txt)
  -d, --dirs          Show directories only
  -f, --files         Show files only
  -p, --path-contains STR   Path must contain this string
  -r, --regex         Use regex instead of FTS
  --date              Show modified date
```

### interactive

Real-time search mode — type and see results instantly.

```
findfast interactive [-n MAX] [-e EXT] [-d] [-f]
findfast i           (shorthand)
```

### stats

Show index statistics.

```
findfast stats
```

## Examples

### Basic search

```bash
$ python findfast.py search "readme"
  📄     2.1 KB  README.md  /home/user/projects/myapp
  📄     1.5 KB  README.md  /home/user/projects/utils
  📄       892 B  readme.txt  /home/user/Documents

  3 results in 0.4ms
```

### Search by extension

Find all Python files matching "test":

```bash
$ python findfast.py search "test" --ext .py
  📄     3.2 KB  test_parser.py  /home/user/projects/log-parser
  📄     1.1 KB  test_utils.py   /home/user/projects/myapp
  📄       540 B  conftest.py    /home/user/projects/myapp

  3 results in 0.5ms
```

### Find directories only

```bash
$ python findfast.py search "config" --dirs
  📁  config       /home/user/.config
  📁  config       /home/user/projects/myapp
  📁  .config      /home/user

  3 results in 0.3ms
```

### Filter by path

Find files in a specific project:

```bash
$ python findfast.py search "*.py" --path-contains "myapp"
  📄     2.3 KB  main.py     /home/user/projects/myapp/src
  📄     1.1 KB  utils.py    /home/user/projects/myapp/src
  📄       890 B  setup.py   /home/user/projects/myapp

  3 results in 0.6ms
```

### Regex search

Use full regex power:

```bash
$ python findfast.py search "^test_.*\.py$" --regex
  📄     3.2 KB  test_parser.py   /home/user/projects/log-parser
  📄     1.1 KB  test_utils.py    /home/user/projects/myapp
  📄     2.0 KB  test_search.py   /home/user/projects/findfast

  3 results in 12.3ms
```

### Exact phrase search

Use quotes for exact matching:

```bash
$ python findfast.py search '"my report"'
  📄    45.2 KB  my report 2025.docx  /home/user/Documents
  📄    12.1 KB  my report draft.pdf  /home/user/Documents

  2 results in 0.3ms
```

### Boolean search

Combine terms with AND, OR, NOT:

```bash
$ python findfast.py search "report AND 2025"
$ python findfast.py search "config OR settings"
$ python findfast.py search "test NOT mock"
```

### Show file dates

```bash
$ python findfast.py search "budget" --date
  📄    23.1 KB  2025-05-15 14:30  budget.xlsx      /home/user/Documents
  📄    18.7 KB  2025-03-01 09:15  budget_q1.xlsx   /home/user/Documents

  2 results in 0.4ms
```

### Interactive mode

```bash
$ python findfast.py interactive
findfast interactive mode (type to search, Ctrl+C to exit)

  Index: 245,831 entries (198,442 files, 47,389 dirs)
  Type to search...

> report
  📄    45.2 KB  my report 2025.docx  /home/user/Documents
  📄    12.1 KB  quarterly_report.pdf /home/user/Work
  📄     8.3 KB  report_generator.py  /home/user/projects/tools
  3 results (0.4ms)

> .env
  📄       128 B  .env         /home/user/projects/myapp
  📄       256 B  .env.example /home/user/projects/myapp
  2 results (0.3ms)

> q
Bye!
```

### Index multiple locations

```bash
# Windows - index multiple drives
python findfast.py index C:\ D:\ E:\

# Linux - index specific directories
python findfast.py index /home /opt /var/log

# Use more workers for faster indexing
python findfast.py index /home -w 8
```

### Check index stats

```bash
$ python findfast.py stats
  Total entries: 245,831
  Files:         198,442
  Directories:   47,389
  Database size: 42.3 MB
  Database path: /home/user/.findfast.db
```

## How it works

```
┌─────────────────────────────────────────────────────────┐
│  INDEXER (runs once, then update as needed)               │
│                                                           │
│  1. Scans top-level directories                           │
│  2. Spawns N threads (ThreadPoolExecutor)                 │
│  3. Each thread walks a subtree with os.walk()            │
│  4. Collects: name, full path, extension, size, mtime    │
│  5. Bulk inserts into SQLite with FTS5 virtual table      │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  SQLite DATABASE (~/.findfast.db)                         │
│                                                           │
│  files table:     id, name, path, ext, size, modified    │
│  files_fts table: FTS5 index on name, path, ext          │
│  Triggers:        Auto-sync FTS on insert/update/delete  │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  SEARCH ENGINE                                            │
│                                                           │
│  FTS mode:   MATCH query → ranked results in <1ms        │
│  Regex mode: Full table scan with re.compile()            │
│  Filters:    Applied post-query (ext, size, type, path)  │
└─────────────────────────────────────────────────────────┘
```

### Why SQLite FTS5?

- **Speed**: Sub-millisecond queries on millions of rows
- **Built-in**: Ships with Python's `sqlite3` module
- **Portable**: Single file database, no server needed
- **Powerful**: Prefix search, phrase matching, boolean operators, ranking

### Skipped directories

The indexer automatically skips system/junk directories:

- Windows: `$Recycle.Bin`, `System Volume Information`, `Windows`, `ProgramData`
- Linux: `proc`, `sys`, `dev`, `run`, `snap`
- Common: `node_modules`, `.git`, `__pycache__`, `.cache`, `.venv`

## Performance

| Files indexed | Index time | Search time | DB size |
|---------------|-----------|-------------|---------|
| 1,000 | <1s | <1ms | ~100 KB |
| 100,000 | ~5s | <1ms | ~10 MB |
| 500,000 | ~20s | <1ms | ~50 MB |
| 1,000,000 | ~40s | 1-2ms | ~100 MB |

Search is always instant regardless of index size thanks to FTS5.

## Tips

- **First run**: Index your main drives/directories once. It takes a few seconds to minutes depending on file count.
- **Re-index**: Run `findfast index` again to rebuild. Useful after major file changes.
- **Windows Terminal**: Use Windows Terminal (not cmd.exe) for color support and better Unicode rendering.
- **Custom DB location**: Use `--db /path/to/custom.db` to maintain separate indexes.
- **Combine with other tools**: Export search results and pipe to other commands.

## Project structure

```
findfast/
├── findfast.py     # CLI entry point
├── indexer.py      # Filesystem crawler + SQLite storage
├── search.py       # Search engine (FTS5 + regex + filters)
└── README.md
```

## Comparison with Everything

| Feature | Everything | findfast |
|---------|-----------|----------|
| Platform | Windows only | Windows + Linux |
| Speed | Instant (NTFS journal) | Instant (FTS5 index) |
| Index method | NTFS MFT parsing | os.walk + threads |
| Dependencies | None | Python 3.7+ |
| GUI | Yes | CLI + Interactive |
| Regex | Yes | Yes |
| Filters | Yes | Yes |
| File size | ~1.7 MB | ~15 KB source |
| Real-time updates | Yes (NTFS journal) | Manual re-index |

## License

MIT
