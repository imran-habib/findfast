"""
findfast GUI - tkinter interface with progress bar, ETA, and background auto-reindex.
"""
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog

from indexer import DEFAULT_DB, index_paths, get_indexed_paths
from search import search, get_stats, format_size

REINDEX_INTERVAL = 300  # seconds (5 minutes)


class FindFastGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("findfast - Instant File Search")
        self.root.geometry("900x600")
        self.root.minsize(600, 400)

        self._indexing = False
        self._auto_reindex_active = True

        self._build_ui()
        self._check_index()
        self._start_auto_reindex()

    def _build_ui(self):
        # Search frame
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        self.entry = ttk.Entry(top, textvariable=self.search_var, font=("Consolas", 12))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        self.entry.focus()

        # Filter frame
        filters = ttk.Frame(self.root, padding=(10, 0))
        filters.pack(fill=tk.X)

        ttk.Label(filters, text="Extension:").pack(side=tk.LEFT)
        self.ext_var = tk.StringVar()
        ext_entry = ttk.Entry(filters, textvariable=self.ext_var, width=8)
        ext_entry.pack(side=tk.LEFT, padx=(2, 10))
        self.ext_var.trace_add("write", self._on_search)

        self.files_only_var = tk.BooleanVar()
        ttk.Checkbutton(filters, text="Files only", variable=self.files_only_var,
                        command=self._on_search_btn).pack(side=tk.LEFT, padx=5)

        self.dirs_only_var = tk.BooleanVar()
        ttk.Checkbutton(filters, text="Dirs only", variable=self.dirs_only_var,
                        command=self._on_search_btn).pack(side=tk.LEFT, padx=5)

        ttk.Button(filters, text="Index Folder...", command=self._index_folder).pack(side=tk.RIGHT)
        ttk.Button(filters, text="Re-index", command=self._reindex).pack(side=tk.RIGHT, padx=5)

        # Progress frame
        progress_frame = ttk.Frame(self.root, padding=(10, 5))
        progress_frame.pack(fill=tk.X)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var,
                                            maximum=100, mode="determinate")
        self.progress_bar.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 10))

        self.progress_label = ttk.Label(progress_frame, text="", width=50)
        self.progress_label.pack(side=tk.RIGHT)

        # Status bar
        status_frame = ttk.Frame(self.root, padding=(10, 0))
        status_frame.pack(fill=tk.X)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.status_var, foreground="gray").pack(side=tk.LEFT)

        self.auto_label = ttk.Label(status_frame, text="Auto-reindex: ON", foreground="green")
        self.auto_label.pack(side=tk.RIGHT)

        # Results
        cols = ("name", "size", "path")
        self.tree = ttk.Treeview(self.root, columns=cols, show="headings")
        self.tree.heading("name", text="Name")
        self.tree.heading("size", text="Size")
        self.tree.heading("path", text="Path")
        self.tree.column("name", width=250)
        self.tree.column("size", width=80, anchor=tk.E)
        self.tree.column("path", width=500)

        scrollbar = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", self._open_location)

    def _check_index(self):
        stats = get_stats()
        if "error" in stats:
            self.status_var.set("No index. Click 'Index Folder...' to start.")
        else:
            self.status_var.set(f"Index: {stats['total_entries']:,} entries ({stats['files']:,} files, {stats['directories']:,} dirs)")

    def _update_progress(self, message, files_done, eta):
        """Called from indexer thread to update progress bar."""
        def update():
            self.progress_label.config(text=f"{message}  |  {files_done:,} files")
            if eta > 0:
                mins, secs = divmod(int(eta), 60)
                eta_str = f"{mins}m {secs}s" if mins else f"{secs}s"
                self.progress_label.config(text=f"{message}  |  {files_done:,} files  |  ETA: {eta_str}")
            # Pulse progress bar (we don't know exact total ahead of time)
            if files_done > 0:
                self.progress_bar.config(mode="indeterminate")
                self.progress_bar.start(15)
        self.root.after(0, update)

    def _index_folder(self):
        folder = filedialog.askdirectory(title="Select folder to index")
        if not folder:
            return
        self._run_index([folder], incremental=False)

    def _reindex(self):
        """Re-index previously indexed paths (incremental)."""
        paths = get_indexed_paths()
        if not paths:
            self.status_var.set("Nothing to re-index. Index a folder first.")
            return
        self._run_index(paths, incremental=True)

    def _run_index(self, paths, incremental=True):
        if self._indexing:
            return
        self._indexing = True
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(15)
        self.progress_label.config(text="Starting...")

        def do_index():
            result = index_paths(paths, callback=self._update_progress, incremental=incremental)
            self.root.after(0, lambda: self._index_done(result))

        threading.Thread(target=do_index, daemon=True).start()

    def _index_done(self, result):
        self._indexing = False
        self.progress_bar.stop()
        self.progress_bar.config(mode="determinate")
        self.progress_var.set(100)

        if result["was_incremental"]:
            msg = (f"Updated: {result['new_files']} new, {result['updated_files']} modified, "
                   f"{result['removed_files']} removed ({result['elapsed_seconds']}s)")
        else:
            msg = f"Indexed {result['total_files']:,} files in {result['elapsed_seconds']}s"

        self.progress_label.config(text=msg)
        self._check_index()

    def _start_auto_reindex(self):
        """Background auto-reindex every REINDEX_INTERVAL seconds."""
        def auto_reindex():
            while self._auto_reindex_active:
                time.sleep(REINDEX_INTERVAL)
                if not self._indexing:
                    paths = get_indexed_paths()
                    if paths:
                        self._indexing = True
                        self.root.after(0, lambda: self.auto_label.config(
                            text="Auto-reindex: running...", foreground="orange"))

                        result = index_paths(paths, callback=self._update_progress, incremental=True)

                        def done():
                            self._indexing = False
                            self.progress_bar.stop()
                            self.progress_bar.config(mode="determinate")
                            self.progress_var.set(100)
                            self.auto_label.config(text="Auto-reindex: ON", foreground="green")
                            self.progress_label.config(
                                text=f"Auto-update: +{result['new_files']} new, "
                                     f"{result['updated_files']} modified, "
                                     f"-{result['removed_files']} removed")
                            self._check_index()

                        self.root.after(0, done)

        t = threading.Thread(target=auto_reindex, daemon=True)
        t.start()

    def _on_search(self, *args):
        query = self.search_var.get().strip()
        if not query:
            self.tree.delete(*self.tree.get_children())
            return

        ext = self.ext_var.get().strip()
        if ext and not ext.startswith("."):
            ext = "." + ext

        result = search(
            query=query,
            limit=100,
            ext_filter=ext or None,
            files_only=self.files_only_var.get(),
            dirs_only=self.dirs_only_var.get(),
        )

        self.tree.delete(*self.tree.get_children())

        if result.get("error"):
            self.status_var.set(f"Error: {result['error']}")
            return

        for r in result["results"]:
            icon = "📁 " if r.is_dir else ""
            size = "" if r.is_dir else format_size(r.size)
            self.tree.insert("", tk.END, values=(
                f"{icon}{r.name}", size, os.path.dirname(r.path)
            ))

        self.status_var.set(f"{result['count']} results in {result['elapsed_ms']}ms")

    def _on_search_btn(self):
        self._on_search()

    def _open_location(self, event):
        item = self.tree.selection()
        if not item:
            return
        values = self.tree.item(item[0])["values"]
        path = values[2]
        if os.path.isdir(path):
            os.startfile(path) if os.name == "nt" else os.system(f'xdg-open "{path}"')

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self._auto_reindex_active = False
        self.root.destroy()


def launch_gui():
    app = FindFastGUI()
    app.run()


if __name__ == "__main__":
    launch_gui()
