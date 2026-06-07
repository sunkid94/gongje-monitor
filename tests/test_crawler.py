from unittest.mock import patch
import crawler


def _article(link):
    return {"keyword": "k", "category": "조합·협회", "is_company": True,
            "title": "제목 - 매체", "link": link, "description": "d"}


def test_aggregator_excludes_seen_links():
    with patch.object(crawler, "SOURCES", [type("S", (), {"fetch": staticmethod(lambda: [_article("http://a/1")]), "__name__": "s"})]):
        result = crawler.fetch_new_articles({"http://a/1"})
    assert result == []


def test_aggregator_includes_unseen_links():
    with patch.object(crawler, "SOURCES", [type("S", (), {"fetch": staticmethod(lambda: [_article("http://a/2")]), "__name__": "s"})]):
        result = crawler.fetch_new_articles(set())
    assert len(result) == 1
    assert result[0]["link"] == "http://a/2"


def test_aggregator_dedups_same_link_across_sources():
    s1 = type("S1", (), {"fetch": staticmethod(lambda: [_article("http://dup")]), "__name__": "s1"})
    s2 = type("S2", (), {"fetch": staticmethod(lambda: [_article("http://dup")]), "__name__": "s2"})
    with patch.object(crawler, "SOURCES", [s1, s2]):
        result = crawler.fetch_new_articles(set())
    assert len(result) == 1


def test_aggregator_continues_when_a_source_raises():
    bad = type("Bad", (), {"fetch": staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("x"))), "__name__": "bad"})
    good = type("Good", (), {"fetch": staticmethod(lambda: [_article("http://ok")]), "__name__": "good"})
    with patch.object(crawler, "SOURCES", [bad, good]):
        result = crawler.fetch_new_articles(set())
    assert len(result) == 1
    assert result[0]["link"] == "http://ok"
