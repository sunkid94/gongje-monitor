from unittest.mock import patch, MagicMock
import pytest


SAMPLE_ARTICLE = {
    "keyword": "기계설비건설공제조합",
    "title": "기계설비건설공제조합, 신규 사업 발표",
    "link": "http://news.example.com/1",
    "description": "기계설비건설공제조합이 올해 신규 사업 계획을 발표했다.",
    "pubDate": "Fri, 11 Apr 2026 10:00:00 +0900",
}


def _make_mock_client(response_text: str):
    mock_content = MagicMock()
    mock_content.text = response_text
    mock_message = MagicMock()
    mock_message.content = [mock_content]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    return mock_client


def test_summarize_article_returns_summary_and_importance():
    mock_client = _make_mock_client("요약: 기계설비건설공제조합이 신규 사업을 발표했다.\n중요도: 긍정")

    with patch("summarizer.anthropic.Anthropic", return_value=mock_client), \
         patch("summarizer.ANTHROPIC_API_KEY", "test_key"):
        import summarizer
        import importlib
        importlib.reload(summarizer)
        result = summarizer.summarize_article(SAMPLE_ARTICLE)

    assert result["summary"] == "기계설비건설공제조합이 신규 사업을 발표했다."
    assert result["importance"] == "긍정"
    assert result["title"] == SAMPLE_ARTICLE["title"]
    assert result["link"] == SAMPLE_ARTICLE["link"]


def test_summarize_article_defaults_to_neutral_on_unknown_importance():
    mock_client = _make_mock_client("요약: 조합 관련 소식이 보도됐다.\n중요도: 알수없음")

    with patch("summarizer.anthropic.Anthropic", return_value=mock_client), \
         patch("summarizer.ANTHROPIC_API_KEY", "test_key"):
        import summarizer
        import importlib
        importlib.reload(summarizer)
        result = summarizer.summarize_article(SAMPLE_ARTICLE)

    assert result["importance"] == "중립"
