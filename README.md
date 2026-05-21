# QuickFind

Instant file search for Windows & Linux. Inspired by [Everything](https://www.voidtools.com/) — indexes your filesystem and provides sub-millisecond search results.

Built in Python with SQLite FTS5 (full-text search) and concurrent filesystem crawling. Zero external dependencies for core functionality.

## Features

- **Instant search** — sub-millisecond query times using SQLite FTS5
- **GUI + CLI** — double-click for GUI, or use from terminal
- **Concurrent indexing** — crawls filesystem in parallel using multiple threads
- **Incremental re-index** — only scans new/modified files on subsequent runs
- **Auto-indexes all drives** — detects and indexes all drives on first launch
- **Background auto-reindex** — keeps index fresh every 5 minutes
- **Cross-platform** — works on Windows and Linux
- **Multiple search modes** — prefix, exact phrase, boolean (AND/OR/NOT), regex
- **Filters** — extension, size, type (file/directory), date modified, path
- **Sortable columns** — click column headers to sort (Name, Type, Size, Modified, Path)
- **Auto-fit columns** — double-click column separator to fit content
- **Duplicate file finder** — scan, review, and bulk delete duplicate files
- **System tray** — minimize to tray, keeps running in background
- **Global hotkey** — `Ctrl+Shift+F` to summon from anywhere
- **Right-click menu** — Open file, Open folder, Copy path
- **Keyboard shortcuts** — `Enter` to open, `Ctrl+C` to copy path, `Delete` to remove duplicates
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
2. First launch automatically indexes all drives
3. Start typing → instant results

### CLI
```bash
python quickfind.py index C:\Users\YourName
python quickfind.py search "report"
python quickfind.py interactive
```

## Tabs

### Search Tab

Real-time file search with filters:

| Feature | How to use |
|---------|-----------|
| Search | Type in search box — results update instantly |
| Filter by extension | Type extension in filter box (e.g., `.py`) |
| Filter by size | Select from Size dropdown |
| Filter by date | Select from Modified dropdown |
| Sort results | Click any column header (toggles ▲/▼) |
| Auto-fit column | Double-click column separator |
| Files/Dirs only | Check the checkboxes |
| Regex mode | Check "Regex" (supports globs like `*.png`) |
| Open file | Double-click result |
| Open folder | Right-click → Open Folder |
| Copy path | Right-click → Copy Path or `Ctrl+C` |

### Duplicates Tab

Find and remove duplicate files:

| Feature | How to use |
|---------|-----------|
| Scan | Click "Scan for Duplicates" |
| Select duplicates | Click files to toggle ☐/☑ |
| Select all copies | "Select All Except First" (keeps one copy) |
| Delete selected | "Delete Selected" or highlight + `Delete` key |
| Delete individual | Right-click → Delete This File |
| Multi-select | `Ctrl+Click` or `Shift+Click` then `Delete` |
| Open/inspect | Right-click → Open File / Open Folder |

**Smart filtering** — automatically skips system files (.dll, .sys, .dat, etc.) and protected directories (Windows, System32, Program Files).

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
│                                                          │
│  DUPLICATE FINDER                                        │
│  Group by size → hash candidates → group by hash        │
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
├── gui.py              # Tkinter GUI (Search + Duplicates tabs)
├── indexer.py          # Filesystem crawler + SQLite storage
├── search.py           # Search engine (FTS5 + regex + filters + sorting)
├── duplicates.py       # Duplicate file finder (size + hash grouping)
├── quickfind.ico       # App icon
├── installer.iss       # Inno Setup script for Windows installer
└── .github/workflows/  # Auto-build exe on release
```

## License

MIT
