from PySide6.QtCore import QEventLoop, QTimer
from render_worker import RenderWorker, RenderRequest, RenderResult


def test_render_worker_produces_result(qapp, sample_pdf):
    worker = RenderWorker()
    results = []

    def on_result(result: RenderResult):
        results.append(result)

    worker.result_ready.connect(on_result)
    worker.start()
    worker.open_document(sample_pdf)
    worker.submit(RenderRequest(page_num=0, dpi=72, generation=1))

    loop = QEventLoop()
    worker.result_ready.connect(lambda _: loop.quit())
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    worker.stop()
    worker.wait()

    assert len(results) == 1
    assert results[0].page_num == 0
    assert results[0].generation == 1
    assert results[0].image is not None
    assert results[0].spans is not None
    assert len(results[0].spans) >= 2


def test_render_worker_extracts_search_text(qapp, sample_pdf):
    worker = RenderWorker()
    search_results = []

    def on_search(page_num: int, text: str):
        search_results.append((page_num, text))

    worker.search_text_ready.connect(on_search)
    worker.start()
    worker.open_document(sample_pdf)
    worker.request_search_index()

    loop = QEventLoop()
    worker.search_index_complete.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    worker.stop()
    worker.wait()

    assert len(search_results) == 1
    assert "Hello World" in search_results[0][1]


def test_render_worker_multipage_search_index(qapp, multipage_pdf):
    worker = RenderWorker()
    search_results = []

    worker.search_text_ready.connect(lambda pn, t: search_results.append((pn, t)))
    worker.start()
    worker.open_document(multipage_pdf)
    worker.request_search_index()

    loop = QEventLoop()
    worker.search_index_complete.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()

    worker.stop()
    worker.wait()

    assert len(search_results) == 10
    for i, (pn, text) in enumerate(sorted(search_results)):
        assert f"Page {pn + 1} content" in text
