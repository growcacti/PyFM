import csv
import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
import unicodedata
import uuid
from tkinter import filedialog, messagebox, ttk
from tkinter import ttk, filedialog, messagebox
#!/usr/bin/env python3
"""PyFile_Manager_JH: integrated explorer, housekeeping, rename and collection tools."""
import queue
import json
import time
import csv
import threading
import webbrowser
from urllib.parse import urlsplit, unquote

class ToolFrame(tk.Frame):
    """Deliver worker callbacks through a queue polled by the Tk main thread."""
    def __init__(self, master):
        super().__init__(master)
        self._callbacks = queue.Queue()
        tk.Frame.after(self, 80, self._poll_callbacks)
    def _poll_callbacks(self):
        for _ in range(100):
            try:
                callback, args = self._callbacks.get_nowait()
            except queue.Empty:
                break
            callback(*args)
        tk.Frame.after(self, 80, self._poll_callbacks)
    def after(self, ms, func=None, *args):
        if threading.current_thread() is not threading.main_thread():
            if func is not None:
                self._callbacks.put((func, args))
            return None
        return super().after(ms, func, *args)

'\nFolder Housekeeper / Explorer\n-----------------------------\nScan a directory recursively and report folder statistics.\n\nFeatures:\n- Empty/non-empty folder reporting\n- Direct item count\n- Recursive file/subfolder counts\n- Recursive folder size\n- Modified and created/change dates\n- Click any column heading to sort\n- Select a folder in "All Folders" to automatically show its direct contents\n- Direct Contents tab shows files and subfolders with type, size and dates\n- Open folder/item, copy path, rename, create folder, copy/move items\n- Safe empty-folder deletion using os.rmdir()\n- CSV report export\n- Duplicate-file finder using size + SHA-256 verification\n- Recursive or current-folder-only duplicate scans\n- Numbered-copy finder for names such as file (1).txt\n- Zero-byte and temporary-file cleanup candidates\n- Safe quarantine option before permanent deletion\n\nUses only the Python standard library.\n'

def human_size(num_bytes):
    """Return a human-readable file size."""
    size = float(num_bytes)
    units = ('B', 'KB', 'MB', 'GB', 'TB', 'PB')
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == 'B':
                return f'{int(size)} {unit}'
            return f'{size:.2f} {unit}'
        size /= 1024.0

def format_time(timestamp):
    if not timestamp:
        return ''
    try:
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    except (OSError, OverflowError, ValueError):
        return ''

def get_created_time(stat_result):
    """
    Return the best available creation-style timestamp.

    On Windows, st_ctime is creation time. On many Unix/Linux systems,
    st_birthtime is used when available; otherwise st_ctime is metadata
    change time rather than true creation time.
    """
    if hasattr(stat_result, 'st_birthtime'):
        return stat_result.st_birthtime
    return stat_result.st_ctime

def open_in_file_manager(path):
    path = str(path)
    try:
        if sys.platform.startswith('win'):
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception as exc:
        messagebox.showerror('Could not open', str(exc))

class FolderInfo:

    def __init__(self, path, direct_items=0, file_count=0, folder_count=0, total_size=0, modified=0, created=0, is_empty=False, error=''):
        self.path = Path(path)
        self.direct_items = direct_items
        self.file_count = file_count
        self.folder_count = folder_count
        self.total_size = total_size
        self.modified = modified
        self.created = created
        self.is_empty = is_empty
        self.error = error

class DuplicateInfo:

    def __init__(self, path, size=0, modified=0, group='', digest='', reason=''):
        self.path = Path(path)
        self.size = size
        self.modified = modified
        self.group = group
        self.digest = digest
        self.reason = reason

class FolderHousekeeper(ToolFrame):

    def __init__(self, master):
        super().__init__(master)
        self.folder_results = []
        self.scan_thread = None
        self.sort_reverse = {}
        self.current_contents_folder = None
        self.contents_paths = {}
        self.duplicate_paths = {}
        self.cleanup_paths = {}
        self.duplicate_results = []
        self.cleanup_results = []
        self.duplicate_thread = None
        self.path_var = tk.StringVar()
        self.status_var = tk.StringVar(value='Choose a folder to scan.')
        self.summary_var = tk.StringVar(value='No scan has been run.')
        self.contents_title_var = tk.StringVar(value='Select a folder in All Folders to view its direct contents.')
        self.include_root_var = tk.BooleanVar(value=False)
        self.dup_recursive_var = tk.BooleanVar(value=True)
        self.find_numbered_var = tk.BooleanVar(value=True)
        self.find_zero_var = tk.BooleanVar(value=True)
        self.find_temp_var = tk.BooleanVar(value=True)
        self.dup_status_var = tk.StringVar(value='Choose a folder, then scan for duplicates.')
        self.cleanup_status_var = tk.StringVar(value='Cleanup candidates have not been scanned yet.')
        self._build_gui()

    def _build_gui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        top = ttk.LabelFrame(self, text='Folder to scan')
        top.grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 5))
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text='Directory:').grid(row=0, column=0, padx=(8, 5), pady=8, sticky='w')
        ttk.Entry(top, textvariable=self.path_var).grid(row=0, column=1, padx=5, pady=8, sticky='ew')
        ttk.Button(top, text='Browse...', command=self.choose_folder).grid(row=0, column=2, padx=5, pady=8)
        self.scan_button = ttk.Button(top, text='Scan Folders', command=self.start_scan)
        self.scan_button.grid(row=0, column=3, padx=(5, 8), pady=8)
        ttk.Checkbutton(top, text='Include selected root folder in results', variable=self.include_root_var).grid(row=1, column=1, columnspan=3, padx=5, pady=(0, 8), sticky='w')
        summary = ttk.Frame(self)
        summary.grid(row=1, column=0, sticky='ew', padx=10, pady=5)
        summary.columnconfigure(0, weight=1)
        ttk.Label(summary, textvariable=self.summary_var, font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky='w')
        self.progress = ttk.Progressbar(summary, mode='indeterminate', length=180)
        self.progress.grid(row=0, column=1, padx=(10, 0), sticky='e')
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=2, column=0, sticky='nsew', padx=10, pady=5)
        self.empty_tab = ttk.Frame(self.notebook)
        self.all_tab = ttk.Frame(self.notebook)
        self.contents_tab = ttk.Frame(self.notebook)
        self.duplicates_tab = ttk.Frame(self.notebook)
        self.cleanup_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.empty_tab, text='Empty Folders')
        self.notebook.add(self.all_tab, text='All Folders')
        self.notebook.add(self.contents_tab, text='Direct Contents')
        self.notebook.add(self.duplicates_tab, text='Duplicate Files')
        self.notebook.add(self.cleanup_tab, text='Cleanup Candidates')
        self.empty_tree = self._make_tree(self.empty_tab, columns=('path', 'modified', 'created'), headings=('Empty Folder', 'Modified', 'Created / Changed'), widths=(760, 170, 170))
        self.all_tree = self._make_tree(self.all_tab, columns=('status', 'path', 'direct', 'files', 'folders', 'size', 'modified', 'created'), headings=('Status', 'Folder', 'Direct Items', 'Files', 'Subfolders', 'Size', 'Modified', 'Created / Changed'), widths=(90, 500, 95, 80, 95, 110, 165, 165))
        self.all_tree.bind('<<TreeviewSelect>>', self.on_all_folder_selected)
        self.all_tree.bind('<Double-1>', lambda _event: self.open_selected_folder())
        self._build_contents_tab()
        self._build_duplicates_tab()
        self._build_cleanup_tab()
        controls = ttk.Frame(self)
        controls.grid(row=3, column=0, sticky='ew', padx=10, pady=5)
        controls.columnconfigure(7, weight=1)
        ttk.Button(controls, text='Select All Empty', command=self.select_all_empty).grid(row=0, column=0, padx=(0, 5))
        ttk.Button(controls, text='Clear Selection', command=self.clear_empty_selection).grid(row=0, column=1, padx=5)
        self.delete_button = ttk.Button(controls, text='Delete Selected Empty Folders', command=self.delete_selected_empty)
        self.delete_button.grid(row=0, column=2, padx=5)
        ttk.Separator(controls, orient='vertical').grid(row=0, column=3, sticky='ns', padx=8)
        ttk.Button(controls, text='Open Selected Folder', command=self.open_selected_folder).grid(row=0, column=4, padx=5)
        ttk.Button(controls, text='Copy Folder Path', command=self.copy_selected_folder_path).grid(row=0, column=5, padx=5)
        ttk.Button(controls, text='Export Report...', command=self.export_report).grid(row=0, column=6, padx=5)
        status = ttk.Label(self, textvariable=self.status_var, relief='sunken', anchor='w')
        status.grid(row=4, column=0, sticky='ew', padx=10, pady=(5, 10))

    def _build_contents_tab(self):
        self.contents_tab.columnconfigure(0, weight=1)
        self.contents_tab.rowconfigure(1, weight=1)
        bar = ttk.Frame(self.contents_tab)
        bar.grid(row=0, column=0, columnspan=2, sticky='ew', padx=6, pady=(6, 3))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, textvariable=self.contents_title_var, font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky='w', padx=(2, 8))
        ttk.Button(bar, text='Refresh', command=self.refresh_contents).grid(row=0, column=1, padx=3)
        ttk.Button(bar, text='Up One Folder', command=self.contents_up_one).grid(row=0, column=2, padx=3)
        frame = ttk.Frame(self.contents_tab)
        frame.grid(row=1, column=0, sticky='nsew', padx=6, pady=3)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.contents_tree = self._make_tree(frame, columns=('name', 'type', 'size', 'modified', 'created', 'fullpath'), headings=('Name', 'Type', 'Size', 'Modified', 'Created / Changed', 'Full Path'), widths=(300, 100, 110, 165, 165, 500))
        self.contents_tree.bind('<Double-1>', self.on_contents_double_click)
        buttons = ttk.Frame(self.contents_tab)
        buttons.grid(row=2, column=0, sticky='ew', padx=6, pady=(3, 7))
        ttk.Button(buttons, text='Open', command=self.open_selected_item).grid(row=0, column=0, padx=3)
        ttk.Button(buttons, text='Copy Path', command=self.copy_selected_item_path).grid(row=0, column=1, padx=3)
        ttk.Button(buttons, text='New Folder...', command=self.create_new_folder).grid(row=0, column=2, padx=3)
        ttk.Button(buttons, text='Rename...', command=self.rename_selected_item).grid(row=0, column=3, padx=3)
        ttk.Button(buttons, text='Copy To...', command=self.copy_selected_items).grid(row=0, column=4, padx=3)
        ttk.Button(buttons, text='Move To...', command=self.move_selected_items).grid(row=0, column=5, padx=3)

    def _build_duplicates_tab(self):
        self.duplicates_tab.columnconfigure(0, weight=1)
        self.duplicates_tab.rowconfigure(2, weight=1)
        options = ttk.LabelFrame(self.duplicates_tab, text='Duplicate scan options')
        options.grid(row=0, column=0, sticky='ew', padx=6, pady=6)
        ttk.Checkbutton(options, text='Scan subfolders recursively', variable=self.dup_recursive_var).grid(row=0, column=0, padx=6, pady=5, sticky='w')
        ttk.Button(options, text='Find Exact Duplicates', command=self.start_duplicate_scan).grid(row=0, column=1, padx=6, pady=5)
        ttk.Label(options, text='Exact duplicates are verified by SHA-256; matching names alone are never enough.').grid(row=0, column=2, padx=8, pady=5, sticky='w')
        ttk.Label(self.duplicates_tab, textvariable=self.dup_status_var).grid(row=1, column=0, sticky='ew', padx=8, pady=(0, 4))
        frame = ttk.Frame(self.duplicates_tab)
        frame.grid(row=2, column=0, sticky='nsew', padx=6, pady=3)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.duplicate_tree = self._make_tree(frame, columns=('group', 'name', 'size', 'modified', 'folder', 'fullpath'), headings=('Group', 'File', 'Size', 'Modified', 'Folder', 'Full Path'), widths=(80, 260, 110, 165, 330, 520))
        self.duplicate_tree.bind('<Double-1>', lambda _e: self.open_selected_duplicate())
        buttons = ttk.Frame(self.duplicates_tab)
        buttons.grid(row=3, column=0, sticky='ew', padx=6, pady=(3, 7))
        ttk.Button(buttons, text='Select All But First in Each Group', command=self.select_duplicate_extras).grid(row=0, column=0, padx=3)
        ttk.Button(buttons, text='Clear Selection', command=lambda: self.duplicate_tree.selection_remove(self.duplicate_tree.selection())).grid(row=0, column=1, padx=3)
        ttk.Button(buttons, text='Open', command=self.open_selected_duplicate).grid(row=0, column=2, padx=3)
        ttk.Button(buttons, text='Copy Path', command=self.copy_duplicate_paths).grid(row=0, column=3, padx=3)
        ttk.Button(buttons, text='Move Selected to Quarantine...', command=self.quarantine_selected_duplicates).grid(row=0, column=4, padx=3)
        ttk.Button(buttons, text='Delete Selected Permanently...', command=self.delete_selected_duplicates).grid(row=0, column=5, padx=3)

    def _build_cleanup_tab(self):
        self.cleanup_tab.columnconfigure(0, weight=1)
        self.cleanup_tab.rowconfigure(2, weight=1)
        options = ttk.LabelFrame(self.cleanup_tab, text='Housekeeping scan')
        options.grid(row=0, column=0, sticky='ew', padx=6, pady=6)
        ttk.Checkbutton(options, text='Numbered copies: name (1).ext', variable=self.find_numbered_var).grid(row=0, column=0, padx=6, pady=5, sticky='w')
        ttk.Checkbutton(options, text='Zero-byte files', variable=self.find_zero_var).grid(row=0, column=1, padx=6, pady=5, sticky='w')
        ttk.Checkbutton(options, text='Temporary/backup files', variable=self.find_temp_var).grid(row=0, column=2, padx=6, pady=5, sticky='w')
        ttk.Button(options, text='Scan Cleanup Candidates', command=self.scan_cleanup_candidates).grid(row=0, column=3, padx=6, pady=5)
        ttk.Label(self.cleanup_tab, textvariable=self.cleanup_status_var).grid(row=1, column=0, sticky='ew', padx=8, pady=(0, 4))
        frame = ttk.Frame(self.cleanup_tab)
        frame.grid(row=2, column=0, sticky='nsew', padx=6, pady=3)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.cleanup_tree = self._make_tree(frame, columns=('reason', 'name', 'size', 'modified', 'folder', 'fullpath'), headings=('Reason', 'File', 'Size', 'Modified', 'Folder', 'Full Path'), widths=(180, 270, 100, 165, 330, 520))
        self.cleanup_tree.bind('<Double-1>', lambda _e: self.open_selected_cleanup())
        buttons = ttk.Frame(self.cleanup_tab)
        buttons.grid(row=3, column=0, sticky='ew', padx=6, pady=(3, 7))
        ttk.Button(buttons, text='Open', command=self.open_selected_cleanup).grid(row=0, column=0, padx=3)
        ttk.Button(buttons, text='Copy Path', command=self.copy_cleanup_paths).grid(row=0, column=1, padx=3)
        ttk.Button(buttons, text='Move Selected to Quarantine...', command=self.quarantine_selected_cleanup).grid(row=0, column=2, padx=3)
        ttk.Button(buttons, text='Delete Selected Permanently...', command=self.delete_selected_cleanup).grid(row=0, column=3, padx=3)

    def _make_tree(self, parent, columns, headings, widths):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        tree = ttk.Treeview(parent, columns=columns, show='headings', selectmode='extended')
        tree._base_headings = dict(zip(columns, headings))
        for col, heading, width in zip(columns, headings, widths):
            tree.heading(col, text=heading, command=lambda c=col, t=tree: self.sort_tree(t, c))
            anchor = 'e' if col in {'direct', 'files', 'folders', 'size'} else 'w'
            tree.column(col, width=width, minwidth=60, anchor=anchor)
        yscroll = ttk.Scrollbar(parent, orient='vertical', command=tree.yview)
        xscroll = ttk.Scrollbar(parent, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky='nsew')
        yscroll.grid(row=0, column=1, sticky='ns')
        xscroll.grid(row=1, column=0, sticky='ew')
        return tree

    def sort_tree(self, tree, column):
        """Sort a Treeview by clicking a column heading; repeated click reverses it."""
        key_id = (str(tree), column)
        reverse = self.sort_reverse.get(key_id, False)
        rows = []
        for item in tree.get_children(''):
            value = tree.set(item, column)
            rows.append((self._sort_value(column, value), item))
        rows.sort(key=lambda pair: pair[0], reverse=reverse)
        for index, (_value, item) in enumerate(rows):
            tree.move(item, '', index)
        self.sort_reverse[key_id] = not reverse
        for col, title in tree._base_headings.items():
            tree.heading(col, text=title)
        arrow = ' ▼' if reverse else ' ▲'
        tree.heading(column, text=tree._base_headings[column] + arrow)

    @staticmethod
    def _sort_value(column, value):
        text = str(value).strip()
        if column in {'direct', 'files', 'folders'}:
            try:
                return (0, int(text.replace(',', '')))
            except ValueError:
                return (1, 0)
        if column == 'size':
            units = {'B': 1, 'KB': 1024, 'MB': 1024 ** 2, 'GB': 1024 ** 3, 'TB': 1024 ** 4, 'PB': 1024 ** 5}
            parts = text.split()
            if len(parts) == 2:
                try:
                    return (0, float(parts[0]) * units.get(parts[1].upper(), 1))
                except ValueError:
                    pass
            return (1, 0)
        if column in {'modified', 'created'}:
            try:
                return (0, datetime.strptime(text, '%Y-%m-%d %H:%M:%S'))
            except ValueError:
                return (1, datetime.min)
        return (0, text.casefold())

    def choose_folder(self):
        folder = filedialog.askdirectory(title='Choose folder to scan')
        if folder:
            self.path_var.set(folder)

    def start_scan(self):
        root_text = self.path_var.get().strip()
        if not root_text:
            messagebox.showwarning('No folder selected', 'Choose a folder before scanning.')
            return
        root = Path(root_text)
        if not root.exists() or not root.is_dir():
            messagebox.showerror('Invalid folder', 'The selected folder does not exist or is not a directory.')
            return
        if self.scan_thread and self.scan_thread.is_alive():
            return
        self.folder_results.clear()
        self.empty_tree.delete(*self.empty_tree.get_children())
        self.all_tree.delete(*self.all_tree.get_children())
        self.contents_tree.delete(*self.contents_tree.get_children())
        self.contents_paths.clear()
        self.current_contents_folder = None
        self.contents_title_var.set('Select a folder in All Folders to view its direct contents.')
        self.scan_button.configure(state='disabled')
        self.delete_button.configure(state='disabled')
        self.progress.start(10)
        self.status_var.set(f'Scanning: {root}')
        self.summary_var.set('Scanning folders...')
        self.scan_thread = threading.Thread(target=self._scan_worker, args=(root, self.include_root_var.get()), daemon=True)
        self.scan_thread.start()

    def _scan_worker(self, root, include_root):
        results = []
        errors = []
        try:
            for current_dir, _dirnames, _filenames in os.walk(root, topdown=False, followlinks=False):
                current_path = Path(current_dir)
                if current_path == root and (not include_root):
                    continue
                total_size = 0
                file_count = 0
                folder_count = 0
                error_text = ''
                modified = 0
                created = 0
                try:
                    try:
                        st = current_path.stat()
                        modified = st.st_mtime
                        created = get_created_time(st)
                    except (OSError, PermissionError):
                        pass
                    for walk_dir, subdirs, files in os.walk(current_path, topdown=True, followlinks=False):
                        folder_count += len(subdirs)
                        for filename in files:
                            file_path = Path(walk_dir) / filename
                            try:
                                if file_path.is_symlink():
                                    continue
                                total_size += file_path.stat().st_size
                                file_count += 1
                            except (OSError, PermissionError):
                                pass
                    try:
                        direct_items = len(list(os.scandir(current_path)))
                    except (OSError, PermissionError) as exc:
                        direct_items = 0
                        error_text = str(exc)
                    results.append(FolderInfo(path=current_path, direct_items=direct_items, file_count=file_count, folder_count=folder_count, total_size=total_size, modified=modified, created=created, is_empty=direct_items == 0 and (not error_text), error=error_text))
                except (OSError, PermissionError) as exc:
                    errors.append(f'{current_path}: {exc}')
        except Exception as exc:
            errors.append(str(exc))
        results.sort(key=lambda item: str(item.path).casefold())
        self.after(0, self._scan_complete, results, errors)

    def _scan_complete(self, results, errors):
        self.progress.stop()
        self.scan_button.configure(state='normal')
        self.delete_button.configure(state='normal')
        self.folder_results = results
        empty_count = nonempty_count = total_bytes = 0
        for info in results:
            if info.is_empty:
                empty_count += 1
                status = 'EMPTY'
                self.empty_tree.insert('', 'end', values=(str(info.path), format_time(info.modified), format_time(info.created)))
            elif info.error:
                status = 'ERROR'
            else:
                nonempty_count += 1
                status = 'Has files'
            total_bytes += info.total_size
            self.all_tree.insert('', 'end', values=(status, str(info.path), info.direct_items, info.file_count, info.folder_count, human_size(info.total_size), format_time(info.modified), format_time(info.created)))
        self.summary_var.set(f'Folders scanned: {len(results):,}    Empty: {empty_count:,}    Non-empty: {nonempty_count:,}    Combined reported size: {human_size(total_bytes)}')
        self.status_var.set(f'Scan finished with {len(errors)} access/error message(s).' if errors else 'Scan finished. Click a column heading to sort.')

    def on_all_folder_selected(self, _event=None):
        selected = self.all_tree.selection()
        if not selected:
            return
        path = Path(self.all_tree.item(selected[0], 'values')[1])
        self.load_contents(path)

    def load_contents(self, folder):
        folder = Path(folder)
        self.contents_tree.delete(*self.contents_tree.get_children())
        self.contents_paths.clear()
        self.current_contents_folder = folder
        self.contents_title_var.set(f'Direct contents of: {folder}')
        try:
            entries = list(folder.iterdir())
        except (OSError, PermissionError) as exc:
            self.status_var.set(f'Could not read {folder}: {exc}')
            return
        entries.sort(key=lambda p: (not p.is_dir(), p.name.casefold()))
        folders = files = 0
        for path in entries:
            try:
                st = path.stat()
                is_dir = path.is_dir()
                if is_dir:
                    item_type = 'Folder'
                    size_text = ''
                    folders += 1
                elif path.is_symlink():
                    item_type = 'Link'
                    size_text = human_size(st.st_size)
                    files += 1
                else:
                    item_type = path.suffix[1:].upper() + ' File' if path.suffix else 'File'
                    size_text = human_size(st.st_size)
                    files += 1
                iid = self.contents_tree.insert('', 'end', values=(path.name, item_type, size_text, format_time(st.st_mtime), format_time(get_created_time(st)), str(path)))
                self.contents_paths[iid] = path
            except (OSError, PermissionError) as exc:
                iid = self.contents_tree.insert('', 'end', values=(path.name, 'ERROR', '', '', '', str(path)))
                self.contents_paths[iid] = path
                self.status_var.set(f'Some items could not be read: {exc}')
        self.status_var.set(f'Showing {len(entries):,} direct items: {folders:,} folders and {files:,} files.')

    def refresh_contents(self):
        if self.current_contents_folder:
            self.load_contents(self.current_contents_folder)

    def contents_up_one(self):
        if self.current_contents_folder:
            parent = self.current_contents_folder.parent
            if parent != self.current_contents_folder:
                self.load_contents(parent)

    def on_contents_double_click(self, _event=None):
        selected = self.contents_tree.selection()
        if not selected:
            return
        path = self.contents_paths.get(selected[0])
        if not path:
            return
        if path.is_dir():
            self.load_contents(path)
        else:
            open_in_file_manager(path)

    def selected_all_folder(self):
        selected = self.all_tree.selection()
        if not selected:
            messagebox.showinfo('Nothing selected', 'Select a folder in the All Folders tab first.')
            return None
        return Path(self.all_tree.item(selected[0], 'values')[1])

    def selected_content_paths(self):
        return [self.contents_paths[item] for item in self.contents_tree.selection() if item in self.contents_paths]

    def open_selected_folder(self):
        path = self.selected_all_folder()
        if path:
            open_in_file_manager(path)

    def copy_selected_folder_path(self):
        path = self.selected_all_folder()
        if path:
            self.clipboard_clear()
            self.clipboard_append(str(path))
            self.status_var.set(f'Copied path: {path}')

    def open_selected_item(self):
        paths = self.selected_content_paths()
        if not paths:
            messagebox.showinfo('Nothing selected', 'Select a file or folder in Direct Contents first.')
            return
        path = paths[0]
        if path.is_dir():
            self.load_contents(path)
        else:
            open_in_file_manager(path)

    def copy_selected_item_path(self):
        paths = self.selected_content_paths()
        if not paths:
            messagebox.showinfo('Nothing selected', 'Select an item first.')
            return
        self.clipboard_clear()
        self.clipboard_append('\n'.join((str(p) for p in paths)))
        self.status_var.set(f'Copied {len(paths)} path(s) to the clipboard.')

    def create_new_folder(self):
        if not self.current_contents_folder:
            messagebox.showinfo('No folder open', 'Open a folder in Direct Contents first.')
            return
        name = simpledialog.askstring('New Folder', 'Folder name:', parent=self)
        if not name:
            return
        if name in {'.', '..'} or any((sep in name for sep in ('/', '\\'))):
            messagebox.showerror('Invalid name', 'Enter a single folder name, not a path.')
            return
        new_path = self.current_contents_folder / name
        try:
            new_path.mkdir()
            self.refresh_contents()
            self.status_var.set(f'Created folder: {new_path}')
        except OSError as exc:
            messagebox.showerror('Could not create folder', str(exc))

    def rename_selected_item(self):
        paths = self.selected_content_paths()
        if len(paths) != 1:
            messagebox.showinfo('Select one item', 'Select exactly one file or folder to rename.')
            return
        old = paths[0]
        new_name = simpledialog.askstring('Rename', 'New name:', initialvalue=old.name, parent=self)
        if not new_name or new_name == old.name:
            return
        if new_name in {'.', '..'} or any((sep in new_name for sep in ('/', '\\'))):
            messagebox.showerror('Invalid name', 'Enter a single file or folder name, not a path.')
            return
        new_path = old.with_name(new_name)
        if new_path.exists():
            messagebox.showerror('Already exists', f"An item named '{new_name}' already exists.")
            return
        try:
            old.rename(new_path)
            self.refresh_contents()
            self.status_var.set(f'Renamed to: {new_path.name}')
        except OSError as exc:
            messagebox.showerror('Rename failed', str(exc))

    def copy_selected_items(self):
        self._transfer_selected_items(move=False)

    def move_selected_items(self):
        self._transfer_selected_items(move=True)

    def _transfer_selected_items(self, move=False):
        paths = self.selected_content_paths()
        if not paths:
            messagebox.showinfo('Nothing selected', 'Select one or more files/folders first.')
            return
        destination = filedialog.askdirectory(title='Choose destination folder')
        if not destination:
            return
        destination = Path(destination)
        action = 'Move' if move else 'Copy'
        if move and (not messagebox.askyesno('Move selected items?', f'Move {len(paths)} selected item(s) to:\n\n{destination}\n\nContinue?')):
            return
        completed = 0
        failed = []
        for source in paths:
            target = destination / source.name
            try:
                transfer_item(source, destination, move)
                completed += 1
            except Exception as exc:
                failed.append(f'{source}: {exc}')
        self.refresh_contents()
        message = f'{action} complete: {completed} item(s).'
        if failed:
            message += f'\n\nFailed: {len(failed)}\n' + '\n'.join(failed[:8])
        messagebox.showinfo(f'{action} complete', message)

    def _selected_root(self):
        root_text = self.path_var.get().strip()
        if not root_text:
            messagebox.showwarning('No folder selected', 'Choose a folder first.')
            return None
        root = Path(root_text)
        if not root.exists() or not root.is_dir():
            messagebox.showerror('Invalid folder', 'The selected folder does not exist or is not a directory.')
            return None
        return root

    def _iter_files(self, root, recursive=True):
        if recursive:
            for current, _dirs, files in os.walk(root, followlinks=False):
                for name in files:
                    path = Path(current) / name
                    if not path.is_symlink():
                        yield path
        else:
            try:
                for path in root.iterdir():
                    if path.is_file() and (not path.is_symlink()):
                        yield path
            except (OSError, PermissionError):
                return

    @staticmethod
    def _sha256_file(path, chunk_size=1024 * 1024):
        digest = hashlib.sha256()
        with open(path, 'rb') as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def start_duplicate_scan(self):
        root = self._selected_root()
        if not root:
            return
        if self.duplicate_thread and self.duplicate_thread.is_alive():
            return
        self.duplicate_tree.delete(*self.duplicate_tree.get_children())
        self.duplicate_paths.clear()
        self.duplicate_results.clear()
        recursive = self.dup_recursive_var.get()
        self.dup_status_var.set('Scanning file sizes first; matching-size files will then be hashed...')
        self.status_var.set('Duplicate scan running...')
        self.duplicate_thread = threading.Thread(target=self._duplicate_worker, args=(root, recursive), daemon=True)
        self.duplicate_thread.start()

    def _duplicate_worker(self, root, recursive):
        by_size = {}
        errors = []
        file_count = 0
        for path in self._iter_files(root, recursive):
            try:
                st = path.stat()
                file_count += 1
                if st.st_size == 0:
                    continue
                by_size.setdefault(st.st_size, []).append((path, st.st_mtime))
            except (OSError, PermissionError) as exc:
                errors.append(f'{path}: {exc}')
        by_hash = {}
        for size, candidates in by_size.items():
            if len(candidates) < 2:
                continue
            for path, modified in candidates:
                try:
                    digest = self._sha256_file(path)
                    by_hash.setdefault((size, digest), []).append((path, modified))
                except (OSError, PermissionError) as exc:
                    errors.append(f'{path}: {exc}')
        groups = []
        group_no = 0
        for (size, digest), matches in sorted(by_hash.items(), key=lambda x: (-x[0][0], x[0][1])):
            if len(matches) < 2:
                continue
            group_no += 1
            group_name = f'D{group_no:04d}'
            matches.sort(key=lambda pair: (pair[1], str(pair[0]).casefold()))
            for path, modified in matches:
                groups.append(DuplicateInfo(path, size, modified, group_name, digest, 'Exact duplicate'))
        self.after(0, self._duplicate_complete, groups, file_count, errors)

    def _duplicate_complete(self, results, file_count, errors):
        self.duplicate_results = results
        self.duplicate_tree.delete(*self.duplicate_tree.get_children())
        self.duplicate_paths.clear()
        groups = set()
        reclaimable = 0
        grouped = {}
        for info in results:
            grouped.setdefault(info.group, []).append(info)
        for group_name, infos in grouped.items():
            groups.add(group_name)
            if len(infos) > 1:
                reclaimable += sum((i.size for i in infos[1:]))
            for info in infos:
                iid = self.duplicate_tree.insert('', 'end', values=(info.group, info.path.name, human_size(info.size), format_time(info.modified), str(info.path.parent), str(info.path)))
                self.duplicate_paths[iid] = info.path
        if results:
            self.dup_status_var.set(f'Scanned {file_count:,} files. Found {len(groups):,} duplicate group(s), {len(results):,} matching files. Potential space recoverable: {human_size(reclaimable)}.')
        else:
            self.dup_status_var.set(f'Scanned {file_count:,} files. No exact duplicates found.')
        if errors:
            self.status_var.set(f'Duplicate scan finished with {len(errors)} file access error(s).')
        else:
            self.status_var.set('Duplicate scan finished.')

    def select_duplicate_extras(self):
        groups = {}
        for iid in self.duplicate_tree.get_children():
            group = self.duplicate_tree.set(iid, 'group')
            groups.setdefault(group, []).append(iid)
        selected = []
        for _group, items in groups.items():
            selected.extend(items[1:])
        self.duplicate_tree.selection_set(selected)
        self.dup_status_var.set(f'Selected {len(selected):,} duplicate extra(s). Review them before moving or deleting.')

    def _selected_duplicate_paths(self):
        return [self.duplicate_paths[iid] for iid in self.duplicate_tree.selection() if iid in self.duplicate_paths]

    def open_selected_duplicate(self):
        paths = self._selected_duplicate_paths()
        if paths:
            open_in_file_manager(paths[0])
        else:
            messagebox.showinfo('Nothing selected', 'Select a duplicate file first.')

    def copy_duplicate_paths(self):
        paths = self._selected_duplicate_paths()
        if not paths:
            messagebox.showinfo('Nothing selected', 'Select one or more duplicate files first.')
            return
        self.clipboard_clear()
        self.clipboard_append('\n'.join((str(p) for p in paths)))
        self.status_var.set(f'Copied {len(paths)} duplicate path(s).')

    def _unique_target(self, folder, name):
        candidate = folder / name
        if not candidate.exists():
            return candidate
        stem = Path(name).stem
        suffix = Path(name).suffix
        count = 1
        while True:
            candidate = folder / f'{stem}__quarantine_{count}{suffix}'
            if not candidate.exists():
                return candidate
            count += 1

    def _quarantine_paths(self, paths, title):
        if not paths:
            messagebox.showinfo('Nothing selected', 'Select one or more files first.')
            return
        destination = filedialog.askdirectory(title='Choose quarantine folder')
        if not destination:
            return
        destination = Path(destination)
        if not messagebox.askyesno(title, f'Move {len(paths)} selected file(s) into this quarantine folder?\n\n{destination}\n\nThe files will NOT be permanently deleted.'):
            return
        moved = 0
        failed = []
        for source in paths:
            try:
                target = self._unique_target(destination, source.name)
                shutil.move(str(source), str(target))
                moved += 1
            except Exception as exc:
                failed.append(f'{source}: {exc}')
        message = f'Moved to quarantine: {moved}'
        if failed:
            message += f'\nFailed: {len(failed)}'
        messagebox.showinfo('Quarantine complete', message)

    def quarantine_selected_duplicates(self):
        paths = self._selected_duplicate_paths()
        self._quarantine_paths(paths, 'Quarantine selected duplicates?')
        if paths:
            self.start_duplicate_scan()

    def _permanent_delete_paths(self, paths, title):
        if not paths:
            messagebox.showinfo('Nothing selected', 'Select one or more files first.')
            return 0
        preview = '\n'.join((str(p) for p in paths[:10]))
        if len(paths) > 10:
            preview += f'\n...and {len(paths) - 10} more.'
        if not messagebox.askyesno(title, f'This permanently deletes the selected files and does NOT use the desktop Trash.\n\nFiles selected: {len(paths)}\n\n{preview}\n\nContinue?', icon='warning'):
            return 0
        deleted = 0
        failed = []
        for path in paths:
            try:
                path.unlink()
                deleted += 1
            except Exception as exc:
                failed.append(f'{path}: {exc}')
        message = f'Permanently deleted: {deleted}'
        if failed:
            message += f'\nFailed: {len(failed)}'
        messagebox.showinfo('Deletion complete', message)
        return deleted

    def delete_selected_duplicates(self):
        paths = self._selected_duplicate_paths()
        if self._permanent_delete_paths(paths, 'Permanently delete selected duplicates?'):
            self.start_duplicate_scan()

    @staticmethod
    def _numbered_copy_name(name):
        return bool(re.search('\\s\\(\\d+\\)(?=\\.[^.]+$|$)', name))

    @staticmethod
    def _temporary_name(name):
        lowered = name.casefold()
        temp_suffixes = ('~', '.tmp', '.temp', '.bak', '.backup', '.old', '.orig', '.swp', '.swo', '.part', '.crdownload')
        return lowered.startswith('~$') or lowered.startswith('.~lock.') or lowered.endswith(temp_suffixes)

    def scan_cleanup_candidates(self):
        root = self._selected_root()
        if not root:
            return
        self.cleanup_tree.delete(*self.cleanup_tree.get_children())
        self.cleanup_paths.clear()
        self.cleanup_results.clear()
        numbered = self.find_numbered_var.get()
        zero = self.find_zero_var.get()
        temp = self.find_temp_var.get()
        results = []
        errors = []
        file_count = 0
        for path in self._iter_files(root, self.dup_recursive_var.get()):
            try:
                st = path.stat()
                file_count += 1
                reasons = []
                if numbered and self._numbered_copy_name(path.name):
                    reasons.append('Numbered copy name')
                if zero and st.st_size == 0:
                    reasons.append('Zero-byte file')
                if temp and self._temporary_name(path.name):
                    reasons.append('Temporary/backup file')
                if reasons:
                    results.append(DuplicateInfo(path=path, size=st.st_size, modified=st.st_mtime, reason='; '.join(reasons)))
            except (OSError, PermissionError) as exc:
                errors.append(f'{path}: {exc}')
        results.sort(key=lambda i: (i.reason.casefold(), i.path.name.casefold(), str(i.path).casefold()))
        self.cleanup_results = results
        total_size = 0
        for info in results:
            total_size += info.size
            iid = self.cleanup_tree.insert('', 'end', values=(info.reason, info.path.name, human_size(info.size), format_time(info.modified), str(info.path.parent), str(info.path)))
            self.cleanup_paths[iid] = info.path
        self.cleanup_status_var.set(f'Scanned {file_count:,} files. Found {len(results):,} cleanup candidate(s), using {human_size(total_size)}. These are candidates only; review before removal.')
        self.status_var.set(f'Cleanup scan finished with {len(errors)} access error(s).' if errors else 'Cleanup scan finished.')

    def _selected_cleanup_paths(self):
        return [self.cleanup_paths[iid] for iid in self.cleanup_tree.selection() if iid in self.cleanup_paths]

    def open_selected_cleanup(self):
        paths = self._selected_cleanup_paths()
        if paths:
            open_in_file_manager(paths[0])
        else:
            messagebox.showinfo('Nothing selected', 'Select a cleanup candidate first.')

    def copy_cleanup_paths(self):
        paths = self._selected_cleanup_paths()
        if not paths:
            messagebox.showinfo('Nothing selected', 'Select one or more cleanup candidates first.')
            return
        self.clipboard_clear()
        self.clipboard_append('\n'.join((str(p) for p in paths)))
        self.status_var.set(f'Copied {len(paths)} cleanup path(s).')

    def quarantine_selected_cleanup(self):
        paths = self._selected_cleanup_paths()
        self._quarantine_paths(paths, 'Quarantine selected cleanup candidates?')
        if paths:
            self.scan_cleanup_candidates()

    def delete_selected_cleanup(self):
        paths = self._selected_cleanup_paths()
        if self._permanent_delete_paths(paths, 'Permanently delete selected cleanup candidates?'):
            self.scan_cleanup_candidates()

    def select_all_empty(self):
        self.empty_tree.selection_set(self.empty_tree.get_children())

    def clear_empty_selection(self):
        self.empty_tree.selection_remove(self.empty_tree.selection())

    def delete_selected_empty(self):
        selected = self.empty_tree.selection()
        if not selected:
            messagebox.showinfo('Nothing selected', 'Select one or more empty folders first.')
            return
        paths = [Path(self.empty_tree.item(item, 'values')[0]) for item in selected]
        preview = '\n'.join((str(path) for path in paths[:12]))
        if len(paths) > 12:
            preview += f'\n...and {len(paths) - 12} more.'
        if not messagebox.askyesno('Delete empty folders?', f'Only folders that are STILL empty will be removed.\n\nSelected: {len(paths)}\n\n{preview}\n\nContinue?'):
            return
        deleted = skipped = 0
        failed = []
        paths.sort(key=lambda p: len(p.parts), reverse=True)
        for path in paths:
            try:
                os.rmdir(path)
                deleted += 1
            except OSError as exc:
                skipped += 1
                failed.append(f'{path}: {exc}')
        message = f'Deleted: {deleted}\nSkipped/failed: {skipped}'
        if failed:
            message += '\n\nA folder may have become non-empty, be protected, or have a permissions problem.'
        messagebox.showinfo('Delete complete', message)
        self.start_scan()

    def export_report(self):
        if not self.folder_results:
            messagebox.showinfo('No report', 'Run a scan before exporting.')
            return
        filename = filedialog.asksaveasfilename(title='Save folder report', defaultextension='.csv', filetypes=[('CSV files', '*.csv'), ('All files', '*.*')], initialfile='folder_housekeeping_report.csv')
        if not filename:
            return
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Status', 'Folder', 'Direct Items', 'Recursive Files', 'Recursive Subfolders', 'Size Bytes', 'Human Size', 'Modified', 'Created or Changed', 'Error'])
                for info in self.folder_results:
                    status = 'EMPTY' if info.is_empty else 'ERROR' if info.error else 'HAS FILES'
                    writer.writerow([status, str(info.path), info.direct_items, info.file_count, info.folder_count, info.total_size, human_size(info.total_size), format_time(info.modified), format_time(info.created), info.error])
            messagebox.showinfo('Report saved', f'Report saved to:\n{filename}')
        except OSError as exc:
            messagebox.showerror('Could not save report', str(exc))

class RecursiveRenamer(ToolFrame):

    def __init__(self, master):
        super().__init__(master)
        self.files = []
        self.last_rename = []
        self.folder_var = tk.StringVar()
        self.extension_var = tk.StringVar(value='*')
        self.include_hidden_var = tk.BooleanVar(value=False)
        self.find_var = tk.StringVar()
        self.replace_var = tk.StringVar()
        self.regex_var = tk.BooleanVar(value=False)
        self.case_sensitive_var = tk.BooleanVar(value=False)
        self.prefix_var = tk.StringVar()
        self.suffix_var = tk.StringVar()
        self.case_var = tk.StringVar(value='No change')
        self.space_var = tk.StringVar(value='No change')
        self.remove_chars_var = tk.StringVar()
        self.remove_accents_var = tk.BooleanVar(value=False)
        self.number_mode_var = tk.StringVar(value='None')
        self.number_start_var = tk.IntVar(value=1)
        self.number_step_var = tk.IntVar(value=1)
        self.number_padding_var = tk.IntVar(value=3)
        self.number_separator_var = tk.StringVar(value='_')
        self.move_enabled_var = tk.BooleanVar(value=False)
        self.move_from_var = tk.StringVar(value='Beginning')
        self.move_skip_var = tk.IntVar(value=0)
        self.move_count_var = tk.IntVar(value=1)
        self.move_to_var = tk.StringVar(value='End')
        self.extension_case_var = tk.StringVar(value='No change')
        self.new_extension_var = tk.StringVar()
        self.status_var = tk.StringVar(value='Choose a root folder. Subfolders will be searched recursively.')
        self.build_gui()
        self.bind_preview_updates()

    def build_gui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        top = ttk.Frame(self, padding=10)
        top.grid(row=0, column=0, sticky='ew')
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text='Recursive In-Place File Renamer', font=('TkDefaultFont', 14, 'bold')).grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 8))
        ttk.Label(top, text='Root folder:').grid(row=1, column=0, sticky='w')
        ttk.Entry(top, textvariable=self.folder_var).grid(row=1, column=1, sticky='ew', padx=6)
        ttk.Button(top, text='Choose Folder...', command=self.choose_folder).grid(row=1, column=2, padx=4)
        ttk.Button(top, text='Scan Again', command=self.scan_folder).grid(row=1, column=3)
        ttk.Label(top, text='Extensions:').grid(row=2, column=0, sticky='w', pady=(6, 0))
        ttk.Entry(top, textvariable=self.extension_var, width=28).grid(row=2, column=1, sticky='w', padx=6, pady=(6, 0))
        ttk.Label(top, text='Examples: *   .jpg   .jpg,.png,.txt').grid(row=2, column=2, columnspan=2, sticky='w', pady=(6, 0))
        ttk.Checkbutton(top, text='Include hidden files/folders', variable=self.include_hidden_var, command=self.scan_folder).grid(row=3, column=1, sticky='w', pady=(5, 0))
        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.grid(row=1, column=0, sticky='nsew', padx=10)
        options = ttk.Frame(body, padding=(0, 0, 8, 0))
        preview = ttk.Frame(body)
        body.add(options, weight=0)
        body.add(preview, weight=1)
        self.build_options(options)
        self.build_preview(preview)
        bottom = ttk.Frame(self, padding=10)
        bottom.grid(row=2, column=0, sticky='ew')
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=self.status_var).grid(row=0, column=0, sticky='w')
        ttk.Button(bottom, text='Reset Options', command=self.reset_options).grid(row=0, column=1, padx=4)
        ttk.Button(bottom, text='Undo Last Batch', command=self.undo_last).grid(row=0, column=2, padx=4)
        ttk.Button(bottom, text='RENAME FILES IN PLACE', command=self.rename_files).grid(row=0, column=3, padx=(12, 0))

    def build_options(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        warning = ttk.LabelFrame(parent, text='Mode', padding=8)
        warning.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        ttk.Label(warning, text='Files stay in their original folders.').grid(row=0, column=0, sticky='w')
        ttk.Label(warning, text='Only filenames change; existing files are never overwritten.').grid(row=1, column=0, sticky='w', pady=(3, 0))
        notebook = ttk.Notebook(parent)
        notebook.grid(row=1, column=0, sticky='nsew')
        find_tab = ttk.Frame(notebook, padding=10)
        add_tab = ttk.Frame(notebook, padding=10)
        format_tab = ttk.Frame(notebook, padding=10)
        number_tab = ttk.Frame(notebook, padding=10)
        move_tab = ttk.Frame(notebook, padding=10)
        extension_tab = ttk.Frame(notebook, padding=10)
        notebook.add(find_tab, text='Find / Replace')
        notebook.add(add_tab, text='Add Text')
        notebook.add(format_tab, text='Formatting')
        notebook.add(number_tab, text='Numbering')
        notebook.add(move_tab, text='Move Characters')
        notebook.add(extension_tab, text='Extension')
        box = find_tab
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text='Find:').grid(row=0, column=0, sticky='w')
        ttk.Entry(box, textvariable=self.find_var).grid(row=0, column=1, sticky='ew', padx=5)
        ttk.Label(box, text='Replace:').grid(row=1, column=0, sticky='w', pady=4)
        ttk.Entry(box, textvariable=self.replace_var).grid(row=1, column=1, sticky='ew', padx=5, pady=4)
        ttk.Checkbutton(box, text='Regular expression', variable=self.regex_var).grid(row=2, column=0, columnspan=2, sticky='w')
        ttk.Checkbutton(box, text='Case sensitive', variable=self.case_sensitive_var).grid(row=3, column=0, columnspan=2, sticky='w')
        box = add_tab
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text='Prefix:').grid(row=0, column=0, sticky='w')
        ttk.Entry(box, textvariable=self.prefix_var).grid(row=0, column=1, sticky='ew', padx=5)
        ttk.Label(box, text='Suffix:').grid(row=1, column=0, sticky='w', pady=4)
        ttk.Entry(box, textvariable=self.suffix_var).grid(row=1, column=1, sticky='ew', padx=5, pady=4)
        box = format_tab
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text='Case:').grid(row=0, column=0, sticky='w')
        ttk.Combobox(box, textvariable=self.case_var, state='readonly', values=('No change', 'lower', 'UPPER', 'Title Case', 'Sentence case')).grid(row=0, column=1, sticky='ew', padx=5)
        ttk.Label(box, text='Spaces:').grid(row=1, column=0, sticky='w', pady=4)
        ttk.Combobox(box, textvariable=self.space_var, state='readonly', values=('No change', 'Spaces to _', 'Spaces to -', '_ to spaces', '- to spaces')).grid(row=1, column=1, sticky='ew', padx=5, pady=4)
        ttk.Label(box, text='Remove chars:').grid(row=2, column=0, sticky='w')
        ttk.Entry(box, textvariable=self.remove_chars_var).grid(row=2, column=1, sticky='ew', padx=5)
        ttk.Checkbutton(box, text='Remove accents', variable=self.remove_accents_var).grid(row=3, column=0, columnspan=2, sticky='w', pady=(4, 0))
        box = number_tab
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text='Position:').grid(row=0, column=0, sticky='w')
        ttk.Combobox(box, textvariable=self.number_mode_var, state='readonly', values=('None', 'Prefix', 'Suffix')).grid(row=0, column=1, sticky='ew', padx=5)
        ttk.Label(box, text='Start:').grid(row=1, column=0, sticky='w', pady=3)
        ttk.Spinbox(box, from_=-999999, to=999999, textvariable=self.number_start_var, width=8).grid(row=1, column=1, sticky='w', padx=5)
        ttk.Label(box, text='Step:').grid(row=2, column=0, sticky='w')
        ttk.Spinbox(box, from_=1, to=999999, textvariable=self.number_step_var, width=8).grid(row=2, column=1, sticky='w', padx=5)
        ttk.Label(box, text='Padding:').grid(row=3, column=0, sticky='w', pady=3)
        ttk.Spinbox(box, from_=1, to=12, textvariable=self.number_padding_var, width=8).grid(row=3, column=1, sticky='w', padx=5)
        ttk.Label(box, text='Separator:').grid(row=4, column=0, sticky='w')
        ttk.Entry(box, textvariable=self.number_separator_var, width=8).grid(row=4, column=1, sticky='w', padx=5)
        box = move_tab
        box.columnconfigure(1, weight=1)
        ttk.Checkbutton(box, text='Move part of the filename', variable=self.move_enabled_var).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 10))
        ttk.Label(box, text='Take from:').grid(row=1, column=0, sticky='w')
        ttk.Combobox(box, textvariable=self.move_from_var, state='readonly', values=('Beginning', 'End')).grid(row=1, column=1, sticky='ew', padx=5)
        ttk.Label(box, text='Skip characters:').grid(row=2, column=0, sticky='w', pady=5)
        ttk.Spinbox(box, from_=0, to=999999, textvariable=self.move_skip_var, width=8).grid(row=2, column=1, sticky='w', padx=5, pady=5)
        ttk.Label(box, text='Characters to move:').grid(row=3, column=0, sticky='w')
        ttk.Spinbox(box, from_=1, to=999999, textvariable=self.move_count_var, width=8).grid(row=3, column=1, sticky='w', padx=5)
        ttk.Label(box, text='Move to:').grid(row=4, column=0, sticky='w', pady=5)
        ttk.Combobox(box, textvariable=self.move_to_var, state='readonly', values=('Beginning', 'End')).grid(row=4, column=1, sticky='ew', padx=5, pady=5)
        ttk.Label(box, text='Skip 0 starts at the first or last character.\nThe moved characters keep their original order.', wraplength=280).grid(row=5, column=0, columnspan=2, sticky='w', pady=(8, 0))
        box = extension_tab
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text='Case:').grid(row=0, column=0, sticky='w')
        ttk.Combobox(box, textvariable=self.extension_case_var, state='readonly', values=('No change', 'lower', 'UPPER')).grid(row=0, column=1, sticky='ew', padx=5)
        ttk.Label(box, text='New extension:').grid(row=1, column=0, sticky='w', pady=(8, 0))
        ttk.Entry(box, textvariable=self.new_extension_var).grid(row=1, column=1, sticky='ew', padx=5, pady=(8, 0))
        ttk.Label(box, text='Optional. Enter txt or .txt. To change only LOG files, set Extensions at the top to .log first.', wraplength=290).grid(row=2, column=0, columnspan=2, sticky='w', pady=(8, 0))

    def build_preview(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        ttk.Label(parent, text='Preview — review this before renaming', font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky='w', pady=(0, 5))
        frame = ttk.Frame(parent)
        frame.grid(row=1, column=0, sticky='nsew')
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        columns = ('old', 'new', 'folder', 'status')
        self.tree = ttk.Treeview(frame, columns=columns, show='headings')
        self.tree.heading('old', text='Current Name')
        self.tree.heading('new', text='New Name')
        self.tree.heading('folder', text='Original Folder')
        self.tree.heading('status', text='Status')
        self.tree.column('old', width=230)
        self.tree.column('new', width=230)
        self.tree.column('folder', width=330)
        self.tree.column('status', width=100, anchor='center')
        y = ttk.Scrollbar(frame, orient='vertical', command=self.tree.yview)
        x = ttk.Scrollbar(frame, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        y.grid(row=0, column=1, sticky='ns')
        x.grid(row=1, column=0, sticky='ew')

    def bind_preview_updates(self):
        variables = [self.find_var, self.replace_var, self.regex_var, self.case_sensitive_var, self.prefix_var, self.suffix_var, self.case_var, self.space_var, self.remove_chars_var, self.remove_accents_var, self.number_mode_var, self.number_start_var, self.number_step_var, self.number_padding_var, self.number_separator_var, self.move_enabled_var, self.move_from_var, self.move_skip_var, self.move_count_var, self.move_to_var, self.extension_case_var, self.new_extension_var]
        for var in variables:
            var.trace_add('write', lambda *_: self.after_idle(self.refresh_preview))

    def choose_folder(self):
        folder = filedialog.askdirectory(title='Choose root folder')
        if folder:
            self.folder_var.set(folder)
            self.scan_folder()

    def scan_folder(self):
        text = self.folder_var.get().strip()
        if not text:
            return
        root = Path(text).expanduser()
        if not root.is_dir():
            return
        found = []
        for path in root.rglob('*'):
            if not path.is_file():
                continue
            if not self.include_hidden_var.get():
                try:
                    parts = path.relative_to(root).parts
                except ValueError:
                    parts = path.parts
                if any((part.startswith('.') for part in parts)):
                    continue
            if self.extension_matches(path):
                found.append(path)
        self.files = sorted(found, key=lambda p: str(p).lower())
        self.refresh_preview()

    def extension_matches(self, path):
        text = self.extension_var.get().strip()
        if not text or text == '*':
            return True
        allowed = set()
        for item in text.split(','):
            item = item.strip().lower()
            if not item:
                continue
            if item.startswith('*.'):
                item = item[1:]
            elif not item.startswith('.'):
                item = '.' + item
            allowed.add(item)
        return path.suffix.lower() in allowed

    def make_new_name(self, path, index):
        name = path.stem
        ext = path.suffix
        find_text = self.find_var.get()
        replace_text = self.replace_var.get()
        if find_text:
            if self.regex_var.get():
                flags = 0 if self.case_sensitive_var.get() else re.IGNORECASE
                name = re.sub(find_text, replace_text, name, flags=flags)
            elif self.case_sensitive_var.get():
                name = name.replace(find_text, replace_text)
            else:
                name = re.sub(re.escape(find_text), lambda _m: replace_text, name, flags=re.IGNORECASE)
        chars = self.remove_chars_var.get()
        if chars:
            name = name.translate(str.maketrans('', '', chars))
        if self.remove_accents_var.get():
            normalized = unicodedata.normalize('NFKD', name)
            name = ''.join((c for c in normalized if not unicodedata.combining(c)))
        spaces = self.space_var.get()
        if spaces == 'Spaces to _':
            name = name.replace(' ', '_')
        elif spaces == 'Spaces to -':
            name = name.replace(' ', '-')
        elif spaces == '_ to spaces':
            name = name.replace('_', ' ')
        elif spaces == '- to spaces':
            name = name.replace('-', ' ')
        case = self.case_var.get()
        if case == 'lower':
            name = name.lower()
        elif case == 'UPPER':
            name = name.upper()
        elif case == 'Title Case':
            name = name.title()
        elif case == 'Sentence case' and name:
            name = name[0].upper() + name[1:].lower()
        if self.move_enabled_var.get() and name:
            skip = max(0, int(self.move_skip_var.get()))
            count = max(1, int(self.move_count_var.get()))
            if self.move_from_var.get() == 'Beginning':
                start = min(skip, len(name))
                end = min(start + count, len(name))
            else:
                end = max(0, len(name) - skip)
                start = max(0, end - count)
            moved = name[start:end]
            remainder = name[:start] + name[end:]
            if self.move_to_var.get() == 'Beginning':
                name = moved + remainder
            else:
                name = remainder + moved
        name = self.prefix_var.get() + name + self.suffix_var.get()
        mode = self.number_mode_var.get()
        if mode != 'None':
            start = int(self.number_start_var.get())
            step = int(self.number_step_var.get())
            padding = max(1, int(self.number_padding_var.get()))
            number = start + index * step
            number_text = str(number).zfill(padding)
            sep = self.number_separator_var.get()
            if mode == 'Prefix':
                name = number_text + sep + name
            elif mode == 'Suffix':
                name = name + sep + number_text
        new_extension = self.new_extension_var.get().strip()
        if new_extension:
            if not new_extension.startswith('.'):
                new_extension = '.' + new_extension
            ext = new_extension
        ext_case = self.extension_case_var.get()
        if ext_case == 'lower':
            ext = ext.lower()
        elif ext_case == 'UPPER':
            ext = ext.upper()
        return name.strip() + ext

    def refresh_preview(self):
        if not hasattr(self, 'tree'):
            return
        self.tree.delete(*self.tree.get_children())
        proposed = []
        destination_counts = {}
        for index, path in enumerate(self.files):
            try:
                new_name = self.make_new_name(path, index)
                status = 'READY'
                if not new_name:
                    status = 'EMPTY'
                elif any(c in new_name for c in '/\\\x00') or new_name in ('.', '..'):
                    status = 'INVALID'
                elif new_name == path.name:
                    status = 'UNCHANGED'
                destination = path.with_name(new_name)
                key = os.path.normcase(str(destination))
                destination_counts[key] = destination_counts.get(key, 0) + 1
                proposed.append((path, new_name, status, destination))
            except re.error:
                proposed.append((path, path.name, 'BAD REGEX', path))
            except (ValueError, tk.TclError):
                proposed.append((path, path.name, 'BAD NUMBER', path))
        source_set = {os.path.normcase(str(p)) for p in self.files}
        ready = 0
        for path, new_name, status, destination in proposed:
            key = os.path.normcase(str(destination))
            if status == 'READY':
                if destination_counts.get(key, 0) > 1:
                    status = 'DUPLICATE'
                elif destination.exists() and key not in source_set:
                    status = 'EXISTS'
            if status == 'READY':
                ready += 1
            self.tree.insert('', 'end', values=(path.name, new_name, str(path.parent), status))
        self.status_var.set(f'{len(self.files)} file(s) found recursively — {ready} ready to rename.')

    def rename_files(self):
        if not self.files:
            messagebox.showinfo('Nothing to rename', 'Choose a root folder first.')
            return
        plan = []
        source_set = {os.path.normcase(str(p)) for p in self.files}
        destination_set = set()
        for index, source in enumerate(self.files):
            try:
                new_name = self.make_new_name(source, index)
            except Exception as exc:
                messagebox.showerror('Invalid settings', str(exc))
                return
            try:
                valid_leaf(new_name)
                destination = source.with_name(new_name)
            except ValueError as exc:
                messagebox.showerror('Invalid filename', str(exc))
                return
            if destination == source:
                continue
            key = os.path.normcase(str(destination))
            if key in destination_set:
                messagebox.showerror('Duplicate filename', f'More than one file would become:\n{destination}')
                return
            if destination.exists() and key not in source_set:
                messagebox.showerror('Filename already exists', f'This file will NOT be overwritten:\n\n{destination}')
                return
            destination_set.add(key)
            plan.append((source, destination))
        if not plan:
            messagebox.showinfo('Nothing changed', 'The current settings do not change any filenames.')
            return
        if not messagebox.askyesno('Confirm recursive rename', f'Rename {len(plan)} file(s)?\n\nFiles will remain in their original folders.\nOnly the filenames will change.\n\nExisting files will NOT be overwritten.'):
            return
        temporary = []
        completed = []
        try:
            for source, destination in plan:
                temp = source.with_name(f'.__rename_{uuid.uuid4().hex}__{source.name}')
                source.rename(temp)
                temporary.append((temp, destination, source))
            for temp, destination, original in temporary:
                final = temp.with_name(destination.name)
                temp.rename(final)
                completed.append((final, original))
        except Exception as exc:
            for current, original in reversed(completed):
                try:
                    if current.exists() and (not original.exists()):
                        current.rename(original)
                except OSError:
                    pass
            for temp, _destination, original in reversed(temporary):
                try:
                    if temp.exists() and (not original.exists()):
                        temp.rename(original)
                except OSError:
                    pass
            messagebox.showerror('Rename failed', f'{exc}\n\nA rollback was attempted.')
            self.scan_folder()
            return
        self.last_rename = completed
        self.scan_folder()
        messagebox.showinfo('Rename complete', f'Successfully renamed {len(completed)} file(s).\n\nAll files stayed in their original folders.')

    def undo_last(self):
        if not self.last_rename:
            messagebox.showinfo('Undo', 'There is no rename batch to undo.')
            return
        restored = 0
        failures = []
        for current, original in reversed(self.last_rename):
            try:
                if not current.exists():
                    failures.append(f'Missing: {current}')
                elif original.exists():
                    failures.append(f'Already exists: {original}')
                else:
                    current.rename(original)
                    restored += 1
            except OSError as exc:
                failures.append(f'{current.name}: {exc}')
        self.last_rename = []
        self.scan_folder()
        if failures:
            messagebox.showwarning('Undo partly completed', f'Restored {restored} file(s).\n\n' + '\n'.join(failures[:10]))
        else:
            messagebox.showinfo('Undo complete', f'Restored {restored} file(s).')

    def reset_options(self):
        self.find_var.set('')
        self.replace_var.set('')
        self.regex_var.set(False)
        self.case_sensitive_var.set(False)
        self.prefix_var.set('')
        self.suffix_var.set('')
        self.case_var.set('No change')
        self.space_var.set('No change')
        self.remove_chars_var.set('')
        self.remove_accents_var.set(False)
        self.number_mode_var.set('None')
        self.number_start_var.set(1)
        self.number_step_var.set(1)
        self.number_padding_var.set(3)
        self.number_separator_var.set('_')
        self.move_enabled_var.set(False)
        self.move_from_var.set('Beginning')
        self.move_skip_var.set(0)
        self.move_count_var.set(1)
        self.move_to_var.set('End')
        self.extension_case_var.set('No change')
        self.new_extension_var.set('')
        self.refresh_preview()

class FileFinderCollector(ToolFrame):

    def __init__(self, master):
        super().__init__(master)
        self.search_folders = []
        self.matches = []
        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        folder_frame = ttk.LabelFrame(self, text='1. Folders to Search')
        folder_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky='nsew')
        folder_frame.columnconfigure(0, weight=1)
        self.folder_list = tk.Listbox(folder_frame, height=4)
        self.folder_list.grid(row=0, column=0, rowspan=4, padx=8, pady=8, sticky='nsew')
        ttk.Button(folder_frame, text='Add Folder', command=self.add_folder).grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        ttk.Button(folder_frame, text='Add Samba Share', command=self.add_samba_share).grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        ttk.Button(folder_frame, text='Remove Selected', command=self.remove_folder).grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        ttk.Button(folder_frame, text='Clear Folders', command=self.clear_folders).grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        options = ttk.LabelFrame(self, text='2. Search Rules')
        options.grid(row=1, column=0, padx=10, pady=5, sticky='ew')
        for col in range(6):
            options.columnconfigure(col, weight=1 if col in (1, 3, 5) else 0)
        ttk.Label(options, text='Name contains:').grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.contains_var = tk.StringVar()
        ttk.Entry(options, textvariable=self.contains_var).grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        ttk.Label(options, text='Starts with:').grid(row=0, column=2, padx=5, pady=5, sticky='e')
        self.starts_var = tk.StringVar()
        ttk.Entry(options, textvariable=self.starts_var).grid(row=0, column=3, padx=5, pady=5, sticky='ew')
        ttk.Label(options, text='Ends with:').grid(row=0, column=4, padx=5, pady=5, sticky='e')
        self.ends_var = tk.StringVar()
        ttk.Entry(options, textvariable=self.ends_var).grid(row=0, column=5, padx=5, pady=5, sticky='ew')
        ttk.Label(options, text='Extension(s):').grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.extensions_var = tk.StringVar()
        ttk.Entry(options, textvariable=self.extensions_var).grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        ttk.Label(options, text='Example: jpg,png,pdf or .jpg,.png').grid(row=1, column=2, columnspan=2, padx=5, pady=5, sticky='w')
        ttk.Label(options, text='Regex:').grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.regex_var = tk.StringVar()
        ttk.Entry(options, textvariable=self.regex_var).grid(row=2, column=1, columnspan=3, padx=5, pady=5, sticky='ew')
        self.use_regex_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text='Use regex', variable=self.use_regex_var).grid(row=2, column=4, padx=5, pady=5, sticky='w')
        self.case_sensitive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text='Case sensitive', variable=self.case_sensitive_var).grid(row=2, column=5, padx=5, pady=5, sticky='w')
        self.capital_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text='Filename contains uppercase letter', variable=self.capital_var).grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky='w')
        ttk.Label(options, text='Simple pattern:').grid(row=3, column=2, padx=5, pady=5, sticky='e')
        self.simple_pattern_var = tk.StringVar()
        self.simple_pattern_combo = ttk.Combobox(options, textvariable=self.simple_pattern_var, state='readonly', values=['', 'Contains digits', 'Starts with digits', 'Ends with digits', 'Contains spaces', 'Contains underscore', 'Contains hyphen', 'Contains parentheses', 'All uppercase filename', 'All lowercase filename'])
        self.simple_pattern_combo.grid(row=3, column=3, columnspan=2, padx=5, pady=5, sticky='ew')
        self.simple_pattern_combo.current(0)
        self.match_all_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options, text='Require ALL filled rules', variable=self.match_all_var).grid(row=3, column=5, padx=5, pady=5, sticky='w')
        controls = ttk.Frame(self)
        controls.grid(row=2, column=0, padx=10, pady=5, sticky='ew')
        controls.columnconfigure(5, weight=1)
        ttk.Button(controls, text='Search', command=self.search).grid(row=0, column=0, padx=3)
        ttk.Button(controls, text='Clear Results', command=self.clear_results).grid(row=0, column=1, padx=3)
        ttk.Button(controls, text='Select All', command=self.select_all).grid(row=0, column=2, padx=3)
        ttk.Button(controls, text='Select None', command=self.select_none).grid(row=0, column=3, padx=3)
        self.status_var = tk.StringVar(value='Ready')
        ttk.Label(controls, textvariable=self.status_var).grid(row=0, column=5, padx=8, sticky='e')
        result_frame = ttk.LabelFrame(self, text='3. Matching Files')
        result_frame.grid(row=3, column=0, padx=10, pady=5, sticky='nsew')
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)
        columns = ('name', 'extension', 'folder', 'fullpath')
        self.tree = ttk.Treeview(result_frame, columns=columns, show='headings', selectmode='extended')
        self.tree.heading('name', text='File Name')
        self.tree.heading('extension', text='Extension')
        self.tree.heading('folder', text='Folder')
        self.tree.heading('fullpath', text='Full Path')
        self.tree.column('name', width=220)
        self.tree.column('extension', width=80, anchor='center')
        self.tree.column('folder', width=250)
        self.tree.column('fullpath', width=450)
        yscroll = ttk.Scrollbar(result_frame, orient='vertical', command=self.tree.yview)
        xscroll = ttk.Scrollbar(result_frame, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        yscroll.grid(row=0, column=1, sticky='ns')
        xscroll.grid(row=1, column=0, sticky='ew')
        action_frame = ttk.LabelFrame(self, text='4. Copy or Move Selected Files')
        action_frame.grid(row=4, column=0, padx=10, pady=(5, 10), sticky='ew')
        action_frame.columnconfigure(1, weight=1)
        ttk.Label(action_frame, text='Destination:').grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.dest_var = tk.StringVar()
        ttk.Entry(action_frame, textvariable=self.dest_var).grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        ttk.Button(action_frame, text='Browse', command=self.choose_destination).grid(row=0, column=2, padx=5, pady=5)
        self.auto_folder_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(action_frame, text='Create a new collection subfolder automatically', variable=self.auto_folder_var).grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky='w')
        ttk.Button(action_frame, text='Copy Selected', command=lambda: self.transfer('copy')).grid(row=1, column=2, padx=5, pady=5)
        ttk.Button(action_frame, text='Move Selected', command=lambda: self.transfer('move')).grid(row=1, column=3, padx=5, pady=5)

    def add_folder(self):
        folder = filedialog.askdirectory(title='Choose folder to search')
        if folder and folder not in self.search_folders:
            self.search_folders.append(folder)
            self.folder_list.insert(tk.END, folder)

    def add_samba_share(self):
        """Add a mounted Samba share or open an smb:// share via GVFS/GIO."""
        dialog = tk.Toplevel(self)
        dialog.title('Add Samba Share')
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)
        ttk.Label(dialog, text='Samba path:').grid(row=0, column=0, padx=8, pady=8, sticky='e')
        samba_var = tk.StringVar(value='smb://')
        entry = ttk.Entry(dialog, textvariable=samba_var, width=55)
        entry.grid(row=0, column=1, padx=8, pady=8, sticky='ew')
        entry.focus_set()
        ttk.Label(dialog, text='Examples: smb://server/share   or   /mnt/share   or   /media/user/share\nMounted shares are fastest and work just like local folders.').grid(row=1, column=0, columnspan=2, padx=8, pady=(0, 8), sticky='w')

        def browse_mounted():
            folder = filedialog.askdirectory(title='Choose mounted Samba/network folder')
            if folder:
                samba_var.set(folder)

        def add_share():
            value = samba_var.get().strip()
            if not value:
                return
            resolved = self.resolve_samba_path(value)
            if resolved is None:
                return
            if resolved not in self.search_folders:
                self.search_folders.append(resolved)
                self.folder_list.insert(tk.END, resolved)
            dialog.destroy()
        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=2, column=0, columnspan=2, padx=8, pady=8, sticky='e')
        ttk.Button(button_frame, text='Browse Mounted Share', command=browse_mounted).grid(row=0, column=0, padx=4)
        ttk.Button(button_frame, text='Add', command=add_share).grid(row=0, column=1, padx=4)
        ttk.Button(button_frame, text='Cancel', command=dialog.destroy).grid(row=0, column=2, padx=4)

    def resolve_samba_path(self, value):
        """Return a normal filesystem path for local/mounted paths or smb:// URIs."""
        value = os.path.expanduser(value)
        if value.lower().startswith('smb://') and os.name == 'nt':
            parts = urlsplit(value)
            value = '\\\\' + parts.netloc + unquote(parts.path).replace('/', '\\')
        if not value.lower().startswith('smb://'):
            if os.path.isdir(value):
                return os.path.abspath(value)
            messagebox.showerror('Folder not found', f'The folder does not exist or is not mounted:\n{value}')
            return None
        try:
            subprocess.run(['gio', 'mount', value], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            messagebox.showerror('Samba support', "Could not run 'gio'. On MX Linux, install/use gvfs support or mount the Samba share first.")
            return None
        gvfs_root = Path(f'/run/user/{os.getuid()}/gvfs')
        if gvfs_root.exists():
            without_scheme = value[6:].strip('/')
            parts = without_scheme.split('/')
            if len(parts) >= 2:
                server, share = (parts[0], parts[1])
                subparts = parts[2:]
                prefix = f'smb-share:server={server},share={share}'
                for child in gvfs_root.iterdir():
                    if child.name.lower() == prefix.lower():
                        candidate = child.joinpath(*subparts) if subparts else child
                        if candidate.is_dir():
                            return str(candidate)
        messagebox.showerror('Samba share unavailable', 'The smb:// share could not be mapped to a local folder.\n\nOpen the share once in Thunar, or mount it under /mnt or /media, then add that folder.')
        return None

    def remove_folder(self):
        selected = list(self.folder_list.curselection())
        for index in reversed(selected):
            self.search_folders.pop(index)
            self.folder_list.delete(index)

    def clear_folders(self):
        self.search_folders.clear()
        self.folder_list.delete(0, tk.END)

    def clear_results(self):
        self.matches.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.status_var.set('Results cleared')

    def select_all(self):
        items = self.tree.get_children()
        self.tree.selection_set(items)

    def select_none(self):
        self.tree.selection_remove(self.tree.selection())

    def choose_destination(self):
        folder = filedialog.askdirectory(title='Choose destination folder')
        if folder:
            self.dest_var.set(folder)

    def normalize_extensions(self):
        text = self.extensions_var.get().strip()
        if not text:
            return []
        extensions = []
        for ext in text.split(','):
            ext = ext.strip()
            if not ext:
                continue
            if not ext.startswith('.'):
                ext = '.' + ext
            extensions.append(ext if self.case_sensitive_var.get() else ext.lower())
        return extensions

    def simple_pattern_match(self, filename):
        pattern = self.simple_pattern_var.get()
        stem = Path(filename).stem
        if not pattern:
            return True
        if pattern == 'Contains digits':
            return bool(re.search('\\d', filename))
        if pattern == 'Starts with digits':
            return bool(re.match('^\\d', filename))
        if pattern == 'Ends with digits':
            return bool(re.search('\\d(?=\\.[^.]+$|$)', filename))
        if pattern == 'Contains spaces':
            return ' ' in filename
        if pattern == 'Contains underscore':
            return '_' in filename
        if pattern == 'Contains hyphen':
            return '-' in filename
        if pattern == 'Contains parentheses':
            return '(' in filename or ')' in filename
        if pattern == 'All uppercase filename':
            letters = [c for c in stem if c.isalpha()]
            return bool(letters) and all((c.isupper() for c in letters))
        if pattern == 'All lowercase filename':
            letters = [c for c in stem if c.isalpha()]
            return bool(letters) and all((c.islower() for c in letters))
        return True

    def filename_matches(self, filename):
        case_sensitive = self.case_sensitive_var.get()
        name_for_compare = filename if case_sensitive else filename.lower()
        contains = self.contains_var.get().strip()
        starts = self.starts_var.get().strip()
        ends = self.ends_var.get().strip()
        if not case_sensitive:
            contains = contains.lower()
            starts = starts.lower()
            ends = ends.lower()
        rules = []
        if contains:
            rules.append(contains in name_for_compare)
        if starts:
            rules.append(name_for_compare.startswith(starts))
        if ends:
            rules.append(name_for_compare.endswith(ends))
        extensions = self.normalize_extensions()
        if extensions:
            suffix = Path(filename).suffix
            suffix_cmp = suffix if case_sensitive else suffix.lower()
            rules.append(suffix_cmp in extensions)
        if self.capital_var.get():
            rules.append(any((ch.isupper() for ch in Path(filename).stem)))
        if self.simple_pattern_var.get():
            rules.append(self.simple_pattern_match(filename))
        if self.use_regex_var.get():
            regex_text = self.regex_var.get().strip()
            if regex_text:
                flags = 0 if case_sensitive else re.IGNORECASE
                try:
                    rules.append(bool(re.search(regex_text, filename, flags)))
                except re.error as exc:
                    raise ValueError(f'Invalid regular expression:\n{exc}')
        if not rules:
            return True
        return all(rules) if self.match_all_var.get() else any(rules)

    def search(self):
        if not self.search_folders:
            messagebox.showwarning('No folders', 'Add at least one folder to search.')
            return
        self.clear_results()
        self.status_var.set('Searching...')
        self.update_idletasks()
        found = []
        seen = set()
        try:
            for root_folder in self.search_folders:
                for root, dirs, files in os.walk(root_folder):
                    for filename in files:
                        if self.filename_matches(filename):
                            full_path = os.path.abspath(os.path.join(root, filename))
                            if full_path in seen:
                                continue
                            seen.add(full_path)
                            found.append(full_path)
        except ValueError as exc:
            messagebox.showerror('Search error', str(exc))
            self.status_var.set('Search error')
            return
        except PermissionError as exc:
            messagebox.showwarning('Permission problem', f'A folder could not be accessed:\n{exc}')
        self.matches = found
        for path_text in found:
            p = Path(path_text)
            self.tree.insert('', tk.END, values=(p.name, p.suffix, str(p.parent), str(p)))
        self.status_var.set(f'{len(found)} matching file(s) found')

    def selected_paths(self):
        selected = self.tree.selection()
        paths = []
        for item in selected:
            values = self.tree.item(item, 'values')
            if values:
                paths.append(values[3])
        return paths

    def unique_destination_path(self, destination_folder, filename):
        destination_folder = Path(destination_folder)
        target = destination_folder / filename
        if not target.exists():
            return target
        stem = target.stem
        suffix = target.suffix
        counter = 1
        while True:
            candidate = destination_folder / f'{stem}_{counter}{suffix}'
            if not candidate.exists():
                return candidate
            counter += 1

    def transfer(self, mode):
        paths = self.selected_paths()
        if not paths:
            messagebox.showwarning('Nothing selected', 'Select one or more matching files first.')
            return
        destination = self.dest_var.get().strip()
        if not destination:
            messagebox.showwarning('No destination', 'Choose a destination folder.')
            return
        destination = Path(destination)
        try:
            destination.mkdir(parents=True, exist_ok=True)
            if self.auto_folder_var.get():
                folder_name = 'Collected_Files'
                collection_folder = destination / folder_name
                counter = 1
                while collection_folder.exists():
                    collection_folder = destination / f'{folder_name}_{counter}'
                    counter += 1
                collection_folder.mkdir(parents=True)
                destination = collection_folder
            completed = 0
            errors = []
            for source_text in paths:
                source = Path(source_text)
                if not source.exists():
                    errors.append(f'Missing: {source}')
                    continue
                target = self.unique_destination_path(destination, source.name)
                try:
                    if mode == 'copy':
                        shutil.copy2(source, target)
                    else:
                        shutil.move(str(source), str(target))
                    completed += 1
                except Exception as exc:
                    errors.append(f'{source}\n{exc}')
            action = 'Copied' if mode == 'copy' else 'Moved'
            message = f'{action} {completed} file(s) to:\n{destination}'
            if errors:
                message += f'\n\n{len(errors)} file(s) had errors.'
            messagebox.showinfo('Finished', message)
            if mode == 'move':
                self.search()
        except Exception as exc:
            messagebox.showerror('Transfer error', str(exc))


def valid_leaf(name):
    if not name or name in ('.', '..') or any(c in name for c in '/\\\0'):
        raise ValueError('Enter one filename without path separators.')
    if os.name == 'nt' and (any(c in name for c in '<>:"|?*') or name.endswith((' ', '.'))):
        raise ValueError('This filename is not valid on Windows.')
    return name


def transfer_item(source, destination, move=False):
    source, destination = Path(source), Path(destination)
    target = destination / source.name
    if os.path.lexists(target):
        raise FileExistsError(f'Already exists: {target}')
    if source.is_dir() and not source.is_symlink():
        if destination.resolve() == source.resolve() or source.resolve() in destination.resolve().parents:
            raise ValueError('A folder cannot be copied or moved into itself.')
    if move:
        shutil.move(str(source), str(target))
    elif source.is_symlink():
        target.symlink_to(os.readlink(source), target_is_directory=source.is_dir())
    elif source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    else:
        # Exclusive creation avoids silently replacing a file created after the check.
        with source.open('rb') as src, target.open('xb') as dst:
            shutil.copyfileobj(src, dst)
        shutil.copystat(source, target)
    return target


class BrowserPane(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=6)
        self.app = app
        self.folder = Path.home()
        self.history = []
        self.entries = {}
        self.generation = 0
        self.path_var = tk.StringVar(value=str(self.folder))
        self.filter_var = tk.StringVar()
        self.hidden = tk.BooleanVar(value=False)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self.pane_title = ttk.Label(self, text=('LEFT FOLDER' if not hasattr(app, 'left') else 'RIGHT FOLDER'), style='Pane.TLabel', anchor='w', padding=7)
        self.pane_title.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 6))
        top = ttk.Frame(self); top.grid(row=1, column=0, sticky='ew'); top.columnconfigure(2, weight=1)
        ttk.Button(top, text='Back', command=self.back).grid(row=0, column=0)
        ttk.Button(top, text='Up', command=lambda: self.navigate(self.folder.parent)).grid(row=0, column=1)
        entry = ttk.Entry(top, textvariable=self.path_var); entry.grid(row=0, column=2, sticky='ew', padx=4)
        entry.bind('<Return>', lambda e: self.navigate(self.path_var.get()))
        ttk.Button(top, text='Go', command=lambda: self.navigate(self.path_var.get())).grid(row=0, column=3)
        ttk.Button(top, text='Browse', command=self.browse).grid(row=0, column=4)
        opts=ttk.Frame(self); opts.grid(row=2,column=0,sticky='ew',pady=5); opts.columnconfigure(1,weight=1)
        ttk.Label(opts,text='Filter:').grid(row=0,column=0)
        ttk.Entry(opts,textvariable=self.filter_var).grid(row=0,column=1,sticky='ew')
        self.filter_var.trace_add('write',lambda *_: self.render())
        ttk.Checkbutton(opts,text='Hidden',variable=self.hidden,command=self.render).grid(row=0,column=2)
        self.tree=ttk.Treeview(self,columns=('name','kind','size','modified'),show='headings',selectmode='extended')
        self.tree.grid(row=3,column=0,sticky='nsew')
        sb=ttk.Scrollbar(self,command=self.tree.yview);sb.grid(row=3,column=1,sticky='ns');self.tree.configure(yscrollcommand=sb.set)
        for c,w in [('name',220),('kind',70),('size',90),('modified',145)]:
            self.tree.heading(c,text=c.title(),command=lambda col=c:self.sort(col))
            self.tree.column(c,width=w)
        self.reverse={}
        self.tree.bind('<Button-1>',lambda e:self.activate())
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.app.preview(self))
        self.tree.bind('<Double-1>',lambda e:self.open_selected())
        self.tree.bind('<Return>',lambda e:self.open_selected())
        self.tree.bind('<Control-a>',lambda e:self.select_all())
        self.tree.bind('<Button-3>',self.menu)
        self.navigate(self.folder,False)
    def activate(self):
        self.app.active=self
        for pane in (getattr(self.app, 'left', None), getattr(self.app, 'right', None)):
            if pane is not None:
                pane.pane_title.configure(style='ActivePane.TLabel' if pane is self else 'Pane.TLabel')
        self.app.status.set(f'Active folder: {self.folder}')
    def selected(self):
        return [self.entries[i][0] for i in self.tree.selection() if i in self.entries]
    def select_all(self):
        self.tree.selection_set(self.tree.get_children());return 'break'
    def browse(self):
        p=filedialog.askdirectory(initialdir=self.folder)
        if p:self.navigate(p)
    def back(self):
        if self.history:self.navigate(self.history.pop(),False)
    def navigate(self,value,remember=True):
        value=str(value)
        if value.lower().startswith('smb://'):
            value=self.app.finder.resolve_samba_path(value)
            if not value:return
        p=Path(value).expanduser().absolute()
        if not p.is_dir():messagebox.showerror('Folder unavailable',str(p));return
        if remember and p!=self.folder:self.history.append(self.folder)
        self.folder=p;self.path_var.set(str(p));self.generation+=1;generation=self.generation
        def worker():
            rows=[];errors=[]
            try:
                with os.scandir(p) as items:
                    for item in items:
                        try:
                            st=item.stat(follow_symlinks=False)
                            kind='Link' if item.is_symlink() else 'Folder' if item.is_dir() else 'File'
                            rows.append((Path(item.path),kind,st.st_size,st.st_mtime))
                        except OSError as exc:errors.append(str(exc))
            except OSError as exc:errors.append(str(exc))
            def done():
                if generation!=self.generation:return
                self.entries={str(i):row for i,row in enumerate(sorted(rows,key=lambda r:(r[1]!='Folder',r[0].name.casefold())))}
                self.render();self.app.status.set(f'{len(rows)} items in {p}'+(f' | {len(errors)} access errors' if errors else ''))
            self.app.events.put(done)
        threading.Thread(target=worker,daemon=True).start()
    def render(self):
        self.tree.delete(*self.tree.get_children())
        term=self.filter_var.get().casefold()
        for i,(p,k,s,t) in self.entries.items():
            if not self.hidden.get() and p.name.startswith('.'):continue
            if term and term not in p.name.casefold():continue
            self.tree.insert('', 'end',iid=i,values=(p.name,k,'' if k=='Folder' else human_size(s),format_time(t)))
    def sort(self,col):
        index={'name':0,'kind':1,'size':2,'modified':3}[col]
        reverse=not self.reverse.get(col,True);self.reverse[col]=reverse
        def key(i):
            v=self.entries[i][index]
            return v.name.casefold() if index==0 else v
        for n,i in enumerate(sorted(self.tree.get_children(),key=key,reverse=reverse)):self.tree.move(i,'',n)
    def open_selected(self):
        paths=self.selected()
        if paths:
            if paths[0].is_dir():self.navigate(paths[0])
            else:open_in_file_manager(paths[0])
    def menu(self,event):
        self.activate();row=self.tree.identify_row(event.y)
        if row and row not in self.tree.selection():self.tree.selection_set(row)
        m=tk.Menu(self,tearoff=False)
        for label,fn in [('Open',self.open_selected),('Preview / properties',lambda:self.app.preview(self)),('Copy to other pane',lambda:self.app.transfer(False)),('Move to other pane',lambda:self.app.transfer(True)),('Rename',self.app.rename_one),('Quarantine',self.app.quarantine),('Copy paths',self.app.copy_paths)]:m.add_command(label=label,command=fn)
        m.tk_popup(event.x_root,event.y_root)


class JH_PYFM(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('PyFile_Manager_JH — Explore • Organize • Collect')
        self.geometry('1460x920');self.minsize(1080,740)
        self.events=queue.Queue();self.busy=False;self.active=None
        self.config_dir=Path.home()/'.jh_file_manager';self.config_dir.mkdir(exist_ok=True)
        self.config_path=self.config_dir/'settings.json'
        try:self.settings=json.loads(self.config_path.read_text())
        except (OSError,ValueError):self.settings={}
        self.status=tk.StringVar(value='Ready');self.bookmark_var=tk.StringVar()
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.ui_size = max(9, min(16, int(self.settings.get('ui_size', 11))))
        self.configure(background='#e8eef5')
        self.apply_appearance()
        self.columnconfigure(0,weight=1);self.rowconfigure(1,weight=1)
        top=ttk.Frame(self,padding=8);top.grid(row=0,column=0,sticky='ew');top.columnconfigure(1,weight=1)
        ttk.Label(top,text='PyFile_Manager_JH',font=('TkDefaultFont',16,'bold'),foreground='#175489').grid(row=0,column=0,padx=8)
        ttk.Label(top,text='A workspace for browsing, cleaning, renaming and collecting files').grid(row=0,column=1,sticky='w')
        ttk.Button(top,text='A−',width=4,command=lambda:self.change_text_size(-1)).grid(row=0,column=2,padx=3)
        ttk.Button(top,text='A+',width=4,command=lambda:self.change_text_size(1)).grid(row=0,column=3,padx=3)
        ttk.Button(top,text='Help',command=self.help).grid(row=0,column=4,padx=3)
        self.tabs=ttk.Notebook(self);self.tabs.grid(row=1,column=0,sticky='nsew',padx=8)
        explorer=ttk.Frame(self.tabs);self.tabs.add(explorer,text='File Explorer')
        explorer.columnconfigure(0,weight=1);explorer.rowconfigure(1,weight=1)
        toolbar=ttk.Frame(explorer,padding=5);toolbar.grid(row=0,column=0,sticky='ew')
        buttons=[('Refresh',self.refresh),('New folder',self.new_folder),('New text file',self.new_file),('Rename',self.rename_one),('Copy → other',lambda:self.transfer(False)),('Move → other',lambda:self.transfer(True)),('Quarantine',self.quarantine),('Restore last',self.restore),('Copy paths',self.copy_paths)]
        for i,(label,fn) in enumerate(buttons):ttk.Button(toolbar,text=label,command=fn).grid(row=i//5,column=i%5,padx=3,pady=3,sticky='ew')
        ttk.Button(toolbar,text='Use active folder in tools',command=self.sync_tools).grid(row=2,column=0,columnspan=2,sticky='ew',pady=5)
        self.bookmarks=ttk.Combobox(toolbar,textvariable=self.bookmark_var,state='readonly',width=42,values=self.settings.get('bookmarks',[]));self.bookmarks.grid(row=2,column=2,columnspan=3,sticky='ew')
        self.bookmarks.bind('<<ComboboxSelected>>',lambda e:self.active.navigate(self.bookmark_var.get()))
        ttk.Button(toolbar,text='Bookmark folder',command=self.add_bookmark).grid(row=2,column=5)
        ttk.Button(toolbar,text='Remove bookmark',command=self.remove_bookmark).grid(row=2,column=6)
        ttk.Button(toolbar,text='Samba share',command=self.samba).grid(row=2,column=7)
        panes=ttk.Panedwindow(explorer,orient='horizontal');panes.grid(row=1,column=0,sticky='nsew')
        self.left=BrowserPane(panes,self);self.right=BrowserPane(panes,self)
        panes.add(self.left,weight=1);panes.add(self.right,weight=1);self.active=self.left
        self.left.activate()
        self.details=tk.Text(explorer,height=7,wrap='word',background='#edf3fa',relief='sunken',borderwidth=2,state='disabled');self.details.grid(row=2,column=0,sticky='ew',padx=6,pady=6)
        self.house=FolderHousekeeper(self.tabs);self.tabs.add(self.house,text='Housekeeping & Duplicates')
        self.renamer=RecursiveRenamer(self.tabs);self.tabs.add(self.renamer,text='Batch Renamer')
        self.finder=FileFinderCollector(self.tabs);self.tabs.add(self.finder,text='Find & Collect')
        ttk.Label(self,textvariable=self.status,padding=8).grid(row=2,column=0,sticky='ew')
        self.bind('<F5>',lambda e:self.refresh());self.protocol('WM_DELETE_WINDOW',self.close)
        self.decorate_widgets(self)
        self.after(80,self.poll)
        for pane,key in [(self.left,'left'),(self.right,'right')]:
            p=self.settings.get(key)
            if p and Path(p).is_dir():pane.navigate(p)
    def apply_appearance(self):
        import tkinter.font as tkfont
        for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont'):
            tkfont.nametofont(name).configure(size=self.ui_size)
        st = self.style
        st.configure('.', background='#e8eef5', foreground='#1e3044')
        st.configure('TFrame', background='#e8eef5')
        st.configure('TLabel', padding=3)
        st.configure('TLabelframe', borderwidth=2, relief='groove')
        st.configure('TLabelframe.Label', foreground='#174c79', font=('TkDefaultFont', self.ui_size, 'bold'))
        st.configure('TButton', padding=(9, 7), borderwidth=2, relief='raised', background='#dde7f1')
        st.map('TButton', background=[('disabled','#e1e5ea'),('pressed','#b4cbe0'),('active','#c8daec')], foreground=[('disabled','#74808d')], relief=[('pressed','sunken')])
        for name, bg, hover in [('Primary.TButton','#225e94','#317ab5'), ('Caution.TButton','#8c342d','#a9453b')]:
            st.configure(name, background=bg, foreground='white', bordercolor=bg)
            st.map(name, background=[('disabled','#d5dce4'),('pressed',bg),('active',hover)], foreground=[('disabled','#74808d'),('!disabled','white')])
        st.configure('TEntry', fieldbackground='white', padding=6, borderwidth=2, relief='sunken', bordercolor='#788da3', lightcolor='#788da3', darkcolor='#788da3')
        st.map('TEntry', bordercolor=[('focus','#236ba7')], lightcolor=[('focus','#236ba7')], darkcolor=[('focus','#236ba7')])
        st.configure('TCombobox', padding=5, fieldbackground='white', borderwidth=2)
        st.configure('Treeview', font=('TkDefaultFont',self.ui_size), rowheight=self.ui_size*2+10, background='white', fieldbackground='white', borderwidth=2, relief='sunken')
        st.map('Treeview', background=[('selected','#225e94')], foreground=[('selected','white')])
        st.configure('Treeview.Heading', padding=(7,8), background='#d0deec', foreground='#183b5b', font=('TkDefaultFont',self.ui_size,'bold'), relief='raised')
        st.configure('TNotebook.Tab', padding=(16,9), font=('TkDefaultFont',self.ui_size,'bold'))
        st.map('TNotebook.Tab', background=[('selected','#225e94'),('active','#ccdfef')], foreground=[('selected','white')])
        st.configure('Pane.TLabel', background='#d4dfeb', foreground='#42576c', font=('TkDefaultFont',self.ui_size,'bold'))
        st.configure('ActivePane.TLabel', background='#225e94', foreground='white', font=('TkDefaultFont',self.ui_size,'bold'))

    def change_text_size(self, delta):
        self.ui_size = max(9, min(16, self.ui_size + delta))
        self.apply_appearance()
        self.save_settings()
        self.status.set(f'Text size: {self.ui_size}. Click either folder pane to choose the source for actions.')

    def decorate_widgets(self, parent):
        for widget in parent.winfo_children():
            if isinstance(widget, ttk.Button):
                label = str(widget.cget('text')).casefold()
                if any(word in label for word in ('delete', 'quarantine', 'move')):
                    widget.configure(style='Caution.TButton')
                elif any(word in label for word in ('scan', 'preview', 'collect', 'copy →', 'go')):
                    widget.configure(style='Primary.TButton')
            elif isinstance(widget, tk.Frame):
                widget.configure(background='#e8eef5')
            elif isinstance(widget, (tk.Text, tk.Listbox)):
                widget.configure(background='white', foreground='#1e3044', borderwidth=2, relief='sunken', selectbackground='#225e94', selectforeground='white')
            self.decorate_widgets(widget)

    def poll(self):
        for _ in range(100):
            try:fn=self.events.get_nowait()
            except queue.Empty:break
            try:fn()
            except Exception as exc:self.status.set(str(exc))
        self.after(80,self.poll)
    def refresh(self):
        self.left.navigate(self.left.folder,False);self.right.navigate(self.right.folder,False)
    def run_job(self,label,worker):
        if self.busy:messagebox.showinfo('Working','Wait for the current file operation to finish.');return
        self.busy=True;self.status.set(label)
        def run():
            try:result=worker();error=None
            except Exception as exc:result=None;error=str(exc)
            def done():
                self.busy=False;self.refresh()
                if error:messagebox.showerror(label,error)
                else:messagebox.showinfo(label,str(result))
            self.events.put(done)
        threading.Thread(target=run,daemon=True).start()
    def transfer(self,move):
        paths=self.active.selected();other=self.right if self.active is self.left else self.left;dest=other.folder
        if not paths:return
        if not messagebox.askyesno('Review transfer',f'{"Move" if move else "Copy"} {len(paths)} selected item(s) to:\n{dest}\n\nExisting names will be skipped.'):return
        def worker():
            ok=0;errors=[]
            for p in paths:
                try:transfer_item(p,dest,move);ok+=1
                except Exception as exc:errors.append(f'{p.name}: {exc}')
            return f'Completed: {ok}\nSkipped/failed: {len(errors)}\n'+'\n'.join(errors[:15])
        self.run_job('Move files' if move else 'Copy files',worker)
    def ask_name(self,title,initial=''):
        from tkinter.simpledialog import askstring
        value=askstring(title,'Name:',initialvalue=initial,parent=self)
        if value is None:return None
        try:return valid_leaf(value)
        except ValueError as exc:messagebox.showerror(title,str(exc));return None
    def new_folder(self):
        name=self.ask_name('New folder')
        if name:
            try:(self.active.folder/name).mkdir();self.refresh()
            except OSError as exc:messagebox.showerror('New folder',str(exc))
    def new_file(self):
        name=self.ask_name('New text file','New file.txt')
        if name:
            try:
                with (self.active.folder/name).open('x',encoding='utf-8'):pass
                self.refresh()
            except OSError as exc:messagebox.showerror('New file',str(exc))
    def rename_one(self):
        paths=self.active.selected()
        if len(paths)!=1:messagebox.showinfo('Rename','Select one item, or use the Batch Renamer tab.');return
        name=self.ask_name('Rename',paths[0].name)
        if name:
            try:
                target=paths[0].with_name(name)
                if os.path.lexists(target):raise FileExistsError('That name already exists.')
                paths[0].rename(target);self.refresh()
            except OSError as exc:messagebox.showerror('Rename',str(exc))
    def quarantine(self):
        paths=self.active.selected()
        if not paths:return
        dest=filedialog.askdirectory(title='Choose quarantine folder (outside selected folders)')
        if not dest:return
        if not messagebox.askyesno('Quarantine',f'Move {len(paths)} selected items into a dated quarantine batch?\n{dest}'):return
        def worker():
            folder=Path(dest)/('JH_quarantine_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
            for p in paths:
                if p.is_dir() and (p.resolve()==folder.parent.resolve() or p.resolve() in folder.parent.resolve().parents):raise ValueError('Choose a quarantine location outside selected folders.')
            folder.mkdir();record=[];errors=[]
            manifest=folder/'restore_manifest.json'
            manifest.write_text('[]',encoding='utf-8')
            for p in paths:
                try:
                    target=folder/(uuid.uuid4().hex[:8]+'_'+p.name)
                    shutil.move(str(p),str(target));record.append({'original':str(p),'stored':str(target)})
                    manifest.write_text(json.dumps(record,indent=2),encoding='utf-8')
                except Exception as exc:errors.append(f'{p}: {exc}')
            self.events.put(lambda:self.remember_quarantine(str(manifest)))
            return f'Quarantined: {len(record)}\nManifest: {manifest}\n'+'\n'.join(errors[:10])
        self.run_job('Quarantine',worker)
    def remember_quarantine(self,path):self.settings['last_quarantine']=path;self.save_settings()
    def restore(self):
        name=self.settings.get('last_quarantine')
        if not name or not Path(name).is_file():name=filedialog.askopenfilename(title='Choose restore_manifest.json',filetypes=[('JSON','*.json')])
        if not name:return
        if not messagebox.askyesno('Restore','Restore the files listed in this quarantine manifest? Existing names will be skipped.'):return
        def worker():
            manifest=Path(name);rows=json.loads(manifest.read_text());remaining=[];errors=[];count=0
            for row in rows:
                try:
                    stored=Path(row['stored']);original=Path(row['original'])
                    if stored.parent.resolve()!=manifest.parent.resolve():raise ValueError('Stored file is outside this quarantine batch.')
                    if os.path.lexists(original):raise FileExistsError(f'Already exists: {original}')
                    if not original.parent.is_dir():raise FileNotFoundError(f'Original folder unavailable: {original.parent}')
                    shutil.move(str(stored),str(original));count+=1
                except Exception as exc:remaining.append(row);errors.append(str(exc))
            manifest.write_text(json.dumps(remaining,indent=2),encoding='utf-8')
            return f'Restored: {count}\nRemaining: {len(remaining)}\n'+'\n'.join(errors[:10])
        self.run_job('Restore quarantine',worker)
    def copy_paths(self):
        paths=self.active.selected();self.clipboard_clear();self.clipboard_append('\n'.join(map(str,paths)))
    def preview(self,pane):
        pane.activate();paths=pane.selected()
        if not paths:return
        p=paths[0]
        try:
            st=p.lstat();text=f'{p}\nType: {"symbolic link" if p.is_symlink() else "folder" if p.is_dir() else "file"} | Size: {human_size(st.st_size)} | Modified: {format_time(st.st_mtime)}\n'
            if p.is_symlink():text+=f'Link target: {os.readlink(p)}\n'
            elif p.is_file():
                with p.open('rb') as f:data=f.read(8192)
                if b'\0' not in data:
                    text+='\n'+data.decode('utf-8',errors='replace')
                else:text+='Binary file; open it with its normal application.'
            if len(paths)>1:text+=f'\n\nSelected items: {len(paths)}'
        except OSError as exc:text=str(exc)
        self.details.configure(state='normal');self.details.delete('1.0','end');self.details.insert('1.0',text);self.details.configure(state='disabled')
    def sync_tools(self):
        p=str(self.active.folder);self.house.path_var.set(p);self.renamer.folder_var.set(p)
        if p not in self.finder.search_folders:self.finder.search_folders.append(p);self.finder.folder_list.insert('end',p)
        self.status.set('Active folder sent to Housekeeping, Batch Renamer and Find & Collect. Run the desired scan there.')
    def add_bookmark(self):
        values=self.settings.setdefault('bookmarks',[]);p=str(self.active.folder)
        if p not in values:values.append(p)
        self.bookmarks.configure(values=values);self.bookmark_var.set(p);self.save_settings()
    def remove_bookmark(self):
        values=self.settings.setdefault('bookmarks',[]);p=self.bookmark_var.get()
        if p in values:values.remove(p)
        self.bookmarks.configure(values=values);self.bookmark_var.set('');self.save_settings()
    def samba(self):
        from tkinter.simpledialog import askstring
        uri=askstring('Samba folder','Enter smb://server/share, a mounted Linux path, or a Windows UNC path:',parent=self)
        if uri:self.active.navigate(uri)
    def save_settings(self):
        self.settings.update(left=str(self.left.folder),right=str(self.right.folder),ui_size=self.ui_size)
        try:
            temp=self.config_path.with_suffix('.tmp');temp.write_text(json.dumps(self.settings,indent=2),encoding='utf-8');temp.replace(self.config_path)
        except OSError as exc:self.status.set(f'Could not save settings: {exc}')
    def close(self):
        if self.busy:messagebox.showinfo('File operation running','Please wait until the transfer finishes before closing.');return
        self.save_settings();self.destroy()
    def help(self):
        messagebox.showinfo('PyFile_Manager_JH', 'Click either pane to make it active. Copy and Move target the other pane.\n\nDouble-click folders to enter them and files to open them. Click headings to sort. Ctrl+A selects all; F5 refreshes.\n\nUse active folder in tools shares the folder with the original programs. Their detailed features remain in their tabs.\n\nQuarantine preserves files with a restore manifest. Permanent deletion in Housekeeping requires confirmation. Review all cleanup candidates.\n\nSamba: use a mounted share, or smb:// with Linux GIO/GVFS support. Windows can use \\server\\share paths. No passwords are stored.\n\nSome inherited scans run in the foreground on large folders. Cancel/queue management and direct SMB protocol access are not included.')


if __name__ == '__main__':
    JH_PYFM().mainloop()
