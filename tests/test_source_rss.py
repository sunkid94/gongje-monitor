from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import time, importlib


def _entry(title, link, summary="", pub="2026-06-05 08:00:00"):
    e = MagicMock()
    e.get = lambda k, d="": {
        "title": title, "link": link, "summary": summary,
        "published_parsed": time.strptime(pub, "%Y-%m-%d %H:%M:%S"),
    }.get(k, d)
    return e


def _feed(entries):
    f = MagicMock(); f.entries = entries; return f


def _frozen_dt():
    fixed = datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc)  # 18:00 KST
    m = MagicMock(spec=datetime)
    m.now.side_effect = lambda tz=None: fixed
    m.fromtimestamp.side_effect = datetime.fromtimestamp
    return m


FEEDS = [{"name": "기계설비신문", "url": "http://feed/x"}]


def test_rss_keeps_company_relevant_with_suffix():
    import source_rss
    importlib.reload(source_rss)
    e = _entry("기계설비건설공제조합 신규 사업 발표", "http://kmec/1", "조합 소식")
    with patch("source_rss.feedparser.parse", return_value=_feed([e])), \
         patch("source_rss.TRADE_RSS_FEEDS", FEEDS), \
         patch("source_rss.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_rss.CATEGORY_KEYWORDS", {}):
        source_rss.datetime = _frozen_dt()
        out = source_rss.fetch()
    assert len(out) == 1
    assert out[0]["title"] == "기계설비건설공제조합 신규 사업 발표 - 기계설비신문"
    assert out[0]["is_company"] is True
    assert out[0]["link"] == "http://kmec/1"


def test_rss_drops_irrelevant_articles():
    import source_rss
    importlib.reload(source_rss)
    e = _entry("롯데건설 봉사활동 진행", "http://kmec/2", "사회공헌")
    with patch("source_rss.feedparser.parse", return_value=_feed([e])), \
         patch("source_rss.TRADE_RSS_FEEDS", FEEDS), \
         patch("source_rss.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_rss.CATEGORY_KEYWORDS", {}):
        source_rss.datetime = _frozen_dt()
        out = source_rss.fetch()
    assert out == []


def test_rss_classifies_industry_category():
    import source_rss
    importlib.reload(source_rss)
    e = _entry("스마트건설 기술 도입 확대", "http://kmec/3", "신기술")
    with patch("source_rss.feedparser.parse", return_value=_feed([e])), \
         patch("source_rss.TRADE_RSS_FEEDS", FEEDS), \
         patch("source_rss.COMPANY_KEYWORDS", []), \
         patch("source_rss.CATEGORY_KEYWORDS", {"신기술": ["스마트건설"]}):
        source_rss.datetime = _frozen_dt()
        out = source_rss.fetch()
    assert len(out) == 1
    assert out[0]["is_company"] is False
    assert out[0]["category"] == "신기술"


def test_rss_feed_error_isolated():
    import source_rss
    importlib.reload(source_rss)
    with patch("source_rss.feedparser.parse", side_effect=RuntimeError("down")), \
         patch("source_rss.TRADE_RSS_FEEDS", FEEDS), \
         patch("source_rss.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_rss.CATEGORY_KEYWORDS", {}):
        source_rss.datetime = _frozen_dt()
        out = source_rss.fetch()
    assert out == []


def test_rss_skips_seen_and_old():
    import source_rss
    importlib.reload(source_rss)
    seen_entry = _entry("기계설비건설공제조합 소식", "http://kmec/seen", "조합")
    old_entry = _entry("기계설비건설공제조합 옛 소식", "http://kmec/old", "조합", pub="2026-06-01 00:00:00")
    with patch("source_rss.feedparser.parse", return_value=_feed([seen_entry, old_entry])), \
         patch("source_rss.TRADE_RSS_FEEDS", FEEDS), \
         patch("source_rss.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_rss.CATEGORY_KEYWORDS", {}):
        source_rss.datetime = _frozen_dt()
        out = source_rss.fetch(seen={"http://kmec/seen"})
    assert out == []   # 하나는 seen, 하나는 24h 밖
