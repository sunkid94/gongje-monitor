from unittest.mock import patch
import crawler


def _article(link):
    return {"keyword": "k", "category": "조합·협회", "is_company": True,
            "title": "제목 - 매체", "link": link, "description": "d"}


def _source(items=None, raises=None):
    """테스트용 소스 스텁 — fetch(seen) 시그니처."""
    def fetch(seen=frozenset()):
        if raises:
            raise raises
        return list(items or [])
    return type("StubSource", (), {"fetch": staticmethod(fetch), "__name__": "stub"})


def test_aggregator_excludes_seen_links():
    with patch.object(crawler, "SOURCES", [_source([_article("http://a/1")])]):
        result = crawler.fetch_new_articles({"http://a/1"})
    assert result == []


def test_aggregator_includes_unseen_links():
    with patch.object(crawler, "SOURCES", [_source([_article("http://a/2")])]):
        result = crawler.fetch_new_articles(set())
    assert len(result) == 1
    assert result[0]["link"] == "http://a/2"


def test_aggregator_dedups_same_link_across_sources():
    with patch.object(crawler, "SOURCES", [_source([_article("http://dup")]), _source([_article("http://dup")])]):
        result = crawler.fetch_new_articles(set())
    assert len(result) == 1


def test_aggregator_continues_when_a_source_raises():
    with patch.object(crawler, "SOURCES", [_source(raises=RuntimeError("x")), _source([_article("http://ok")])]):
        result = crawler.fetch_new_articles(set())
    assert len(result) == 1
    assert result[0]["link"] == "http://ok"
