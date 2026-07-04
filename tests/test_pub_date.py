from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pub_date


GN_URL = "https://news.google.com/rss/articles/CBMiABCDEF?oc=5"
REAL_URL = "https://www.example.com/news/12345"


def _mock_response(status=200, text=""):
    m = MagicMock()
    m.status_code = status
    m.text = text
    m.url = text  # 디버그용
    return m


def test_extract_published_time_property_form():
    html = '<meta property="article:published_time" content="2021-02-26T08:55:00+09:00" />'
    dt = pub_date._extract_published_time(html)
    assert dt == datetime(2021, 2, 26, 8, 55, tzinfo=timezone(__import__("datetime").timedelta(hours=9)))


def test_extract_published_time_reversed_attr_order():
    html = '<meta content="2026-05-11T18:00:00+09:00" property="article:published_time" />'
    dt = pub_date._extract_published_time(html)
    assert dt is not None
    assert dt.year == 2026 and dt.month == 5 and dt.day == 11


def test_extract_published_time_itemprop():
    html = '<meta itemprop="datePublished" content="2024-12-01T12:00:00Z" />'
    dt = pub_date._extract_published_time(html)
    assert dt is not None
    assert dt.year == 2024


def test_extract_published_time_time_element():
    html = '<time datetime="2025-03-10T14:00:00+09:00">2025년 3월 10일</time>'
    dt = pub_date._extract_published_time(html)
    assert dt is not None
    assert dt.year == 2025 and dt.month == 3


def test_extract_published_time_returns_none_when_absent():
    html = "<html><body>no date here</body></html>"
    assert pub_date._extract_published_time(html) is None


def test_extract_published_time_skips_malformed():
    html = '<meta property="article:published_time" content="not-a-date" />'
    assert pub_date._extract_published_time(html) is None


def test_decode_google_news_url_returns_real_url():
    page_html = (
        '<html data-n-a-sg="SIGSIG" data-n-a-ts="1234567890">...</html>'
    )
    batch_response_text = (
        ")]}'\n"
        '[["wrb.fr","Fbv4je",'
        '"[\\"garturl\\",\\"https://www.example.com/news/12345\\",1234]",'
        'null,null,null,"generic"]]'
    )
    with patch("pub_date.requests.get", return_value=_mock_response(200, page_html)), \
         patch("pub_date.requests.post", return_value=_mock_response(200, batch_response_text)):
        url = pub_date._decode_google_news_url(GN_URL)
    assert url == REAL_URL


def test_decode_google_news_url_returns_none_on_bad_id():
    assert pub_date._decode_google_news_url("https://news.google.com/foo") is None


def test_decode_google_news_url_returns_none_when_signature_missing():
    page_html = "<html>no signature here</html>"
    with patch("pub_date.requests.get", return_value=_mock_response(200, page_html)):
        url = pub_date._decode_google_news_url(GN_URL)
    assert url is None


def test_resolve_published_time_end_to_end():
    page_html = '<html data-n-a-sg="SIG" data-n-a-ts="999">x</html>'
    batch_text = (
        ")]}'\n"
        '[["wrb.fr","Fbv4je",'
        '"[\\"garturl\\",\\"https://www.example.com/news/12345\\",1]",'
        'null,null,null,"generic"]]'
    )
    source_html = '<meta property="article:published_time" content="2021-02-26T08:55:00+09:00" />'

    # 첫 GET = google news 페이지, 두번째 GET = 원문 페이지
    get_calls = [_mock_response(200, page_html), _mock_response(200, source_html)]

    def fake_get(*args, **kwargs):
        return get_calls.pop(0)

    with patch("pub_date.requests.get", side_effect=fake_get), \
         patch("pub_date.requests.post", return_value=_mock_response(200, batch_text)):
        dt = pub_date.resolve_published_time(GN_URL)

    assert dt is not None
    assert dt.year == 2021 and dt.month == 2 and dt.day == 26


def test_resolve_published_time_returns_none_on_network_error():
    import requests
    with patch("pub_date.requests.get", side_effect=requests.ConnectionError):
        assert pub_date.resolve_published_time(GN_URL) is None


def test_extract_content_og_description():
    html = '<meta property="og:description" content="기계설비공사의 중요성이 커지고 있다. 정부 정책도 뒷받침." />'
    assert "기계설비공사의 중요성" in pub_date._extract_content(html)


def test_extract_content_meta_description_fallback():
    html = '<html><head><meta name="description" content="본문 요약 내용입니다."></head></html>'
    assert pub_date._extract_content(html) == "본문 요약 내용입니다."


def test_extract_content_unescapes_and_collapses():
    html = '<meta property="og:description" content="A &amp; B\n  끝">'
    c = pub_date._extract_content(html)
    assert "&amp;" not in c and "A & B 끝" == c


def test_extract_content_returns_empty_when_absent():
    assert pub_date._extract_content("<html><body>메타 없음</body></html>") == ""


def test_resolve_published_time_and_content_returns_both():
    real_html = (
        '<meta property="article:published_time" content="2026-07-01T10:00:00+09:00" />'
        '<meta property="og:description" content="원문 리드 문장 내용입니다." />'
    )
    with patch("pub_date._decode_google_news_url", return_value=REAL_URL), \
         patch("pub_date.requests.get", return_value=_mock_response(200, real_html)):
        dt, content, url = pub_date.resolve_published_time_and_content(GN_URL)
    assert dt is not None and dt.year == 2026
    assert content == "원문 리드 문장 내용입니다."
    assert url == REAL_URL


def test_resolve_published_time_wrapper_still_returns_datetime():
    real_html = '<meta property="article:published_time" content="2026-07-01T10:00:00+09:00" />'
    with patch("pub_date._decode_google_news_url", return_value=REAL_URL), \
         patch("pub_date.requests.get", return_value=_mock_response(200, real_html)):
        dt = pub_date.resolve_published_time(GN_URL)
    assert dt is not None and dt.year == 2026


def test_extract_daum_og_regdate():
    from datetime import timedelta
    html = '<meta property="og:regDate" content="20260624160119">'
    dt = pub_date._extract_published_time(html)
    assert dt == datetime(2026, 6, 24, 16, 1, 19, tzinfo=timezone(timedelta(hours=9)))


def test_extract_nate_firstdate():
    from datetime import timedelta
    html = '<span class="firstDate">기사전송 <em>2026-07-03 13:57</em></span>'
    dt = pub_date._extract_published_time(html)
    assert dt == datetime(2026, 7, 3, 13, 57, tzinfo=timezone(timedelta(hours=9)))


def test_standard_meta_takes_priority_over_regdate():
    html = ('<meta property="article:published_time" content="2026-01-01T00:00:00+09:00">'
            '<meta property="og:regDate" content="20260624160119">')
    dt = pub_date._extract_published_time(html)
    assert dt.month == 1 and dt.day == 1   # 표준 메타가 우선


def test_regdate_before_nate_when_both_present():
    from datetime import timedelta
    html = ('<meta property="og:regDate" content="20260624160119">'
            '<span class="firstDate">기사전송 <em>2026-07-03 13:57</em></span>')
    dt = pub_date._extract_published_time(html)
    assert dt == datetime(2026, 6, 24, 16, 1, 19, tzinfo=timezone(timedelta(hours=9)))


def test_returns_none_when_no_date_anywhere():
    assert pub_date._extract_published_time('<html><body>날짜 없음</body></html>') is None
