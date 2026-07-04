from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import time
import importlib

FIXED_NOW = datetime(2026, 4, 18, 12, 0, 0)
FIXED_NOW_UTC = FIXED_NOW.replace(tzinfo=timezone.utc)

MOCK_ENTRY = MagicMock()
MOCK_ENTRY.get = lambda key, default="": {
    "title": "기계설비건설공제조합 신규 공시 - 기계설비신문",
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


def test_fetch_keyword_returns_articles():
    with patch("source_google.feedparser.parse", return_value=_mock_feed([MOCK_ENTRY])):
        import source_google
        importlib.reload(source_google)
        result = source_google._fetch_keyword("기계설비건설공제조합", "조합·협회", True)
    assert len(result) == 1
    assert result[0]["keyword"] == "기계설비건설공제조합"
    assert result[0]["link"] == "http://news.google.com/articles/1"
    assert result[0]["is_company"] is True


def test_fetch_excludes_old_articles():
    import source_google
    importlib.reload(source_google)
    old = MagicMock()
    old.get = lambda key, default="": {
        "title": "오래된 기사 - 매체", "link": "http://news.google.com/articles/old",
        "summary": "오래된 내용",
        "published_parsed": time.strptime("2024-01-01 10:00:00", "%Y-%m-%d %H:%M:%S"),
    }.get(key, default)
    with patch("source_google.feedparser.parse", return_value=_mock_feed([old])), \
         patch("source_google.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_google.CATEGORY_KEYWORDS", {}):
        source_google.datetime = _make_datetime_mock()
        result = source_google.fetch()
    assert result == []


def test_fetch_drops_old_original_pub():
    import source_google
    importlib.reload(source_google)
    from datetime import datetime as _dt
    old_pub = _dt(2021, 2, 26, 8, 55, tzinfo=timezone.utc)
    with patch("source_google.feedparser.parse", return_value=_mock_feed([MOCK_ENTRY])), \
         patch("source_google.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_google.CATEGORY_KEYWORDS", {}), \
         patch("source_google.resolve_published_time_and_content", return_value=(old_pub, "", None)):
        source_google.datetime = _make_datetime_mock()
        result = source_google.fetch()
    assert result == []


def test_fetch_keeps_recent_original_pub_and_sets_published_at():
    import source_google
    importlib.reload(source_google)
    from datetime import datetime as _dt
    recent = _dt(2026, 4, 17, 9, 0, tzinfo=timezone.utc)
    with patch("source_google.feedparser.parse", return_value=_mock_feed([MOCK_ENTRY])), \
         patch("source_google.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_google.CATEGORY_KEYWORDS", {}), \
         patch("source_google.resolve_published_time_and_content", return_value=(recent, "", None)):
        source_google.datetime = _make_datetime_mock()
        result = source_google.fetch()
    assert len(result) == 1
    assert result[0]["published_at"] == recent.isoformat()


def test_fetch_keeps_when_pub_unresolvable():
    import source_google
    importlib.reload(source_google)
    with patch("source_google.feedparser.parse", return_value=_mock_feed([MOCK_ENTRY])), \
         patch("source_google.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_google.CATEGORY_KEYWORDS", {}), \
         patch("source_google.resolve_published_time_and_content", return_value=(None, "", None)):
        source_google.datetime = _make_datetime_mock()
        result = source_google.fetch()
    assert len(result) == 1
    assert "published_at" not in result[0]


def test_fetch_dedups_same_link_across_keywords():
    # 같은 기사가 두 키워드에 걸려도 1건만
    import source_google
    importlib.reload(source_google)
    with patch("source_google.feedparser.parse", return_value=_mock_feed([MOCK_ENTRY])), \
         patch("source_google.COMPANY_KEYWORDS", ["기계설비건설공제조합", "건설공제조합"]), \
         patch("source_google.CATEGORY_KEYWORDS", {}), \
         patch("source_google.resolve_published_time_and_content", return_value=(None, "", None)):
        source_google.datetime = _make_datetime_mock()
        result = source_google.fetch()
    assert len(result) == 1


def test_fetch_skips_seen_before_resolve():
    # seen 에 있는 link 는 원문 페치(resolve) 호출 없이 건너뜀
    import source_google
    importlib.reload(source_google)
    with patch("source_google.feedparser.parse", return_value=_mock_feed([MOCK_ENTRY])), \
         patch("source_google.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_google.CATEGORY_KEYWORDS", {}), \
         patch("source_google.resolve_published_time_and_content") as mock_resolve:
        source_google.datetime = _make_datetime_mock()
        result = source_google.fetch(seen={"http://news.google.com/articles/1"})
    assert result == []
    mock_resolve.assert_not_called()


def test_fetch_replaces_thin_description_with_fetched_content():
    # 원문 발행사 요약(콘텐츠)이 있으면 얇은 구글 description 을 그것으로 교체
    import source_google
    importlib.reload(source_google)
    from datetime import datetime as _dt
    recent = _dt(2026, 4, 17, 9, 0, tzinfo=timezone.utc)
    content = "원문 발행사가 제공한 실제 기사 리드 문장으로, 40자를 확실히 넘기는 충분한 길이의 콘텐츠."
    with patch("source_google.feedparser.parse", return_value=_mock_feed([MOCK_ENTRY])), \
         patch("source_google.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_google.CATEGORY_KEYWORDS", {}), \
         patch("source_google.resolve_published_time_and_content", return_value=(recent, content, None)):
        source_google.datetime = _make_datetime_mock()
        result = source_google.fetch()
    assert len(result) == 1
    assert result[0]["description"] == content


def test_fetch_keeps_original_description_when_no_content():
    # 콘텐츠가 없으면(빈 문자열) 기존 description 유지
    import source_google
    importlib.reload(source_google)
    from datetime import datetime as _dt
    recent = _dt(2026, 4, 17, 9, 0, tzinfo=timezone.utc)
    with patch("source_google.feedparser.parse", return_value=_mock_feed([MOCK_ENTRY])), \
         patch("source_google.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_google.CATEGORY_KEYWORDS", {}), \
         patch("source_google.resolve_published_time_and_content", return_value=(recent, "", None)):
        source_google.datetime = _make_datetime_mock()
        result = source_google.fetch()
    assert len(result) == 1
    assert result[0]["description"] == MOCK_ENTRY.get("summary", "")


def test_fetch_drops_image_popup_link():
    # 구글 링크가 etnews 이미지 팝업으로 디코딩되면 그 기사는 제외
    # (클릭 시 본문 대신 사진만 뜨는 깨진 링크 — 같은 기사는 etnews.com 직접경로로 정상 유입)
    import source_google
    importlib.reload(source_google)
    from datetime import datetime as _dt
    recent = _dt(2026, 4, 17, 9, 0, tzinfo=timezone.utc)
    popup = "https://www.etnews.com/tools/image_popup.html?v=abc123"
    with patch("source_google.feedparser.parse", return_value=_mock_feed([MOCK_ENTRY])), \
         patch("source_google.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_google.CATEGORY_KEYWORDS", {}), \
         patch("source_google.resolve_published_time_and_content", return_value=(recent, "", popup)):
        source_google.datetime = _make_datetime_mock()
        result = source_google.fetch()
    assert result == []


def test_fetch_naive_original_pub_treated_as_kst():
    # tz 없는 원문 발행시각은 UTC 가 아니라 KST 로 저장 (발행일 +9h 밀림 방지)
    import source_google
    importlib.reload(source_google)
    from datetime import datetime as _dt
    naive = _dt(2026, 4, 17, 18, 0)  # tz 없음 (한국사이트 KST 로 해석돼야)
    with patch("source_google.feedparser.parse", return_value=_mock_feed([MOCK_ENTRY])), \
         patch("source_google.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_google.CATEGORY_KEYWORDS", {}), \
         patch("source_google.resolve_published_time_and_content", return_value=(naive, "", None)):
        source_google.datetime = _make_datetime_mock()
        result = source_google.fetch()
    assert len(result) == 1
    assert result[0]["published_at"].endswith("+09:00")
    assert result[0]["published_at"].startswith("2026-04-17T18:00:00")
