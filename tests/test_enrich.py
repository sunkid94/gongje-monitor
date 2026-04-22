from enrich import normalize_title, extract_publisher


def test_normalize_title_strips_publisher_suffix():
    assert normalize_title("현대건설 사우디 수주 확대 - 조선비즈") == "현대건설사우디수주확대"


def test_normalize_title_removes_whitespace_and_punctuation():
    assert normalize_title('"태영건설" 워크아웃, 1주년…') == "태영건설워크아웃1주년"


def test_normalize_title_handles_no_suffix():
    assert normalize_title("그냥 제목") == "그냥제목"


def test_normalize_title_handles_multiple_dashes():
    # 마지막 " - " 만 제거
    assert normalize_title("A-B 논란 - 매경") == "ab논란"


def test_extract_publisher_returns_suffix():
    assert extract_publisher("현대건설 사우디 수주 확대 - 조선비즈") == "조선비즈"


def test_extract_publisher_returns_empty_when_no_suffix():
    assert extract_publisher("그냥 제목") == ""


def test_extract_publisher_trims_whitespace():
    assert extract_publisher("제목 -  머니투데이  ") == "머니투데이"


from enrich import cluster_articles


def _art(title, link):
    return {"title": title, "link": link, "description": ""}


def test_cluster_articles_assigns_cluster_id():
    articles = [_art("제목A", "l1"), _art("제목B", "l2")]
    result = cluster_articles(articles)
    assert "cluster_id" in result[0]
    assert result[0]["cluster_id"] != result[1]["cluster_id"]


def test_cluster_articles_groups_exact_normalized_match():
    articles = [
        _art("태영건설 워크아웃 1주년 - 조선비즈", "l1"),
        _art("태영건설 워크아웃 1주년 - 매경", "l2"),
    ]
    result = cluster_articles(articles)
    assert result[0]["cluster_id"] == result[1]["cluster_id"]


def test_cluster_articles_groups_jaccard_similar():
    # 토큰 자카드 >= 0.85 → 같은 cluster
    articles = [
        _art("태영건설 워크아웃 1주년 재무 개선 미흡", "l1"),
        _art("태영건설 워크아웃 1주년 재무개선 미흡", "l2"),  # 공백 1개 차이
    ]
    result = cluster_articles(articles)
    assert result[0]["cluster_id"] == result[1]["cluster_id"]


def test_cluster_articles_keeps_different_apart():
    articles = [
        _art("태영건설 워크아웃 1주년", "l1"),
        _art("현대건설 사우디 수주", "l2"),
    ]
    result = cluster_articles(articles)
    assert result[0]["cluster_id"] != result[1]["cluster_id"]


def test_cluster_articles_cluster_id_is_4char_hex():
    articles = [_art("제목", "l1")]
    result = cluster_articles(articles)
    assert len(result[0]["cluster_id"]) == 4
    assert all(c in "0123456789abcdef" for c in result[0]["cluster_id"])


import json
from unittest.mock import MagicMock, patch


def test_enrich_article_returns_summary_and_sentiment():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약입니다.", "sentiment": "negative"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용")

    assert result == {"summary": "요약입니다.", "sentiment": "negative"}


def test_enrich_article_falls_back_on_api_error():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API down")
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용이 200자 이상이어야 하는가 아닌가 테스트")

    assert result["sentiment"] == "neutral"
    assert "내용" in result["summary"]


def test_enrich_article_falls_back_on_invalid_json():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="This is not JSON at all.")]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "원문 내용")

    assert result["sentiment"] == "neutral"
    assert result["summary"] == "원문 내용"[:200]


def test_enrich_article_caps_description_fallback_at_200():
    long_desc = "가" * 500
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("down")
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", long_desc)

    assert len(result["summary"]) == 200


def test_enrich_article_strips_markdown_code_fence():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='```json\n{"summary": "요약", "sentiment": "positive"}\n```')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용")

    assert result == {"summary": "요약", "sentiment": "positive"}


def test_enrich_article_normalizes_invalid_sentiment():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "S", "sentiment": "mixed"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용")

    assert result["sentiment"] == "neutral"


from datetime import datetime, timedelta


def test_calc_importance_minimum_is_zero():
    from enrich import calc_importance
    art = {"is_company": False, "sentiment": "neutral", "collected_at": "2020-01-01T00:00:00"}
    assert calc_importance(art, cluster_size=1, now=datetime(2026, 4, 23)) == 1  # cluster_size 1 → +1


def test_calc_importance_company_plus_negative_plus_recent():
    from enrich import calc_importance
    now = datetime(2026, 4, 23, 12, 0, 0)
    recent = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    art = {"is_company": True, "sentiment": "negative", "collected_at": recent}
    # 5 (company) + 3 (neg) + 1 (cluster_size 1) + 2 (recent) = 11 → round(11*10/15)=7
    assert calc_importance(art, cluster_size=1, now=now) == 7


def test_calc_importance_caps_cluster_size_at_5():
    from enrich import calc_importance
    now = datetime(2026, 4, 23)
    art = {"is_company": False, "sentiment": "neutral", "collected_at": "2020-01-01T00:00:00"}
    # cluster_size 10 → 5 (capped) / 15 * 10 = 3.33 → round = 3
    assert calc_importance(art, cluster_size=10, now=now) == 3


def test_calc_importance_max_is_10():
    from enrich import calc_importance
    now = datetime(2026, 4, 23, 12, 0, 0)
    recent = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    art = {"is_company": True, "sentiment": "negative", "collected_at": recent}
    # 5 + 3 + 5 (cluster cap) + 2 = 15 → 10
    assert calc_importance(art, cluster_size=20, now=now) == 10


def test_calc_importance_handles_missing_collected_at():
    from enrich import calc_importance
    now = datetime(2026, 4, 23)
    art = {"is_company": False, "sentiment": "positive"}  # no collected_at
    # 0 + 0 + 1 + 0 = 1 → round(1*10/15) = 1
    assert calc_importance(art, cluster_size=1, now=now) == 1


def test_enrich_articles_full_pipeline():
    articles = [
        {
            "keyword": "기계설비건설공제조합",
            "category": "조합",
            "is_company": True,
            "title": "기계설비건설공제조합 신규 사업 - 조선비즈",
            "link": "http://x/1",
            "description": "신규 사업 발표",
        },
        {
            "keyword": "기계설비건설공제조합",
            "category": "조합",
            "is_company": True,
            "title": "기계설비건설공제조합 신규 사업 - 매경",
            "link": "http://x/2",
            "description": "신규 사업 발표",
        },
    ]

    with patch("enrich.enrich_article", return_value={"summary": "AI 요약", "sentiment": "positive"}):
        from enrich import enrich_articles
        result = enrich_articles(articles)

    # 같은 기사 묶임 (cluster_size=2)
    assert result[0]["cluster_id"] == result[1]["cluster_id"]
    # publisher 추출됨
    assert result[0]["publisher"] == "조선비즈"
    assert result[1]["publisher"] == "매경"
    # title_clean 은 매체명 제거됨
    assert result[0]["title_clean"] == "기계설비건설공제조합 신규 사업"
    # summary, sentiment 들어감
    assert result[0]["summary"] == "AI 요약"
    assert result[0]["sentiment"] == "positive"
    # importance 계산됨
    assert isinstance(result[0]["importance"], int)
    assert 0 <= result[0]["importance"] <= 10


def test_enrich_articles_preserves_original_fields():
    articles = [{
        "keyword": "kw", "category": "조합", "is_company": False,
        "title": "제목", "link": "l1", "description": "d",
        "extra": "keep me",
    }]
    with patch("enrich.enrich_article", return_value={"summary": "s", "sentiment": "neutral"}):
        from enrich import enrich_articles
        result = enrich_articles(articles)

    assert result[0]["extra"] == "keep me"


def test_enrich_articles_applies_recent_importance_boost():
    """방금 수집된 기사는 24h 가산점(+2)을 받아 importance 가 올라가야 한다."""
    articles = [{
        "keyword": "현대건설", "category": "종합건설사", "is_company": False,
        "title": "현대건설 사우디 수주 확대", "link": "l1", "description": "d",
    }]
    with patch("enrich.enrich_article", return_value={"summary": "s", "sentiment": "negative"}):
        from enrich import enrich_articles
        result = enrich_articles(articles)

    # neg(+3) + cluster=1(+1) + recent(+2) = 6 → round(6*10/15) = 4
    assert result[0]["importance"] == 4
