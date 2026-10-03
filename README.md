# PyFile Manager JH

A Python desktop workspace for browsing files, housekeeping, batch renaming, and collecting matching files. Uses Tkinter and Python's standard library; no pip packages are required.

## Start the app



Linux:

```bash
python3 JH_File_Manager.py
```

Windows:

```bat
JH_PyFile_Manager.py
```

You can also open the script in IDLE and choose **Run → Run Module (F5)**. The app needs a graphical desktop. On MX Linux/Debian, if your distribution's Python lacks Tkinter, install `python3-tk`. A separately compiled Python may need its own Tk support.

## Appearance and controls

- **A− / A+** adjust normal interface text and table row height. The setting is remembered; some headings keep their own fixed font sizes.
- Blue buttons emphasize common actions. Red buttons identify actions that move or remove files.
- Entries have stronger borders, selected tabs have a blue background, and tables have larger rows.
- The blue **LEFT FOLDER / RIGHT FOLDER** header identifies the active pane.
- Maximize the window for the larger toolbars. Drag the divider between the explorer panes to adjust their widths.

## File Explorer: quick start

1. Choose a source folder using **Browse** in the left pane.
2. Choose a destination folder in the right pane.
3. Click an item in the source pane; its header turns blue.
4. Select files or folders, then choose **Copy → other** or **Move → other**.
5. Review the destination in the confirmation dialog.

Copy leaves the source in place. Move transfers it. Existing destination names are skipped in the explorer transfer operation. The completion dialog reports failures or skipped items.

Double-click a folder to enter it or a file to open it in its normal application. Use **Back**, **Up**, or type a path and press Enter. **Filter** limits the visible names in the current folder; it is not a recursive search. **Hidden** shows names beginning with a dot.

Click table headings to sort. Ctrl-click selects several items; Shift-click selects a range. Right-click offers common actions. The lower panel displays properties and a limited text preview of the first selected item.

| Control | Action |
| --- | --- |
| F5 | Refresh both explorer panes |
| Ctrl+A, with an explorer table focused | Select all visible items in that pane |
| Enter, with an explorer table focused | Open the first selected item |
| Enter, in a path entry | Navigate to the entered path |
| New folder / New text file | Create an item in the active pane's folder |
| Rename | Rename one selected item |
| Copy paths | Copy selected full paths to the clipboard |
| Bookmark folder | Remember the active folder |
| Use active folder in tools | Set the housekeeping and renamer folder; add it to the collector's search list |

## Housekeeping & Duplicates

Choose a directory and click **Scan Folders**. The inner tabs provide:

- **Empty Folders:** select empty folders individually or use **Select All Empty**. Deletion uses `os.rmdir`, which refuses to remove folders that contain items.
- **All Folders:** folder statistics, recursive sizes, item counts, and dates. Select a row to populate Direct Contents.
- **Direct Contents:** browse the selected folder's immediate files and subfolders; open, rename, create, copy, or move items.
- **Duplicate Files:** scan for matching contents using file size and SHA-256. Review groups and preserve a wanted copy before removing any duplicates.
- **Cleanup Candidates:** find numbered-copy names, zero-byte files, temporary files, and files below a selected size threshold. A candidate is not necessarily disposable.

Click column headings to sort results. Export the folder report to CSV when you want a record. On Linux, “Created / Changed” can mean metadata-change time when creation time is unavailable.

## Batch Renamer

1. Choose a root folder and an extension filter, such as `*` or `.jpg,.png`.
2. Scan the folder. Subfolders are included.
3. Set find/replace, optional regular expressions, prefixes/suffixes, case, spaces, numbering, character movement, or extension changes.
4. Review the **Current Name**, **New Name**, folder, and status columns.
5. Apply the rename only after the preview matches your intention.

Extension changes rename a file; they do not convert its contents. Undo information is held for the current running session; keep a backup for important work.

## Find & Collect

Add one or more search folders, then set name, extension, simple-pattern, or regex rules. **Require ALL filled rules** controls whether every filled rule must match. Run **Search**, select matching files, choose a destination, and use **Copy Selected** or **Move Selected**. An optional collection subfolder helps keep a new collection separate.

Use Copy when building a collection while keeping the original files in place.

## Samba / network folders

On Windows, enter a UNC path such as:

```text
\\server\share\folder
```

A mapped network drive also works. Authenticate through Windows when needed.

On Linux, a mounted share works like a local directory:

```text
/mnt/share
/media/yourname/share
```

The explorer's **Samba share** button also accepts `smb://server/share` using Linux GIO/GVFS support when available. If it cannot resolve the share, connect through your desktop file manager and use its mounted filesystem path. Network permissions and availability still apply. The app does not store passwords.

## Quarantine and restore

In the explorer, **Quarantine** moves selected items into a dated batch inside a folder you choose. Choose a location outside the selected folders. Each batch contains `restore_manifest.json`, which records the original and stored paths.

**Restore last** uses the latest remembered manifest, or lets you choose one if it is unavailable. Existing original names are skipped. Keep the manifest with the batch and do not edit it. Housekeeping has its own cleanup actions; do not assume every action can be restored with the explorer's Restore last button.

Permanent deletion cannot be reversed by this app. Review selections and confirmations before deleting.

## Settings and troubleshooting

Settings are stored in `.jh_file_manager/settings.json` beneath your home folder. They include explorer locations, bookmarks, text size, and the last explorer quarantine manifest.

- **Permission denied:** check folder/share permissions and whether the drive is read-only.
- **Network path unavailable:** reconnect the share and verify it opens in your operating system's file manager.
- **Missing items:** clear Filter, enable Hidden where appropriate, and refresh.
- **Wrong transfer direction:** click the source pane and verify its header is blue before copying or moving.
- **Slow scans:** recursive size calculations and hashing large duplicates can take time, especially over Samba. Some inherited scans run in the foreground.
- **Large controls:** lower the text size with A− or maximize the window.

## Validation of this appearance update

The updated script passed Python syntax compilation. A graphical launch could not be verified in the editing environment; check the appearance on your Windows or Linux desktop.
