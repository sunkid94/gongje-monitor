from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import time


FIXED_NOW = datetime(2026, 4, 18, 12, 0, 0)
FIXED_NOW_UTC = FIXED_NOW.replace(tzinfo=timezone.utc)

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
    mock_dt.now.side_effect = lambda tz=None: FIXED_NOW_UTC if tz is not None else FIXED_NOW
    mock_dt.fromtimestamp.side_effect = datetime.fromtimestamp
    return mock_dt


def test_fetch_news_rss_returns_articles():
    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])), \
         patch("crawler.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("crawler.CATEGORY_KEYWORDS", {}):
        import crawler
        import importlib
        importlib.reload(crawler)
        result = crawler.fetch_news_rss("기계설비건설공제조합", category="조합·협회", is_company=True)

    assert len(result) == 1
    assert result[0]["keyword"] == "기계설비건설공제조합"
    assert result[0]["link"] == "http://news.google.com/articles/1"
    assert result[0]["title"] == "기계설비건설공제조합 신규 공시"


def test_fetch_new_articles_excludes_seen_urls():
    import crawler
    import importlib

    mock_dt = _make_datetime_mock()
    importlib.reload(crawler)

    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])), \
         patch("crawler.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("crawler.CATEGORY_KEYWORDS", {}):
        crawler.datetime = mock_dt
        result = crawler.fetch_new_articles({"http://news.google.com/articles/1"})

    assert result == []


def test_fetch_new_articles_includes_unseen_urls():
    import crawler
    import importlib

    mock_dt = _make_datetime_mock()
    importlib.reload(crawler)

    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])), \
         patch("crawler.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("crawler.CATEGORY_KEYWORDS", {}):
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

    importlib.reload(crawler)

    with patch("crawler.feedparser.parse", return_value=_mock_feed([old_entry])), \
         patch("crawler.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("crawler.CATEGORY_KEYWORDS", {}):
        crawler.datetime = mock_dt
        result = crawler.fetch_new_articles(set())

    assert result == []


def test_fetch_new_articles_drops_articles_with_old_original_pub_date():
    """Google News pubDate는 최근이지만 원문 발행일이 7일을 넘으면 폐기."""
    import crawler
    import importlib
    from datetime import datetime as _real_datetime, timezone

    mock_dt = _make_datetime_mock()
    importlib.reload(crawler)

    old_pub = _real_datetime(2021, 2, 26, 8, 55, tzinfo=timezone.utc)
    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])), \
         patch("crawler.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("crawler.CATEGORY_KEYWORDS", {}), \
         patch("crawler.resolve_published_time", return_value=old_pub):
        crawler.datetime = mock_dt
        result = crawler.fetch_new_articles(set())

    assert result == []


def test_fetch_new_articles_keeps_articles_with_recent_original_pub_date():
    """원문 발행일이 7일 이내면 통과하고 published_at 필드가 부착된다."""
    import crawler
    import importlib
    from datetime import datetime as _real_datetime, timezone

    mock_dt = _make_datetime_mock()
    importlib.reload(crawler)

    recent_pub = _real_datetime(2026, 4, 17, 9, 0, tzinfo=timezone.utc)  # FIXED_NOW-1d
    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])), \
         patch("crawler.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("crawler.CATEGORY_KEYWORDS", {}), \
         patch("crawler.resolve_published_time", return_value=recent_pub):
        crawler.datetime = mock_dt
        result = crawler.fetch_new_articles(set())

    assert len(result) == 1
    assert result[0]["published_at"] == recent_pub.isoformat()


def test_fetch_new_articles_keeps_when_pub_date_unresolvable():
    """원문 발행일을 못 가져오면 기사를 폐기하지 않는다 (보수적)."""
    import crawler
    import importlib

    mock_dt = _make_datetime_mock()
    importlib.reload(crawler)

    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])), \
         patch("crawler.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("crawler.CATEGORY_KEYWORDS", {}), \
         patch("crawler.resolve_published_time", return_value=None):
        crawler.datetime = mock_dt
        result = crawler.fetch_new_articles(set())

    assert len(result) == 1
    assert "published_at" not in result[0]


def test_fetch_news_rss_attaches_category_for_company_keyword():
    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])):
        import crawler
        import importlib
        importlib.reload(crawler)
        result = crawler.fetch_news_rss("기계설비건설공제조합", category="조합·협회", is_company=True)

    assert result[0]["category"] == "조합·협회"
    assert result[0]["is_company"] is True


def test_fetch_news_rss_attaches_category_for_industry_keyword():
    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])):
        import crawler
        import importlib
        importlib.reload(crawler)
        result = crawler.fetch_news_rss("건설 PF", category="시장·경기", is_company=False)

    assert result[0]["category"] == "시장·경기"
    assert result[0]["is_company"] is False


def test_fetch_new_articles_uses_category_keywords_dict():
    import crawler
    import importlib

    mock_dt = _make_datetime_mock()
    test_category_keywords = {"시장·경기": ["건설 PF"]}

    importlib.reload(crawler)

    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])), \
         patch("crawler.COMPANY_KEYWORDS", []), \
         patch("crawler.CATEGORY_KEYWORDS", test_category_keywords):
        crawler.datetime = mock_dt
        result = crawler.fetch_new_articles(set())

    assert len(result) == 1
    assert result[0]["category"] == "시장·경기"
    assert result[0]["is_company"] is False
