from unittest.mock import patch, MagicMock
import pytest


MOCK_API_RESPONSE = {
    "items": [
        {
            "title": "<b>기계설비</b>건설공제조합 신규 공시",
            "link": "http://news.example.com/1",
            "description": "기계설비건설공제조합이 <b>신규</b> 사업 계획을 발표했다.",
            "pubDate": "Fri, 11 Apr 2026 10:00:00 +0900",
        }
    ]
}


def test_search_news_strips_html_tags():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("crawler.requests.get", return_value=mock_resp), \
         patch("crawler.NAVER_CLIENT_ID", "test_id"), \
         patch("crawler.NAVER_CLIENT_SECRET", "test_secret"):
        import crawler
        import importlib
        importlib.reload(crawler)
        result = crawler.search_news("기계설비건설공제조합")

    assert len(result) == 1
    assert "<b>" not in result[0]["title"]
    assert "<b>" not in result[0]["description"]
    assert result[0]["keyword"] == "기계설비건설공제조합"
    assert result[0]["link"] == "http://news.example.com/1"


def test_fetch_new_articles_excludes_seen_urls():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    seen = {"http://news.example.com/1"}

    with patch("crawler.requests.get", return_value=mock_resp), \
         patch("crawler.NAVER_CLIENT_ID", "test_id"), \
         patch("crawler.NAVER_CLIENT_SECRET", "test_secret"), \
         patch("crawler.KEYWORDS", ["기계설비건설공제조합"]):
        import crawler
        import importlib
        importlib.reload(crawler)
        result = crawler.fetch_new_articles(seen)

    assert result == []


def test_fetch_new_articles_includes_unseen_urls():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    seen = set()

    with patch("crawler.requests.get", return_value=mock_resp), \
         patch("crawler.NAVER_CLIENT_ID", "test_id"), \
         patch("crawler.NAVER_CLIENT_SECRET", "test_secret"), \
         patch("crawler.KEYWORDS", ["기계설비건설공제조합"]):
        import crawler
        import importlib
        importlib.reload(crawler)
        result = crawler.fetch_new_articles(seen)

    assert len(result) == 1
    assert result[0]["link"] == "http://news.example.com/1"
