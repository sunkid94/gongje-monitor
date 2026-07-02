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
    assert out[0]["keyword"] == "기계설비건설공제조합"


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
    assert out[0]["keyword"] == "스마트건설"


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


def test_rss_body_fallback_catches_body_only_mention():
    """제목·요약엔 없고 본문에만 조직명이 있는 기사 — 본문 페치로 포착."""
    import source_rss
    importlib.reload(source_rss)
    e = _entry("3대 메가프로젝트가 여는 기계설비 시대", "http://kmec/body", "업계 트렌드 분석")
    body_html = "<html><body>...대한기계설비건설협회는 이번에...</body></html>"
    with patch("source_rss.feedparser.parse", return_value=_feed([e])), \
         patch("source_rss.TRADE_RSS_FEEDS", FEEDS), \
         patch("source_rss.COMPANY_KEYWORDS", ["대한기계설비건설협회"]), \
         patch("source_rss.CATEGORY_KEYWORDS", {}), \
         patch("source_rss.requests.get", return_value=MagicMock(text=body_html, status_code=200)):
        source_rss.datetime = _frozen_dt()
        out = source_rss.fetch()
    assert len(out) == 1
    assert out[0]["is_company"] is True
    assert out[0]["keyword"] == "대한기계설비건설협회"
    assert out[0]["link"] == "http://kmec/body"


def test_rss_body_fallback_skips_when_body_also_irrelevant():
    """제목·요약·본문 모두 무관하면 버림 (본문은 한 번만 페치)."""
    import source_rss
    importlib.reload(source_rss)
    e = _entry("어느 회사 봉사활동", "http://kmec/none", "사회공헌 소식")
    getter = MagicMock(return_value=MagicMock(text="<html>무관한 본문</html>", status_code=200))
    with patch("source_rss.feedparser.parse", return_value=_feed([e])), \
         patch("source_rss.TRADE_RSS_FEEDS", FEEDS), \
         patch("source_rss.COMPANY_KEYWORDS", ["대한기계설비건설협회"]), \
         patch("source_rss.CATEGORY_KEYWORDS", {}), \
         patch("source_rss.requests.get", getter):
        source_rss.datetime = _frozen_dt()
        out = source_rss.fetch()
    assert out == []
    assert getter.call_count == 1  # 본문 페치는 1회만


def test_rss_body_not_fetched_when_title_matches():
    """제목/요약에서 이미 매칭되면 본문 페치하지 않음 (비용 절약)."""
    import source_rss
    importlib.reload(source_rss)
    e = _entry("대한기계설비건설협회 총회 개최", "http://kmec/fast", "협회 소식")
    getter = MagicMock(return_value=MagicMock(text="", status_code=200))
    with patch("source_rss.feedparser.parse", return_value=_feed([e])), \
         patch("source_rss.TRADE_RSS_FEEDS", FEEDS), \
         patch("source_rss.COMPANY_KEYWORDS", ["대한기계설비건설협회"]), \
         patch("source_rss.CATEGORY_KEYWORDS", {}), \
         patch("source_rss.requests.get", getter):
        source_rss.datetime = _frozen_dt()
        out = source_rss.fetch()
    assert len(out) == 1
    assert getter.call_count == 0  # 제목 매칭 시 본문 미페치


def test_rss_keeps_when_pubdate_unknown_without_published_at():
    import source_rss
    importlib.reload(source_rss)
    e = MagicMock()
    e.get = lambda k, d="": {"title": "기계설비건설공제조합 공지", "link": "http://kmec/np", "summary": "조합"}.get(k, d)
    # published_parsed 없음 → 보수적으로 유지, published_at 키 없음
    with patch("source_rss.feedparser.parse", return_value=_feed([e])), \
         patch("source_rss.TRADE_RSS_FEEDS", FEEDS), \
         patch("source_rss.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_rss.CATEGORY_KEYWORDS", {}):
        source_rss.datetime = _frozen_dt()
        out = source_rss.fetch()
    assert len(out) == 1
    assert "published_at" not in out[0]


def test_published_at_naive_kst_pubdate_corrected():
    # tz 없는 naive pubDate('2026-07-02 17:23:55')는 KST 로 해석 (feedparser UTC 오해 교정)
    import source_rss
    importlib.reload(source_rss)
    from datetime import datetime, timezone
    e = MagicMock()
    e.get = lambda k, d="": {
        "published": "2026-07-02 17:23:55",
        "published_parsed": time.strptime("2026-07-02 17:23:55", "%Y-%m-%d %H:%M:%S"),
    }.get(k, d)
    cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
    iso, recent = source_rss._published_at(e, cutoff)
    assert recent is True
    assert iso == "2026-07-02T17:23:55+09:00"


def test_published_at_tzaware_pubdate_kept():
    # tz 표기 있는 pubDate 는 feedparser 값(UTC) 유지
    import source_rss
    importlib.reload(source_rss)
    from datetime import datetime, timezone
    e = MagicMock()
    e.get = lambda k, d="": {
        "published": "Wed, 02 Jul 2026 08:23:55 +0000",
        "published_parsed": time.strptime("2026-07-02 08:23:55", "%Y-%m-%d %H:%M:%S"),
    }.get(k, d)
    cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
    iso, recent = source_rss._published_at(e, cutoff)
    assert iso == "2026-07-02T08:23:55+00:00"
