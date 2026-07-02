from enrich import normalize_title, extract_publisher
import enrich


def test_relevance_criteria_excludes_venue_only_entertainment():
    # 게이트 강화: 조직이 행사 장소로만 등장 + 연예/시상식 주제 → false 규칙 포함
    c = enrich._RELEVANCE_CRITERIA
    assert "장소" in c and "시상식" in c and "연예" in c


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


def test_enrich_article_fallback_strips_html():
    # API 실패 시 폴백 요약에 raw HTML/엔티티가 새지 않아야 함 (구글뉴스 HTML description)
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("down")
    html_desc = '<a href="https://news.google.com/x">[The 초점]기계설비공사의 중요성</a>&nbsp;<font color="#6f6f6f">'
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        r = enrich_article("제목", html_desc)
    assert "<a" not in r["summary"] and "href" not in r["summary"]
    assert "&nbsp;" not in r["summary"] and "<font" not in r["summary"]
    assert "기계설비공사의 중요성" in r["summary"]


def test_enrich_article_retries_once_on_parse_failure():
    # 첫 응답이 빈 문자열(char 0) → 1회 재시도 → 유효 JSON → 폴백 아닌 정상 결과
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        MagicMock(content=[MagicMock(text="")]),
        MagicMock(content=[MagicMock(text='{"summary": "정상 요약", "sentiment": "neutral"}')]),
    ]
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        r = enrich_article("제목", "본문 내용")
    assert r["summary"] == "정상 요약"
    assert mock_client.messages.create.call_count == 2


def test_enrich_article_cleans_html_from_model_input():
    # description 의 HTML 이 모델에 raw 로 전달되지 않고 정제된 텍스트로 들어감
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "s", "sentiment": "neutral"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        enrich_article("제목", '<a href="http://x">본문텍스트</a>&nbsp;끝')
    sent = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "<a href" not in sent and "&nbsp;" not in sent
    assert "본문텍스트" in sent


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
            "category": "조합·협회",
            "is_company": True,
            "title": "기계설비건설공제조합 신규 사업 - 조선비즈",
            "link": "http://x/1",
            "description": "신규 사업 발표",
        },
        {
            "keyword": "기계설비건설공제조합",
            "category": "조합·협회",
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
        "keyword": "kw", "category": "조합·협회", "is_company": False,
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


def test_enrich_article_returns_about_org_when_orgs_given():
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "neutral", "about_org": false}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("성과급 칼럼", "노동법 해설", orgs=enrich._TRACKED_ORGS)
    assert result["about_org"] is False
    sent_prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "전문건설공제조합" in sent_prompt
    assert "K-FINCO" in sent_prompt
    assert "대한기계설비건설협회" in sent_prompt
    assert "CIG" in sent_prompt


def test_enrich_article_about_org_true():
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "positive", "about_org": true}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("조합 수주", "내용", orgs=enrich._TRACKED_ORGS)
    assert result["about_org"] is True


def test_enrich_article_no_orgs_omits_about_org_and_question():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "neutral"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용")
    assert "about_org" not in result
    sent_prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "about_org" not in sent_prompt


def test_enrich_article_orgs_given_but_field_missing_omits_about_org():
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "neutral"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용", orgs=enrich._TRACKED_ORGS)
    assert "about_org" not in result


def test_enrich_article_about_org_string_false_treated_as_drop():
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "neutral", "about_org": "false"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용", orgs=enrich._TRACKED_ORGS)
    assert result["about_org"] is False


def test_enrich_article_about_org_string_true_treated_as_keep():
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "neutral", "about_org": "true"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용", orgs=enrich._TRACKED_ORGS)
    assert result["about_org"] is True


def _mock_text(payload):
    return MagicMock(content=[MagicMock(text=payload)])


def test_enrich_articles_excludes_irrelevant_company_article():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_text('{"summary": "s", "sentiment": "neutral", "about_org": false}')
    articles = [{"title": "성과급 단체교섭 칼럼 - 기계설비신문", "description": "노동법 해설",
                 "link": "http://x/1", "keyword": "대한기계설비건설협회",
                 "category": "조합·협회", "is_company": True}]
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_articles
        result = enrich_articles(articles)
    assert result == []


def test_enrich_articles_keeps_relevant_company_article():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_text('{"summary": "s", "sentiment": "positive", "about_org": true}')
    articles = [{"title": "전문건설공제조합 피치 A+ 유지 - 이데일리", "description": "신용등급",
                 "link": "http://x/2", "keyword": "전문건설공제조합",
                 "category": "조합·협회", "is_company": True}]
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_articles
        result = enrich_articles(articles)
    assert len(result) == 1
    assert result[0]["is_company"] is True


def test_enrich_articles_keeps_when_about_org_missing():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_text('{"summary": "s", "sentiment": "neutral"}')
    articles = [{"title": "조합 관련 - 매체", "description": "내용", "link": "http://x/3",
                 "keyword": "건설공제조합", "category": "조합·협회", "is_company": True}]
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_articles
        result = enrich_articles(articles)
    assert len(result) == 1


def test_enrich_articles_keeps_on_api_error():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("down")
    articles = [{"title": "조합 관련 - 매체", "description": "내용", "link": "http://x/4",
                 "keyword": "건설공제조합", "category": "조합·협회", "is_company": True}]
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_articles
        result = enrich_articles(articles)
    assert len(result) == 1


def test_enrich_articles_non_company_not_relevance_filtered():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_text('{"summary": "s", "sentiment": "neutral", "about_org": false}')
    articles = [{"title": "삼성중공업 수주 - 매체", "description": "내용", "link": "http://x/5",
                 "keyword": "삼성중공업", "category": "종합건설사", "is_company": False}]
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_articles
        result = enrich_articles(articles)
    assert len(result) == 1


def test_enrich_articles_gate_uses_full_org_list_not_keyword():
    # 조합기사 판정 시 매칭 키워드 하나가 아니라 추적 조직 전체(별칭 포함)가 프롬프트에 들어가야 함
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "s", "sentiment": "neutral", "about_org": true}')]
    )
    # keyword 는 "엉뚱한" 조합인데도, 게이트는 전체 목록으로 물어야 함
    articles = [{"title": "대한기계설비건설협회, 직접발주 법제화 추진 - 매체", "description": "협회 활동",
                 "link": "http://x/협회", "keyword": "기계설비건설공제조합",
                 "category": "조합·협회", "is_company": True}]
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_articles
        result = enrich_articles(articles)
    assert len(result) == 1   # 협회 뉴스 → 통과
    sent_prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "대한기계설비건설협회" in sent_prompt
    assert "K-FINCO" in sent_prompt


def test_enrich_article_returns_event_label():
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary":"s","sentiment":"neutral","about_org":true,"event_label":"대한기계설비건설협회 박종학 회장 별세"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        r = enrich_article("박종학 별세", "부고", orgs=enrich._TRACKED_ORGS)
    assert r["event_label"] == "대한기계설비건설협회 박종학 회장 별세"
    sent = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "event_label" in sent


def test_enrich_article_no_event_label_without_orgs():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary":"s","sentiment":"neutral"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        r = enrich_article("제목", "내용")
    assert "event_label" not in r
    sent = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "event_label" not in sent


def test_enrich_article_event_label_missing_in_response_omitted():
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary":"s","sentiment":"neutral","about_org":true}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        r = enrich_article("제목", "내용", orgs=enrich._TRACKED_ORGS)
    assert "event_label" not in r


def test_enrich_articles_attaches_event_label():
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary":"s","sentiment":"neutral","about_org":true,"event_label":"전문건설공제조합 피치 A+ 유지"}')]
    )
    arts = [{"title": "K-FINCO 피치 A+ - 매체", "description": "d", "link": "l1",
             "keyword": "전문건설공제조합", "category": "조합·협회", "is_company": True}]
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_articles
        res = enrich_articles(arts)
    assert len(res) == 1
    assert res[0]["event_label"] == "전문건설공제조합 피치 A+ 유지"


def test_enrich_article_event_label_non_string_ignored():
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary":"s","sentiment":"neutral","about_org":true,"event_label":null}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        r = enrich_article("제목", "내용", orgs=enrich._TRACKED_ORGS)
    assert "event_label" not in r


def test_enrich_articles_excludes_blocked_publisher():
    # 브런치 등 블로그 발행처는 기사 아님 → enrich_articles에서 제외(AI 호출 전)
    import enrich
    arts = [
        {"title": "대한건설기계협회 이수증 발급방법 - 브런치", "description": "d",
         "link": "http://g", "keyword": "대한기계설비건설협회", "category": "조합·협회", "is_company": True},
        {"title": "전문건설공제조합 피치 A+ 유지 - 대한경제", "description": "d",
         "link": "http://h", "keyword": "전문건설공제조합", "category": "조합·협회", "is_company": True},
    ]
    with patch("enrich.enrich_article", return_value={"summary": "s", "sentiment": "neutral"}) as m, \
         patch.object(enrich, "BLOCKED_PUBLISHERS", ["브런치"]):
        out = enrich.enrich_articles(arts)
    titles = [o["title"] for o in out]
    assert not any("브런치" in t for t in titles)   # 브런치 제외
    assert any("대한경제" in t for t in titles)       # 정상 기사 유지
    # 브런치는 AI 호출 전에 걸러져 enrich_article 1회만(대한경제) 호출
    assert m.call_count == 1


# ─────────────────────────────────────────────────────────────
#  폴백 요약 감지 + enrich 실패 알림 (2026-06-26 추가)
# ─────────────────────────────────────────────────────────────
from datetime import datetime as _dt


def test_is_fallback_summary_true_when_equals_desc_prefix():
    from enrich import is_fallback_summary
    desc = "가" * 300
    assert is_fallback_summary(desc[:200], desc) is True


def test_is_fallback_summary_true_for_short_desc_copied():
    from enrich import is_fallback_summary
    assert is_fallback_summary("짧은 원문 그대로", "짧은 원문 그대로") is True


def test_is_fallback_summary_false_for_real_summary():
    from enrich import is_fallback_summary
    assert is_fallback_summary("AI가 다시 쓴 요약", "원문은 전혀 다른 긴 내용 " * 5) is False


def test_is_fallback_summary_false_for_empty_summary():
    from enrich import is_fallback_summary
    assert is_fallback_summary("", "") is False
    assert is_fallback_summary("", "내용") is False


def test_should_alert_true_when_rate_high_and_enough_sample():
    from enrich import should_alert
    now = _dt(2026, 6, 26, 9, 0, 0)
    assert should_alert(10, 9, None, now) is True


def test_should_alert_false_when_below_min_sample():
    from enrich import should_alert
    now = _dt(2026, 6, 26, 9, 0, 0)
    assert should_alert(3, 3, None, now) is False


def test_should_alert_false_when_rate_below_threshold():
    from enrich import should_alert
    now = _dt(2026, 6, 26, 9, 0, 0)
    assert should_alert(10, 4, None, now) is False


def test_should_alert_false_when_within_throttle():
    from enrich import should_alert
    now = _dt(2026, 6, 26, 9, 0, 0)
    last = _dt(2026, 6, 26, 5, 0, 0).isoformat()  # 4h 전 < 6h
    assert should_alert(10, 10, last, now) is False


def test_should_alert_true_when_throttle_elapsed():
    from enrich import should_alert
    now = _dt(2026, 6, 26, 9, 0, 0)
    last = _dt(2026, 6, 26, 1, 0, 0).isoformat()  # 8h 전 > 6h
    assert should_alert(10, 10, last, now) is True


def test_enrich_articles_alerts_with_counts_when_all_fallback():
    desc = "내용 " * 40
    arts = [{"title": f"조합 뉴스{i} - 매체", "description": desc, "link": f"l{i}",
             "keyword": "건설공제조합", "category": "조합·협회", "is_company": False}
            for i in range(6)]
    with patch("enrich.enrich_article", return_value={"summary": desc[:200], "sentiment": "neutral"}), \
         patch("enrich._maybe_alert_fallbacks") as alert:
        from enrich import enrich_articles
        enrich_articles(arts)
    alert.assert_called_once_with(6, 6)


def test_enrich_articles_reports_zero_fallbacks_when_healthy():
    arts = [{"title": "조합 수주 - 매체", "description": "원문 내용", "link": "l1",
             "keyword": "건설공제조합", "category": "조합·협회", "is_company": False}]
    with patch("enrich.enrich_article", return_value={"summary": "진짜 AI 요약", "sentiment": "positive"}), \
         patch("enrich._maybe_alert_fallbacks") as alert:
        from enrich import enrich_articles
        enrich_articles(arts)
    alert.assert_called_once_with(1, 0)


def test_maybe_alert_sends_and_writes_state_when_threshold_crossed(tmp_path):
    import enrich
    state = tmp_path / "state.json"
    with patch.object(enrich, "_ENRICH_ALERT_STATE", str(state)), \
         patch.object(enrich, "_send_enrich_alert") as send:
        enrich._maybe_alert_fallbacks(10, 9)
    send.assert_called_once()
    assert state.exists()


def test_maybe_alert_throttled_does_not_send(tmp_path):
    import enrich
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"last_alert": datetime.now().astimezone().isoformat()}))
    with patch.object(enrich, "_ENRICH_ALERT_STATE", str(state)), \
         patch.object(enrich, "_send_enrich_alert") as send:
        enrich._maybe_alert_fallbacks(10, 10)
    send.assert_not_called()
