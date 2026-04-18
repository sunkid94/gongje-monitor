from unittest.mock import MagicMock, patch


def test_summarize_article_returns_text():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="  건설공제조합이 MOU를 체결했다. 법률 지원이 강화될 전망이다.  ")]
    )
    with patch("summarizer._get_client", return_value=mock_client):
        import summarizer
        result = summarizer.summarize_article("테스트 제목", "테스트 내용")

    assert result == "건설공제조합이 MOU를 체결했다. 법률 지원이 강화될 전망이다."


def test_summarize_article_returns_none_on_api_error():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API Error")
    with patch("summarizer._get_client", return_value=mock_client):
        import summarizer
        result = summarizer.summarize_article("제목", "내용")

    assert result is None


def test_summarize_articles_adds_summary_field():
    with patch("summarizer.summarize_article", return_value="테스트 요약"):
        import summarizer
        articles = [
            {"keyword": "건설공제조합", "title": "제목", "description": "내용", "link": "http://l/1"},
        ]
        result = summarizer.summarize_articles(articles)

    assert result[0]["summary"] == "테스트 요약"
    assert result[0]["keyword"] == "건설공제조합"
    assert result[0]["link"] == "http://l/1"


def test_summarize_articles_handles_none_summary():
    with patch("summarizer.summarize_article", return_value=None):
        import summarizer
        articles = [
            {"keyword": "건설경기", "title": "제목", "description": "내용", "link": "http://l/2"},
        ]
        result = summarizer.summarize_articles(articles)

    assert result[0]["summary"] is None


def test_summarize_articles_preserves_all_fields():
    with patch("summarizer.summarize_article", return_value="요약"):
        import summarizer
        articles = [
            {
                "keyword": "건설공제조합",
                "title": "제목",
                "description": "내용",
                "link": "http://l/3",
                "extra_field": "extra",
            },
        ]
        result = summarizer.summarize_articles(articles)

    assert result[0]["extra_field"] == "extra"
    assert result[0]["summary"] == "요약"
