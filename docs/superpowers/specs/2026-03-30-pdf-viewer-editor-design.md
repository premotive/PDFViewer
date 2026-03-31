# PDF Viewer/Editor — Design Specification

**Date:** 2026-03-30
**Status:** Draft
**Target:** `C:\Users\Noah\Documents\Tool_Projects\PDFViewer\`

---

## 1. Purpose

A personal desktop PDF viewer that prioritizes **reading comfort** (customizable background and font colors) with **text editing** capability (rewrite text content in-place). It handles text-heavy PDFs that include complex layouts such as columns, tables, and outlined text boxes.

This is a single-user local tool — no collaboration, cloud, or multi-platform requirements.

---

## 2. Core Architecture

### 2.1 Hybrid Pixmap + Text Overlay Approach

Each PDF page is rendered as two layers inside a `QGraphicsScene`:

- **Layer 1 — Page Pixmap (background):** The full page rendered as a raster image via `page.get_pixmap()`. This perfectly preserves all graphics, images, tables, lines, borders, vector art, and complex layouts without reconstruction.
- **Layer 2 — Text Overlays:** Extracted text spans positioned on top of the pixmap at their exact PDF coordinates. These are the editable elements.

This hybrid approach sidesteps layout reconstruction entirely — the pixmap handles visual fidelity, while the overlays provide interactivity.

### 2.2 Display Modes

**Faithful Mode (default):**
- Pixmap rendered normally — shows the PDF exactly as authored
- Text overlays are fully invisible (alpha = 0), serving only as click/hover targets
- On hover: a subtle highlight rectangle appears over the text region
- On double-click: overlay becomes visible and editable
- Purpose: view the PDF as-is, with optional editing

**Reading Mode:**
- Pixmap is tinted to the user's chosen background color via a semi-transparent `QGraphicsRectItem` overlay placed between the pixmap and text layers
- All text overlay colors are overridden to the user's chosen font color
- Text overlays become the primary visible text (pixmap text is hidden behind the tint)
- Purpose: comfortable reading with custom colors

### 2.3 Rendering Pipeline

```
PDF File
  |
  v
fitz.open(path) ──> Two fitz.Document instances
  |                    |
  |                    +──> Render thread (read-only operations):
  |                    |      page.get_pixmap(dpi=render_dpi)
  |                    |      page.get_text("dict")
  |                    |      page.get_text("text") (for search index)
  |                    |            |
  |                    |            v
  |                    |    Qt signal ──> Main thread receives:
  |                    |                   - QImage (pixmap data)
  |                    |                   - text dict (span positions/fonts)
  |                    |                        |
  |                    |                        v
  |                    |                 QGraphicsPixmapItem (Layer 1)
  |                    |                 QGraphicsSimpleTextItem per span (Layer 2)
  |                    |                 (swapped to QGraphicsTextItem on double-click)
  |
  +──> Main thread instance (write operations):
         page.draw_rect() + page.insert_textbox() on save
         doc.save() on save
```

### 2.4 Threading Model

PyMuPDF is **not thread-safe**. Two separate `fitz.Document` instances are opened on the same file:

- **Main thread instance:** Text insertion on save, document metadata
- **Render thread instance:** Pixmap generation (`get_pixmap`) AND text extraction (`get_text`) — both are read-only operations

These instances share no state. The render thread sends completed pixmaps and extracted text dicts back to the main thread via Qt signals. The main thread then creates QGraphicsItems from the received data.

### 2.5 Coordinate System

PDF coordinates are in points (72 DPI). Pixmaps are rendered at a configurable DPI (default 150). The scale factor is:

```
scale = render_dpi / 72.0
```

All text overlay positions are transformed: `pixmap_coord = (text_coord - page.rect.top_left) * scale`

`page.rect` is used as the canonical coordinate space (accounts for CropBox and page rotation). The same DPI is used for both pixmap rendering and coordinate scaling to ensure pixel-perfect alignment.

HiDPI displays: render DPI is multiplied by `devicePixelRatio` (e.g., 150 * 2.0 = 300 DPI on a 2x display) to maintain crispness.

---

## 3. Text Editing

### 3.1 Edit Flow

1. User double-clicks a text span
2. The `QGraphicsSimpleTextItem` is replaced with a `QGraphicsTextItem` with `TextEditorInteraction` flag
3. A thin border appears around the editing area; cursor is placed at click position
4. User edits text freely
5. Exit edit mode via: click outside, press Escape, or press Tab (Tab moves to next span in reading order)
6. The item is swapped back to `QGraphicsSimpleTextItem` with updated text
7. The span is marked "dirty" in the edit tracker: `{(page_num, span_id): {original_text, original_rect, new_text}}`

### 3.2 Undo/Redo

A unified `QUndoStack` at the document level. Each edit (entering and exiting a span with changed text) pushes a `QUndoCommand` with before/after snapshots. Ctrl+Z / Ctrl+Y work globally across all spans and pages.

### 3.3 Unsaved Changes Tracking

- Global dirty flag set when any span is modified
- Title bar shows `*` prefix when dirty (e.g., `* document.pdf — PDF Viewer`)
- Close / Open New triggers a "Save changes?" dialog (Yes / No / Cancel)

---

## 4. Save Pipeline

### 4.1 White-Out + Insert Strategy

Redaction (`add_redact_annot` + `apply_redactions`) is destructive — it removes overlapping graphics like table borders and images. Instead, the save pipeline uses a **white-out** approach:

1. For each dirty span:
   a. Draw a filled rectangle over the original span rect using `page.draw_rect(rect, color=white, fill=white)` — this covers the original text with the page's background color (white for most PDFs)
   b. Insert new text via `page.insert_textbox(rect, new_text, fontname=matched_font, fontsize=original_size, color=original_color)`
2. If `insert_textbox` returns overflow text (didn't fit), retry with font size reduced by 0.5pt increments, down to a minimum of `original_size * 0.7`. If still overflowing, warn the user.

This preserves annotations, form fields, and surrounding graphical elements.

### 4.2 Font Matching

Original font metadata (name, size, bold/italic flags, color) is extracted from the text dict. Matching strategy:

1. **Base-14 fonts:** If the original is a PDF base-14 font (Helvetica, Times, Courier, etc.), match exactly
2. **Bundled fonts:** Map common font families to bundled open-source equivalents:
   - Sans-serif → Noto Sans
   - Serif → Noto Serif
   - Monospace → Liberation Mono
   - Bold/Italic variants included
3. **Fallback:** If no match, use the closest base-14 font. Display a one-time warning toast: "Some fonts were substituted — saved text may look slightly different from the original."

Bundled fonts: Noto Sans (Regular, Bold, Italic, BoldItalic), Noto Serif (same), Liberation Mono (same). ~10MB total.

### 4.3 File Save Mechanics (Windows)

Windows file locking prevents writing to an open file. Save procedure:

1. Write to a temp file in the same directory (`tempfile.NamedTemporaryFile`)
2. Close the original `fitz.Document` instances
3. Rename original to `filename.pdf.bak`
4. Rename temp to `filename.pdf`
5. Reopen the file (both document instances)
6. Delete `.bak` on success

"Save As" always available via dialog. If the directory is read-only or a network share fails, fall back to a "Save As" dialog pointing to the user's Documents folder.

### 4.4 Limitations (Documented in App)

- Edited text uses substitute fonts; appearance may differ slightly from the original
- Original text is covered (white-out), not truly deleted from the PDF structure
- Digital signatures are invalidated by any modification
- Text length changes may cause slight layout differences within the edited span's bounding box

---

## 5. Theme Engine

### 5.1 Preset Themes

| Theme | Background | Font Color |
|-------|-----------|------------|
| Light | `#FFFFFF` | `#000000` |
| Sepia | `#F4ECD8` | `#5B4636` |
| Dark | `#1E1E1E` | `#D4D4D4` |
| AMOLED Dark | `#000000` | `#FFFFFF` |
| Custom | User-picked | User-picked |

### 5.2 Theme Application

- **Background tint:** A `QGraphicsRectItem` with **fully opaque fill** matching the theme's background color, sized to the page, placed between the pixmap layer and text overlay layer. It must be fully opaque (not semi-transparent) to completely hide the pixmap text underneath — otherwise the original text bleeds through and doubles with the overlay text. Toggling theme = changing this rect's color and visibility. In faithful mode this rect is hidden (pixmap visible). In reading mode it's shown (pixmap hidden). Instant, no pixmap regeneration.
- **Font color:** All `QGraphicsSimpleTextItem` colors updated to the theme's font color in reading mode. In faithful mode, text overlays are invisible so color is irrelevant.
- **Mode switch:** Batch all item updates inside `scene.blockSignals(True)` / `False` to prevent incremental repaints. Switch feels instant.

### 5.3 Persistence

Theme choice, custom colors, and mode are saved to `config.json` and restored on next launch.

---

## 6. Lazy Loading & Performance

### 6.1 Page Loading Strategy

- **At open time:** Read all `page.rect` dimensions (fast — no rendering). Calculate total scene height for scrollbar.
- **Visible range:** Load pages in the current viewport + 2-page buffer (above and below)
- **Page load:** Render pixmap + extract text in the background thread, show gray placeholder with page number until ready. First page is loaded synchronously for instant feedback.
- **Unloading:** Pages outside viewport + 5-page buffer are fully unloaded (all QGraphicsItems removed from scene, memory freed)

### 6.2 Render Queue

- Priority queue ordered by distance from current viewport center
- **Generation counter:** Each scroll event increments the counter. When a render completes, if its generation doesn't match current, discard the result.
- Prevents thrashing during rapid scrolling

### 6.3 Zoom

- **Interactive zoom:** `QGraphicsView.setTransform()` scales everything instantly (pixmap gets blurry on zoom-in)
- **Deferred re-render:** After 300ms of no zoom change, re-render visible pixmaps at the correct DPI in the background and swap them in
- Ctrl+mouse wheel zooms. Zoom range: 50% to 300%.
- Presets: Fit Width, Fit Page, and percentage values in a dropdown

### 6.4 Memory Budget

At 150 DPI, a letter-sized page pixmap is ~33MB uncompressed. With 5 pages loaded: ~165MB. Strategies:

- Aggressive unloading outside the buffer zone
- Convert to QPixmap (potentially GPU-backed) after receiving from render thread
- If memory is a concern, reduce base DPI to 120 (barely perceptible difference, 36% memory reduction)
- Target: under 500MB for a 500-page document at any scroll position

---

## 7. Text Search (Ctrl+F)

### 7.1 Search Architecture

Search operates on **extracted text data**, not on QGraphicsItems (since most pages aren't loaded).

- At open time, extract text for ALL pages using `page.get_text("text")` in the background thread (fast — just text, no positioning, ~1-3 seconds for a 500-page doc). Store as `list[str]` indexed by page number. Search is available once extraction completes; show "Indexing..." in the search bar until ready.
- Search bar: text input + Previous/Next buttons + match count + close button
- Matches highlighted with semi-transparent yellow `QGraphicsRectItem` overlays on loaded pages
- Jumping to a match on an unloaded page triggers that page's load

### 7.2 Search Features

- Case-insensitive by default, toggle for case-sensitive
- Wraps around at document end
- Current match highlighted distinctly from other matches (e.g., orange vs yellow)
- Escape closes search bar

---

## 8. Copy Text (Ctrl+C)

### 8.1 Selection Model

- Click and drag on the page creates a rubber-band selection rectangle
- All text spans whose bounding boxes intersect the selection are included
- Selected spans are highlighted with a blue semi-transparent overlay
- Ctrl+C copies the concatenated text (sorted by y-position then x-position) to the system clipboard
- Click anywhere to deselect
- Single-page selection only (no cross-page selection in MVP)

### 8.2 Interaction with Edit Mode

- Selection mode is the default mouse mode
- Double-click overrides to enter edit mode on that specific span
- While in edit mode, standard text selection within the span works normally (Ctrl+C copies selected text within the span)

---

## 9. UI Layout

```
+--------------------------------------------------------------+
|  File  |  Edit  |  View                           [- [] X]   |  <- Menu bar (future TOC sidebar toggle under View)
+--------------------------------------------------------------+
|  [Open] [Save] [SaveAs] | [Theme: v] [BG] [Font] | [Zoom v] |  <- Toolbar
|  [Find: ___________  < > x]         | [Page: [1] / 24]       |
+--------------------------------------------------------------+
|                                                                |
|                  +------------------------+                    |
|                  |                        |                    |
|                  |     PDF Page           |                    |  <- QGraphicsView (scrollable)
|                  |     (continuous)       |                    |
|                  |                        |                    |
|                  |                        |                    |
|                  +------------------------+                    |
|                                                                |
+--------------------------------------------------------------+
|  Ready  |  Page 1 of 24  |  Zoom: 100%                       |  <- Status bar
+--------------------------------------------------------------+
```

### 9.1 Toolbar Controls

- **Open** (Ctrl+O): File dialog filtered to `*.pdf`
- **Save** (Ctrl+S): Save with dirty-block processing. Disabled when no changes.
- **Save As** (Ctrl+Shift+S): Always available
- **Theme dropdown:** Light / Sepia / Dark / AMOLED Dark / Custom
- **BG Color button:** Opens color picker, auto-switches to Custom theme
- **Font Color button:** Opens color picker, auto-switches to Custom theme
- **Zoom dropdown:** 50%, 75%, 100%, 125%, 150%, 200%, 300%, Fit Width, Fit Page
- **Find bar** (Ctrl+F): Inline find with prev/next/count/close
- **Page indicator:** Editable spinbox showing current page / total. Type a number + Enter to jump.

### 9.2 Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+O | Open file |
| Ctrl+S | Save |
| Ctrl+Shift+S | Save As |
| Ctrl+F | Find |
| Ctrl+C | Copy selected text |
| Ctrl+Z | Undo |
| Ctrl+Y | Redo |
| Ctrl+Mouse Wheel | Zoom in/out |
| Page Up / Page Down | Scroll by viewport |
| Home / End | First / last page |
| Up / Down arrows | Scroll small increment |
| Space | Scroll down one viewport |
| Escape | Exit edit mode / close find bar |
| Tab (in edit mode) | Move to next text span |
| F5 | Toggle Faithful / Reading mode |

### 9.3 Drag and Drop

Main window accepts drag-and-drop of `.pdf` files. Drop opens the file (with unsaved-changes check if a document is already open).

---

## 10. Error Handling

| Scenario | Behavior |
|----------|----------|
| **Password-protected PDF** | Detect via `doc.needs_pass`. Show password dialog. Retry up to 3 times. Cancel returns to empty state. |
| **Scanned/image-only PDF** | Detect via empty `get_text("dict")` on first page. Show info toast: "This PDF is image-based. Text editing is not available." Viewer works normally; edit UI disabled. |
| **Corrupted PDF** | `fitz.open()` wrapped in try/except. Show error dialog. Per-page: `get_pixmap()` and `get_text()` wrapped in try/except. Failed pages show placeholder: "Page X could not be rendered." |
| **File locked by another app** | Catch `PermissionError` / `OSError` on open. Message: "Cannot open file — it may be locked by another application." |
| **Save fails (read-only / network)** | Catch exception on temp file creation. Fall back to Save As dialog targeting Documents folder. |
| **Font substitution on save** | One-time toast notification: "Some fonts were substituted." |
| **Text overflow on save** | Reduce font size incrementally. If still overflowing after minimum threshold, warn user which spans couldn't fit. |

---

## 11. Space Handling Heuristic

`page.get_text("dict")` sometimes omits spaces between spans. Instead of cross-referencing with `get_text("words")` (complex, fragile), use a gap heuristic:

For adjacent spans on the same line:
- Calculate the gap between span N's right edge and span N+1's left edge
- If gap > `0.3 * font_size`, insert a space when concatenating for search/copy
- Display-wise, spans are positioned independently so visual spacing is always correct

This handles ~90% of cases with minimal complexity.

---

## 12. Configuration Persistence

`config.json` in the application directory:

```json
{
  "theme": "dark",
  "custom_bg_color": "#1E1E1E",
  "custom_font_color": "#D4D4D4",
  "display_mode": "reading",
  "zoom_level": 100,
  "window_width": 1200,
  "window_height": 800,
  "window_x": 100,
  "window_y": 100,
  "last_opened_file": "C:/Users/Noah/Documents/example.pdf",
  "render_dpi": 150
}
```

Loaded on startup, saved on change (debounced 1 second). Missing keys use defaults. Corrupted file is replaced with defaults.

---

## 13. Project Structure

```
C:\Users\Noah\Documents\Tool_Projects\PDFViewer\
├── main.py                # Entry point, QApplication setup, main window
├── pdf_engine.py          # PyMuPDF wrapper: open, extract text, render pixmaps, save
├── page_renderer.py       # QGraphicsScene management, page items, lazy loading, render queue
├── text_overlay.py        # Text span items, edit mode swap, selection model
├── search.py              # Full-text search across pages, match highlighting
├── theme_engine.py        # Theme presets, color management, tint overlays
├── editor.py              # Edit tracking, dirty spans, undo stack
├── toolbar.py             # Toolbar widget, find bar, zoom controls, page navigator
├── config.py              # Config load/save/defaults
├── requirements.txt       # pymupdf, PySide6
├── fonts/                 # Bundled Noto Sans, Noto Serif, Liberation Mono
│   ├── NotoSans-Regular.ttf
│   ├── NotoSans-Bold.ttf
│   ├── NotoSans-Italic.ttf
│   ├── NotoSans-BoldItalic.ttf
│   ├── NotoSerif-Regular.ttf
│   ├── NotoSerif-Bold.ttf
│   ├── NotoSerif-Italic.ttf
│   ├── NotoSerif-BoldItalic.ttf
│   ├── LiberationMono-Regular.ttf
│   ├── LiberationMono-Bold.ttf
│   ├── LiberationMono-Italic.ttf
│   └── LiberationMono-BoldItalic.ttf
└── config.json            # User preferences (auto-generated at runtime)
```

---

## 14. Dependencies

```
pymupdf>=1.24.0
PySide6>=6.7.0
```

Python 3.11+ required. No other external dependencies.

---

## 15. Known Limitations (MVP)

- No TOC/bookmarks sidebar (layout space reserved; deferred to v1.1)
- No print functionality (user can print from any other PDF viewer)
- No recent files list (deferred to v1.1)
- No cross-page text selection
- No OCR for scanned PDFs
- Font substitution on save — edited text may look slightly different
- Very large pages (maps, posters >10,000pt) may render at reduced DPI
- Original text is covered on save, not truly removed from PDF structure
- No file association / installer (run via `python main.py`)

---

## 16. Success Criteria

1. Opens any standard text-based PDF and displays it faithfully
2. Switching to reading mode with Dark theme makes text comfortable to read
3. Double-clicking a text span allows editing; changes are saved correctly
4. Ctrl+F finds text across the document and navigates to matches
5. Scrolling through a 200+ page document feels smooth (no visible stutter)
6. Save produces a valid PDF that opens correctly in other viewers
7. HiDPI displays render crisply at 150%+ Windows scaling
