# QuickFind

Instant file search for Windows & Linux. Inspired by [Everything](https://www.voidtools.com/) — indexes your filesystem and provides sub-millisecond search results.

Built in Python with SQLite FTS5 (full-text search) and concurrent filesystem crawling. Zero external dependencies for core functionality.

## Features

- **Instant search** — sub-millisecond query times using SQLite FTS5
- **GUI + CLI** — double-click for GUI, or use from terminal
- **Concurrent indexing** — crawls filesystem in parallel using multiple threads
- **Incremental re-index** — only scans new/modified files on subsequent runs
- **Background auto-reindex** — keeps index fresh every 5 minutes
- **Cross-platform** — works on Windows and Linux
- **Multiple search modes** — prefix, exact phrase, boolean (AND/OR/NOT), regex
- **Filters** — extension, size, type (file/directory), date modified, path
- **Sorting** — by name, size, date modified, type, or relevance
- **System tray** — minimize to tray, keeps running in background
- **Global hotkey** — `Ctrl+Shift+F` to summon from anywhere
- **Dark/Light theme** — toggle with `Ctrl+T`
- **Right-click menu** — Open file, Open folder, Copy path
- **Remembers position** — window size/position saved between sessions
- **Lightweight** — single SQLite file, minimal dependencies

## Installation

### Windows (Installer)
Download `QuickFind-Setup.exe` from [Releases](https://github.com/imran-habib/quickfind/releases) — installs to Start Menu with optional desktop shortcut and startup.

### Windows (Portable)
Download `QuickFind.exe` from [Releases](https://github.com/imran-habib/quickfind/releases) — just run, no install needed.

### Linux (Portable)
Download `quickfind-linux` from [Releases](https://github.com/imran-habib/quickfind/releases):
```bash
chmod +x quickfind-linux
./quickfind-linux
```

### From Source
```bash
git clone https://github.com/imran-habib/quickfind.git
cd quickfind
python quickfind.py
```

Requires Python 3.7+.

## Quick Start

### GUI (double-click)
1. Run `QuickFind.exe` → GUI opens
2. Click **"Index Folder..."** → select your drive/folder
3. Start typing → instant results

### CLI
```bash
python quickfind.py index C:\Users\YourName
python quickfind.py search "report"
python quickfind.py interactive
```

## Usage (CLI)

```
usage: quickfind [-h] [--db DB] {index,search,interactive,i,stats} ...

QuickFind - Instant file search for Windows & Linux

positional arguments:
  {index,search,interactive,i,stats}
    index               Index filesystem paths
    search              Search indexed files
    interactive (i)     Interactive search mode
    stats               Show index statistics

options:
  -h, --help            show this help message and exit
  --db DB               Database path (default: ~/.quickfind.db)
```

### index

```bash
quickfind index C:\ D:\              # Windows
quickfind index /home /opt            # Linux
quickfind index /home -w 8            # Use 8 workers
```

### search

```bash
quickfind search "report"
quickfind search "test" --ext .py
quickfind search "config" --dirs
quickfind search "budget" --max 20
quickfind search "^test_.*\.py$" --regex
```

### interactive

```bash
quickfind interactive
quickfind i                           # shorthand
```

## GUI Features

| Feature | How to use |
|---------|-----------|
| Search | Type in search box — results update instantly |
| Filter by extension | Type extension in filter box (e.g., `.py`) |
| Filter by size | Select from Size dropdown |
| Filter by date | Select from Modified dropdown |
| Sort results | Select from Sort dropdown |
| Files/Dirs only | Check the checkboxes |
| Dark mode | Click 🌙 or press `Ctrl+T` |
| Open file | Double-click result |
| Open folder | Right-click → Open Folder |
| Copy path | Right-click → Copy Path |
| Minimize to tray | Press `Escape` or View → Minimize to Tray |
| Summon window | `Ctrl+Shift+F` (global hotkey) |
| Re-index | Click "Re-index" button |

## How it works

```
┌─────────────────────────────────────────────────────────┐
│  INDEXER (concurrent, incremental)                       │
│  os.scandir() → ThreadPoolExecutor → SQLite bulk insert │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│  SQLite DATABASE (~/.quickfind.db)                       │
│  files table + FTS5 virtual table for instant search    │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│  SEARCH ENGINE                                           │
│  FTS5 MATCH → filter → sort → results in <1ms          │
└─────────────────────────────────────────────────────────┘
```

## Performance

| Files indexed | Index time | Re-index (no changes) | Search time |
|---------------|-----------|----------------------|-------------|
| 1,000 | <1s | instant | <1ms |
| 100,000 | ~5s | ~2s | <1ms |
| 500,000 | ~20s | ~5s | <1ms |
| 1,000,000 | ~40s | ~10s | 1-2ms |

## Project structure

```
quickfind/
├── quickfind.py        # CLI entry point (launches GUI if no args)
├── gui.py              # Tkinter GUI
├── indexer.py          # Filesystem crawler + SQLite storage
├── search.py           # Search engine (FTS5 + regex + filters + sorting)
├── quickfind.ico       # App icon
├── installer.iss       # Inno Setup script for Windows installer
└── .github/workflows/  # Auto-build exe on release
```

## License

MIT
