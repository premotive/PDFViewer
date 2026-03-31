# PDF Viewer Upgrade — Full App with Tabs, Library & Installer

**Date:** 2026-03-31
**Status:** Approved

## Overview

Upgrade the existing PySide6/PyMuPDF PDF viewer from a script-launched tool into a full-fledged desktop application with tabbed document viewing, a collapsible PDF library sidebar, a compact header, drag-and-drop support, and a proper Windows installer with file associations.

## Goals

- Open and switch between multiple PDFs via tabs
- Build a personal PDF library that auto-populates as documents are opened
- Clean, compact UI with minimal chrome
- Install as a real Windows application (Start Menu, file association, taskbar icon)
- Keyboard-driven workflow for power use

## Non-Goals

- Annotations/highlights
- Page thumbnail sidebar
- OCR or scanned PDF support
- Print functionality
- Cross-platform packaging (Windows only for now)

---

## 1. Tab System

### Architecture

A `TabManager` class wrapping a `QTabBar` at the top of the window. Each tab owns its own `PDFEngine` + `PageRenderer` (QGraphicsScene/View) pair, making documents fully independent.

### Behavior

- Opening a PDF (file dialog, drag-drop, library click, CLI arg) creates a new tab
- Each tab maintains its own: zoom level, scroll position, theme, edit state, undo/redo stack
- Closing a tab with unsaved edits prompts "Save changes?"
- `+` button at the end of the tab bar opens a file dialog
- Middle-click on a tab closes it
- When all tabs are closed, the window shows an empty state with the library sidebar still visible

### Keyboard Shortcuts

- `Ctrl+Tab` / `Ctrl+Shift+Tab` — cycle tabs forward/back
- `Ctrl+W` — close current tab
- `Ctrl+T` — open file dialog (new tab)
- `Ctrl+1-9` — jump to tab by number

### Impact on Existing Code

`MainWindow` currently holds a single `PDFEngine` + `PageRenderer`. Refactor so the window holds a `TabManager`, and each tab holds its own engine/renderer pair. The toolbar, search bar, and editor connect to whichever tab is active. Switching tabs swaps which engine/renderer the toolbar and search bar interact with.

---

## 2. Collapsible Library Sidebar

### Architecture

A `LibrarySidebar` class (QWidget) docked on the right side of the main window. Contains a scrollable area of `LibraryCard` widgets. Backed by a `library.json` file for persistence.

### Data Model (`library.json`)

Each entry stores:
- `file_path` — absolute path to the PDF
- `filename` — display name
- `page_count` — number of pages
- `last_opened` — ISO timestamp of last open
- `thumb_path` — path to cached thumbnail image

On startup, validate that files still exist. Mark missing files with a visual indicator (e.g., dimmed card) rather than removing them — the file might be on a disconnected drive.

### Library Cards

- Thumbnail of first page (rendered once at low DPI, cached as a small PNG in a `.thumbs/` directory alongside `library.json`)
- Filename (truncated with ellipsis if long)
- Light metadata line: page count + relative time (e.g., "3 pages · 2h ago")
- Single-click opens the PDF in a new tab, or switches to its tab if already open
- Right-click context menu: Open, Remove from Library

### Sidebar Behavior

- Collapsible via a thin toggle strip on its left edge (arrow button)
- Toggle shortcut: `Ctrl+\`
- Collapsed state persisted in `config.json`
- Default width ~200px, not user-resizable
- Scrolls vertically when items overflow

### Auto-Population

Any PDF opened by any method (file dialog, drag-drop, CLI argument, file association double-click) is automatically added to the library. No manual "add to library" step. Library sorted by last opened (most recent first).

---

## 3. Compact Header

### Layout

Two rows replacing the current three (menu bar + toolbar):

1. **Row 1 — Tab bar:** `QTabBar` with close buttons on each tab, `+` button at the end
2. **Row 2 — Unified toolbar:** Hamburger (☰) → Open → Save → Save As │ Theme dropdown → Color pickers │ Zoom dropdown │ spacer │ Search button

### Hamburger Menu

Clicking ☰ opens a `QMenu` containing all current File/Edit/View menu items. All keyboard shortcuts (Ctrl+O, Ctrl+S, Ctrl+F, etc.) remain bound globally — the hamburger is just the menu reorganized into a single button.

### Changes from Current UI

- `QMenuBar` removed from the window
- `toolbar.py` refactored to include the hamburger button
- Page navigator ("Page X of Y") moves to the status bar

---

## 4. Drag-and-Drop

- Enable `setAcceptDrops(True)` on the main window
- Accept files with `.pdf` extension from Windows Explorer
- On drop: open the PDF in a new tab + add to library
- Visual feedback: subtle highlight/border overlay on the window while dragging a PDF over it
- Reject non-PDF files silently

---

## 5. Keyboard Shortcuts

### New Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Tab` | Next tab |
| `Ctrl+Shift+Tab` | Previous tab |
| `Ctrl+W` | Close current tab |
| `Ctrl+T` | Open file (new tab) |
| `Ctrl+1-9` | Jump to tab N |
| `Ctrl+\` | Toggle library sidebar |

### Preserved Shortcuts

All existing shortcuts apply to the active tab:
- `Ctrl+O` — open file (same as Ctrl+T for consistency, both open a new tab)
- `Ctrl+S` — save current document
- `Ctrl+Shift+S` — save as
- `Ctrl+F` — search in current document
- `Ctrl+Z` / `Ctrl+Y` — undo/redo in current document
- `Ctrl+C` — copy selected text
- `Ctrl+Mouse Wheel` — zoom current document

---

## 6. App Packaging & Installation

### PyInstaller Build

- Single-folder bundle (not one-file — faster startup, easier debugging)
- Bundles: Python runtime, PySide6, PyMuPDF, numpy, all project modules
- Includes: `fonts/` directory, app icon (`.ico`)
- Build artifact: `build.bat` script that invokes PyInstaller with a checked-in `.spec` file

### App Icon

- Simple, clean design — stylized PDF document shape
- Generated as `.ico` with multiple sizes (16, 32, 48, 256px)
- Used for: window title bar, taskbar, installer, file association icon

### Inno Setup Installer

- Install location: `Program Files\PDFViewer`
- Creates Start Menu shortcut
- Optional: Desktop shortcut (checkbox in installer)
- Optional: Register `.pdf` file association (checkbox — user may want to keep their current default)
- Adds entry to Add/Remove Programs with uninstaller
- Installer script (`.iss` file) checked into the repo

### Single-Instance Support

When the app is registered as the default PDF viewer, double-clicking a PDF in Explorer should:
1. Check if an instance is already running (via Windows named mutex)
2. If yes: send the file path to the running instance (via a simple socket or Windows message), which opens it in a new tab
3. If no: launch normally with the file as an argument

---

## 7. File & Directory Structure (New/Changed)

```
PDFViewer/
├── main.py              # Refactored — holds TabManager instead of single engine
├── tab_manager.py       # NEW — TabManager + TabState classes
├── library_sidebar.py   # NEW — LibrarySidebar + LibraryCard widgets
├── library.json         # NEW — persisted library data (auto-generated)
├── .thumbs/             # NEW — cached page thumbnails
├── toolbar.py           # MODIFIED — hamburger menu, absorbs menu bar
├── pdf_engine.py        # UNCHANGED
├── page_renderer.py     # UNCHANGED
├── text_overlay.py      # UNCHANGED
├── search.py            # MINOR — connects to active tab
├── editor.py            # MINOR — connects to active tab
├── render_worker.py     # UNCHANGED
├── theme_engine.py      # UNCHANGED
├── config.py            # MODIFIED — new keys for sidebar state, library path
├── config.json          # MODIFIED — new keys
├── icon.ico             # NEW — app icon
├── build.bat            # NEW — PyInstaller build script
├── PDFViewer.spec       # NEW — PyInstaller spec file
├── installer.iss        # NEW — Inno Setup installer script
└── ...
```
