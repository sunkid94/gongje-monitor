from datetime import datetime
from unittest.mock import patch, MagicMock
import time


FIXED_NOW = datetime(2026, 4, 18, 12, 0, 0)

MOCK_FEED_ENTRY = MagicMock()
MOCK_FEED_ENTRY.get = lambda key, default="": {
    "title": "기계설비건설공제조합 신규 공시",
    "link": "http://news.google.com/articles/1",
    "summary": "기계설비건설공제조합이 신규 사업 계획을 발표했다.",
    "published_parsed": time.strptime("2026-04-18 10:00:00", "%Y-%m-%d %H:%M:%S"),
}.get(key, default)


def _mock_feed(entries):
    feed = MagicMock()
    feed.entries = entries
    return feed


def _make_datetime_mock():
    mock_dt = MagicMock(spec=datetime)
    mock_dt.now.return_value = FIXED_NOW
    mock_dt.fromtimestamp.side_effect = datetime.fromtimestamp
    return mock_dt


def test_fetch_news_rss_returns_articles():
    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])), \
         patch("crawler.KEYWORDS", ["기계설비건설공제조합"]):
        import crawler
        import importlib
        importlib.reload(crawler)
        result = crawler.fetch_news_rss("기계설비건설공제조합")

    assert len(result) == 1
    assert result[0]["keyword"] == "기계설비건설공제조합"
    assert result[0]["link"] == "http://news.google.com/articles/1"
    assert result[0]["title"] == "기계설비건설공제조합 신규 공시"


def test_fetch_new_articles_excludes_seen_urls():
    import crawler
    import importlib

    mock_dt = _make_datetime_mock()

    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])), \
         patch("crawler.KEYWORDS", ["기계설비건설공제조합"]), \
         patch("crawler.INDUSTRY_KEYWORDS", []):
        importlib.reload(crawler)
        crawler.datetime = mock_dt
        result = crawler.fetch_new_articles({"http://news.google.com/articles/1"})

    assert result == []


def test_fetch_new_articles_includes_unseen_urls():
    import crawler
    import importlib

    mock_dt = _make_datetime_mock()

    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])), \
         patch("crawler.KEYWORDS", ["기계설비건설공제조합"]), \
         patch("crawler.INDUSTRY_KEYWORDS", []):
        importlib.reload(crawler)
        crawler.datetime = mock_dt
        result = crawler.fetch_new_articles(set())

    assert len(result) == 1
    assert result[0]["link"] == "http://news.google.com/articles/1"


def test_fetch_new_articles_excludes_old_articles():
    import crawler
    import importlib

    mock_dt = _make_datetime_mock()

    old_entry = MagicMock()
    old_entry.get = lambda key, default="": {
        "title": "오래된 기사",
        "link": "http://news.google.com/articles/old",
        "summary": "오래된 내용",
        "published_parsed": time.strptime("2024-01-01 10:00:00", "%Y-%m-%d %H:%M:%S"),
    }.get(key, default)

    with patch("crawler.feedparser.parse", return_value=_mock_feed([old_entry])), \
         patch("crawler.KEYWORDS", ["기계설비건설공제조합"]), \
         patch("crawler.INDUSTRY_KEYWORDS", []):
        importlib.reload(crawler)
        crawler.datetime = mock_dt
        result = crawler.fetch_new_articles(set())

    assert result == []
