from search import SearchEngine


def test_search_engine_empty():
    engine = SearchEngine()
    results = engine.search("hello")
    assert results == []


def test_search_engine_add_page():
    engine = SearchEngine()
    engine.set_page_text(0, "Hello World this is a test")
    engine.set_page_text(1, "Another page with different content")
    results = engine.search("hello")
    assert len(results) == 1
    assert results[0]["page"] == 0


def test_search_case_insensitive():
    engine = SearchEngine()
    engine.set_page_text(0, "Hello WORLD")
    results = engine.search("hello world", case_sensitive=False)
    assert len(results) == 1


def test_search_case_sensitive():
    engine = SearchEngine()
    engine.set_page_text(0, "Hello WORLD")
    results = engine.search("hello", case_sensitive=True)
    assert len(results) == 0
    results = engine.search("Hello", case_sensitive=True)
    assert len(results) == 1


def test_search_multiple_matches_per_page():
    engine = SearchEngine()
    engine.set_page_text(0, "cat and dog and cat again")
    results = engine.search("cat")
    assert len(results) == 2
    assert results[0]["page"] == 0
    assert results[1]["page"] == 0


def test_search_across_pages():
    engine = SearchEngine()
    engine.set_page_text(0, "first page with target word")
    engine.set_page_text(1, "second page no match")
    engine.set_page_text(2, "third page with target here")
    results = engine.search("target")
    assert len(results) == 2
    assert results[0]["page"] == 0
    assert results[1]["page"] == 2


def test_search_returns_match_positions():
    engine = SearchEngine()
    engine.set_page_text(0, "Hello World")
    results = engine.search("World")
    assert len(results) == 1
    assert results[0]["start"] == 6
    assert results[0]["end"] == 11


def test_search_total_count():
    engine = SearchEngine()
    engine.set_page_text(0, "aaa aaa")
    engine.set_page_text(1, "aaa")
    results = engine.search("aaa")
    assert len(results) == 3


def test_search_empty_query():
    engine = SearchEngine()
    engine.set_page_text(0, "some text")
    results = engine.search("")
    assert results == []


def test_clear_index():
    engine = SearchEngine()
    engine.set_page_text(0, "some text")
    engine.clear()
    results = engine.search("text")
    assert results == []


def test_is_ready():
    engine = SearchEngine()
    assert not engine.is_ready
    engine.set_page_text(0, "text")
    engine.mark_ready()
    assert engine.is_ready
