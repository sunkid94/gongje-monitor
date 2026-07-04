from unittest.mock import patch
import crawler


def _article(link):
    return {"keyword": "k", "category": "조합·협회", "is_company": True,
            "title": "제목 - 매체", "link": link, "description": "d"}


def _source(items=None, raises=None):
    """테스트용 소스 스텁 — fetch(seen) 시그니처."""
    def fetch(seen=frozenset()):
        if raises:
            raise raises
        return list(items or [])
    return type("StubSource", (), {"fetch": staticmethod(fetch), "__name__": "stub"})


def test_aggregator_excludes_seen_links():
    with patch.object(crawler, "SOURCES", [_source([_article("http://a/1")])]):
        result = crawler.fetch_new_articles({"http://a/1"})
    assert result == []


def test_aggregator_includes_unseen_links():
    with patch.object(crawler, "SOURCES", [_source([_article("http://a/2")])]):
        result = crawler.fetch_new_articles(set())
    assert len(result) == 1
    assert result[0]["link"] == "http://a/2"


def test_aggregator_dedups_same_link_across_sources():
    with patch.object(crawler, "SOURCES", [_source([_article("http://dup")]), _source([_article("http://dup")])]):
        result = crawler.fetch_new_articles(set())
    assert len(result) == 1


def test_aggregator_continues_when_a_source_raises():
    with patch.object(crawler, "SOURCES", [_source(raises=RuntimeError("x")), _source([_article("http://ok")])]):
        result = crawler.fetch_new_articles(set())
    assert len(result) == 1
    assert result[0]["link"] == "http://ok"


def test_is_blocked_domain_matches_host_and_subdomains():
    with patch.object(crawler, "BLOCKED_DOMAINS", ["job-post.co.kr"]):
        assert crawler.is_blocked_domain("https://www.job-post.co.kr/news/articleView.html?idxno=1")
        assert crawler.is_blocked_domain("https://job-post.co.kr/y")
        assert not crawler.is_blocked_domain("https://www.cnbnews.com/z")
        assert not crawler.is_blocked_domain("")
        # 부분 문자열 오탐 방지: notjob-post.co.kr 는 차단 아님
        assert not crawler.is_blocked_domain("https://notjob-post.co.kr/x")


def test_aggregator_excludes_blocked_domain():
    src = _source([_article("https://www.job-post.co.kr/n/1"), _article("https://www.cnbnews.com/n/2")])
    with patch.object(crawler, "BLOCKED_DOMAINS", ["job-post.co.kr"]), \
         patch.object(crawler, "SOURCES", [src]):
        result = crawler.fetch_new_articles(set())
    assert len(result) == 1
    assert result[0]["link"] == "https://www.cnbnews.com/n/2"


def test_has_blocked_content_checks_title_and_description():
    with patch.object(crawler, "BLOCKED_CONTENT_KEYWORDS", ["포토월", "레드카펫"]):
        assert crawler.has_blocked_content({"title": "포토월 행사", "description": ""})
        assert crawler.has_blocked_content({"title": "x", "description": "현장 레드카펫 모습"})
        assert not crawler.has_blocked_content({"title": "건설공제조합 특별융자", "description": "3000억 지원"})


def test_aggregator_excludes_blocked_content_keyword():
    blocked = {"keyword": "k", "category": "조합·협회", "is_company": True,
               "title": "손예진, 새 스타일 - 스포츠경향", "link": "https://sports.khan.co.kr/1",
               "description": "건설공제조합 본점에서 열린 제46회 황금촬영상 레드카펫 행사"}
    clean = _article("https://www.cnbnews.com/2")
    with patch.object(crawler, "BLOCKED_CONTENT_KEYWORDS", ["황금촬영상", "레드카펫", "포토월", "쇼호스트"]), \
         patch.object(crawler, "SOURCES", [_source([blocked, clean])]):
        result = crawler.fetch_new_articles(set())
    assert len(result) == 1
    assert result[0]["link"] == "https://www.cnbnews.com/2"


def test_same_headline_across_sources_gets_same_cluster_id():
    import enrich
    arts = [
        {"title": "전문건설공제조합 피치 A+ 유지 - 대한전문건설신문", "description": "", "link": "http://a", "keyword": "k", "category": "조합·협회", "is_company": True},
        {"title": "전문건설공제조합 피치 A+ 유지 - 네이버뉴스", "description": "", "link": "http://b", "keyword": "k", "category": "조합·협회", "is_company": True},
        {"title": "전문건설공제조합 피치 A+ 유지 - 기계설비신문", "description": "", "link": "http://c", "keyword": "k", "category": "조합·협회", "is_company": True},
    ]
    clustered = enrich.cluster_articles(arts)
    ids = {c["cluster_id"] for c in clustered}
    assert len(ids) == 1   # 매체만 달라도 같은 사건 → 한 cluster


def test_fetch_new_articles_accepts_sources_override():
    # sources 인자로 특정 소스만 지정하면 SOURCES 기본값 대신 그것만 수집
    s1 = _source([_article("http://only/1")])
    with patch.object(crawler, "SOURCES", [_source([_article("http://default/x")])]):
        result = crawler.fetch_new_articles(set(), sources=[s1])
    assert len(result) == 1
    assert result[0]["link"] == "http://only/1"


def test_fetch_trade_only_uses_rss_source_only():
    # fast-path: 직접 RSS 소스만 사용(구글/네이버 제외)
    with patch.object(crawler, "source_rss", _source([_article("http://rss/1")])):
        result = crawler.fetch_trade_only(set())
    assert len(result) == 1
    assert result[0]["link"] == "http://rss/1"


def test_fetch_trade_only_still_applies_blocked_filters():
    # fast-path 도 차단 도메인 필터 적용
    blocked = _article("http://job-post.co.kr/1")
    with patch.object(crawler, "source_rss", _source([blocked])), \
         patch.object(crawler, "BLOCKED_DOMAINS", ["job-post.co.kr"]):
        result = crawler.fetch_trade_only(set())
    assert result == []


def test_lacks_corp_qualifier_drops_corp_without_qualifier():
    a = {"category": "종합건설사", "title": "삼성중공업 조선 수출 호조", "description": "방산 실적"}
    assert crawler.lacks_corp_qualifier(a) is True


def test_lacks_corp_qualifier_keeps_corp_with_qualifier():
    a = {"category": "종합건설사", "title": "대우건설 성수 재건축 수주", "description": ""}
    assert crawler.lacks_corp_qualifier(a) is False


def test_lacks_corp_qualifier_ignores_non_corp_category():
    # 조합·협회 등 다른 카테고리는 한정어 없어도 필터 대상 아님
    a = {"category": "조합·협회", "title": "기계설비건설공제조합 신규 공시", "description": ""}
    assert crawler.lacks_corp_qualifier(a) is False


def test_lacks_corp_qualifier_matches_qualifier_in_description():
    a = {"category": "종합건설사", "title": "롯데건설 소식", "description": "신규 아파트 착공 예정"}
    assert crawler.lacks_corp_qualifier(a) is False


def test_fetch_new_articles_drops_corp_without_qualifier():
    src = type("S", (), {"fetch": staticmethod(lambda seen=None: [
        {"category": "종합건설사", "title": "삼성중공업 방산 수출", "description": "", "link": "http://x/1"},
        {"category": "종합건설사", "title": "대우건설 현장 안전점검", "description": "", "link": "http://x/2"},
    ]), "__name__": "s"})
    with patch.object(crawler, "SOURCES", [src]):
        result = crawler.fetch_new_articles(set())
    links = {a["link"] for a in result}
    assert links == {"http://x/2"}   # 한정어(현장) 있는 것만 유지
