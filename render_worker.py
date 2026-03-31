"""Background thread for PDF pixmap rendering and text extraction."""

import queue
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from pdf_engine import PDFEngine


@dataclass
class RenderRequest:
    page_num: int
    dpi: int
    generation: int


@dataclass
class RenderResult:
    page_num: int
    generation: int
    image: QImage | None
    spans: list[dict] | None
    error: str | None = None


class RenderWorker(QThread):
    """Renders PDF pages on a background thread using its own fitz.Document."""

    result_ready = Signal(object)          # RenderResult
    search_text_ready = Signal(int, str)   # (page_num, text)
    search_index_complete = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine = PDFEngine()
        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._current_generation = 0

    def open_document(self, path: Path, password: str | None = None):
        needs_pass = self._engine.open(path)
        if needs_pass and password:
            self._engine.authenticate(password)

    def close_document(self):
        self._engine.close()

    def submit(self, request: RenderRequest):
        self._queue.put(("render", request))

    def request_search_index(self):
        self._queue.put(("search_index", None))

    def set_current_generation(self, gen: int):
        self._current_generation = gen

    def stop(self):
        self._running = False
        self._queue.put(("stop", None))

    def run(self):
        self._running = True
        while self._running:
            try:
                cmd, data = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if cmd == "stop":
                break
            elif cmd == "render":
                self._handle_render(data)
            elif cmd == "search_index":
                self._handle_search_index()

        self._engine.close()

    def _handle_render(self, request: RenderRequest):
        if request.generation < self._current_generation:
            return

        try:
            pixmap = self._engine.render_pixmap(request.page_num, dpi=request.dpi)
            if pixmap.alpha:
                fmt = QImage.Format.Format_RGBA8888
            else:
                fmt = QImage.Format.Format_RGB888
            img = QImage(pixmap.samples, pixmap.width, pixmap.height, pixmap.stride, fmt)
            img = img.copy()  # Must copy — pixmap memory may be freed

            spans = self._engine.extract_spans(request.page_num)

            if request.generation < self._current_generation:
                return

            self.result_ready.emit(
                RenderResult(page_num=request.page_num, generation=request.generation, image=img, spans=spans)
            )
        except Exception as e:
            self.result_ready.emit(
                RenderResult(page_num=request.page_num, generation=request.generation, image=None, spans=None, error=str(e))
            )

    def _handle_search_index(self):
        if not self._engine.is_open:
            self.search_index_complete.emit()
            return

        for i in range(self._engine.page_count):
            if not self._running:
                break
            try:
                text = self._engine.extract_page_text(i)
                self.search_text_ready.emit(i, text)
            except Exception:
                self.search_text_ready.emit(i, "")

        self.search_index_complete.emit()
