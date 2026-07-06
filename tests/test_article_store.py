from datetime import datetime, timedelta
from unittest.mock import patch


SAMPLE_ARTICLES = [
    {
        "keyword": "기계설비건설공제조합",
        "title": "기계설비건설공제조합 신규 발표 - 대한전문건설신문",
        "link": "http://news.google.com/1",
        "description": '<a href="http://...">기계설비건설공제조합 신규 발표</a>&nbsp;<font>대한전문건설신문</font>',
    },
    {
        "keyword": "건설공제조합",
        "title": "건설공제조합 신규 소식 발표 - 건설일보",
        "link": "http://news.google.com/2",
        "description": '<a href="http://...">건설공제조합 신규 소식 발표</a>&nbsp;<font>건설일보</font>',
    },
]


def test_load_articles_returns_empty_list_when_file_missing(tmp_path):
    articles_file = str(tmp_path / "articles.json")
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        result = article_store.load_articles()
    assert result == []


def test_save_and_load_articles_roundtrip(tmp_path):
    articles_file = str(tmp_path / "articles.json")
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        article_store.save_articles(SAMPLE_ARTICLES)
        result = article_store.load_articles()
    assert len(result) == 2
    assert result[0]["link"] == "http://news.google.com/1"


def test_save_articles_truncates_to_max(tmp_path):
    articles_file = str(tmp_path / "articles.json")
    # collected_at 없는 기사들 (파싱 실패 → 유지) + MAX 10
    many = [{"keyword": "k", "title": f"t{i}", "link": f"http://l/{i}", "description": ""} for i in range(600)]
    with patch("article_store.ARTICLES_FILE", articles_file), \
         patch("article_store.MAX_ARTICLES", 10):
        import article_store
        article_store.save_articles(many)
        result = article_store.load_articles()
    assert len(result) == 10


def test_save_articles_drops_non_company_older_than_retention(tmp_path):
    articles_file = str(tmp_path / "articles.json")
    now = datetime.now()
    recent = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S")
    old = (now - timedelta(days=120)).strftime("%Y-%m-%dT%H:%M:%S")
    items = [
        {"keyword": "k", "is_company": False, "link": "r1", "collected_at": recent},
        {"keyword": "k", "is_company": False, "link": "r2", "collected_at": recent},
        {"keyword": "k", "is_company": False, "link": "old1", "collected_at": old},
        {"keyword": "k", "is_company": False, "link": "old2", "collected_at": old},
    ]
    with patch("article_store.ARTICLES_FILE", articles_file), \
         patch("article_store.RETENTION_DAYS", 60):
        import article_store
        article_store.save_articles(items)
        result = article_store.load_articles()
    links = {a["link"] for a in result}
    assert links == {"r1", "r2"}        # 60일 이내만 보존, 옛날 건 삭제


def test_save_articles_prunes_old_is_company_after_retention(tmp_path):
    # 조합 기사도 30일 보존으로 변경 — 400일 기사는 대시보드에서 제거(전 기간은 archive.json)
    articles_file = str(tmp_path / "articles.json")
    now = datetime.now()
    very_old = (now - timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%S")
    items = [
        {"keyword": "k", "is_company": True, "link": "co_old", "collected_at": very_old},
        {"keyword": "k", "is_company": False, "link": "old", "collected_at": very_old},
    ]
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        article_store.save_articles(items)
        result = article_store.load_articles()
    links = {a["link"] for a in result}
    assert links == set()               # 조합·일반 모두 보존기간 초과 → 제거


def test_save_articles_preserves_is_company_when_truncating(tmp_path):
    articles_file = str(tmp_path / "articles.json")
    items = (
        [{"keyword": "kw", "is_company": True, "link": f"co{i}"} for i in range(8)]
        + [{"keyword": "kw", "is_company": False, "link": f"o{i}"} for i in range(600)]
    )
    with patch("article_store.ARTICLES_FILE", articles_file), \
         patch("article_store.MAX_ARTICLES", 50):
        import article_store
        article_store.save_articles(items)
        result = article_store.load_articles()
    company_kept = [a for a in result if a.get("is_company")]
    assert len(company_kept) == 8       # 조합 기사 모두 보존
    assert len(result) == 50            # 전체 limit 준수
    assert sum(1 for a in result if not a.get("is_company")) == 42


def test_save_articles_caps_corp_category(tmp_path):
    articles_file = str(tmp_path / "articles.json")
    recent = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    items = [
        {"keyword": "k", "category": "종합건설사", "is_company": False,
         "link": f"corp{i}", "collected_at": recent}
        for i in range(15)
    ]
    with patch("article_store.ARTICLES_FILE", articles_file), \
         patch("article_store.MAX_CORP_ARTICLES", 10):
        import article_store
        article_store.save_articles(items)
        result = article_store.load_articles()
    assert len(result) == 10
    # 입력 최신 우선 가정 → 처음 10건이 살아남음
    assert {a["link"] for a in result} == {f"corp{i}" for i in range(10)}


def test_save_articles_corp_cap_does_not_affect_other_categories(tmp_path):
    articles_file = str(tmp_path / "articles.json")
    recent = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    items = (
        [{"keyword": "k", "category": "종합건설사", "is_company": False,
          "link": f"corp{i}", "collected_at": recent} for i in range(15)]
        + [{"keyword": "k", "category": "정책·규제", "is_company": False,
            "link": f"pol{i}", "collected_at": recent} for i in range(15)]
    )
    with patch("article_store.ARTICLES_FILE", articles_file), \
         patch("article_store.MAX_CORP_ARTICLES", 10):
        import article_store
        article_store.save_articles(items)
        result = article_store.load_articles()
    corp_kept = [a for a in result if a["category"] == "종합건설사"]
    pol_kept = [a for a in result if a["category"] == "정책·규제"]
    assert len(corp_kept) == 10   # 종건사 캡 적용
    assert len(pol_kept) == 15    # 다른 카테고리는 영향 없음


def test_add_articles_prepends_with_collected_at(tmp_path):
    articles_file = str(tmp_path / "articles.json")
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        article_store.add_articles(SAMPLE_ARTICLES)
        result = article_store.load_articles()
    assert len(result) == 2
    assert "collected_at" in result[0]
    assert result[0]["link"] == "http://news.google.com/1"


def test_add_articles_prepends_to_existing(tmp_path):
    articles_file = str(tmp_path / "articles.json")
    recent = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    existing = [{"keyword": "k", "title": "old", "link": "http://old/1", "description": "", "collected_at": recent}]
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        article_store.save_articles(existing)
        article_store.add_articles([SAMPLE_ARTICLES[0]])
        result = article_store.load_articles()
    assert result[0]["link"] == "http://news.google.com/1"
    assert result[1]["link"] == "http://old/1"


def test_add_articles_writes_timezone_aware_collected_at(tmp_path):
    """프론트엔드 relativeTime() 이 collected_at 을 KST 가 아닌 UTC 로 오인식해
    "1분 전"이 무한 반복되던 버그 회귀 방지 — 저장 시 타임존 오프셋이 반드시 포함돼야 함.
    """
    import re
    articles_file = str(tmp_path / "articles.json")
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        article_store.add_articles([SAMPLE_ARTICLES[0]])
        result = article_store.load_articles()
    collected_at = result[0]["collected_at"]
    # index.html:793 의 정규식과 동일한 패턴 — Z 또는 ±HH:MM 으로 끝나야 함
    assert re.search(r"[Zz]|[+-]\d{2}:?\d{2}$", collected_at), \
        f"collected_at 에 타임존 오프셋 없음: {collected_at!r}"


def test_save_articles_migrates_naive_collected_at_to_timezone_aware(tmp_path):
    """기존 articles.json 의 타임존 없는 데이터는 저장 시 자동으로 로컬 타임존이 부여돼야 함."""
    import re
    articles_file = str(tmp_path / "articles.json")
    naive = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    items = [{"keyword": "k", "is_company": True, "link": "x", "collected_at": naive}]
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        article_store.save_articles(items)
        result = article_store.load_articles()
    assert re.search(r"[+-]\d{2}:?\d{2}$", result[0]["collected_at"])


def test_parse_collected_at_handles_both_formats():
    from article_store import parse_collected_at
    naive = parse_collected_at("2026-05-31T22:04:55")
    tz_aware = parse_collected_at("2026-05-31T22:04:55+09:00")
    assert naive.tzinfo is not None         # naive → 로컬 tz 부여
    assert tz_aware.utcoffset().total_seconds() == 9 * 3600


def test_filter_duplicates_blocks_same_publisher_cluster(tmp_path):
    """Google News 가 같은 기사에 다른 리다이렉트 URL 을 발급해 재수집되는 케이스 차단.
    같은 (publisher, cluster_id) 면 새 기사로 취급하지 않음.
    """
    articles_file = str(tmp_path / "articles.json")
    existing = [{
        "keyword": "k", "publisher": "v.daum.net", "cluster_id": "f71f",
        "title": "건설공제조합 AX 포럼", "link": "old-url", "collected_at": "2026-06-01T14:22:46+09:00",
    }]
    incoming = [{
        "keyword": "k", "publisher": "v.daum.net", "cluster_id": "f71f",
        "title": "건설공제조합 AX 포럼", "link": "new-url-different-redirect",
    }]
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        article_store.save_articles(existing)
        result = article_store.filter_duplicates(incoming)
    assert result == []  # 같은 publisher+cluster_id → 전부 차단


def test_filter_duplicates_allows_different_publisher_same_cluster(tmp_path):
    """다른 매체가 같은 사건을 다루는 건 정상이므로 허용 (커버리지 다양성 유지)."""
    articles_file = str(tmp_path / "articles.json")
    existing = [{
        "keyword": "k", "publisher": "파이낸셜뉴스", "cluster_id": "f71f",
        "link": "url1", "collected_at": "2026-06-01T14:22:46+09:00",
    }]
    incoming = [{
        "keyword": "k", "publisher": "뉴시스", "cluster_id": "f71f",
        "link": "url2",
    }]
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        article_store.save_articles(existing)
        result = article_store.filter_duplicates(incoming)
    assert len(result) == 1
    assert result[0]["publisher"] == "뉴시스"


def test_filter_duplicates_dedupes_within_batch(tmp_path):
    """단일 배치 안에 같은 (publisher, cluster_id) 가 여러 번 들어와도 한 번만 남아야 함."""
    articles_file = str(tmp_path / "articles.json")
    incoming = [
        {"publisher": "v.daum.net", "cluster_id": "f71f", "link": "u1"},
        {"publisher": "v.daum.net", "cluster_id": "f71f", "link": "u2"},
        {"publisher": "네이트", "cluster_id": "f71f", "link": "u3"},
    ]
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        result = article_store.filter_duplicates(incoming)
    # 첫 v.daum.net 하나 + 네이트 하나 → 2건
    assert len(result) == 2
    assert {r["publisher"] for r in result} == {"v.daum.net", "네이트"}


def test_filter_duplicates_passes_through_articles_without_keys(tmp_path):
    """publisher 또는 cluster_id 없는 기사는 dedup 키 없음 → 모두 통과."""
    articles_file = str(tmp_path / "articles.json")
    incoming = [
        {"publisher": None, "cluster_id": "f71f", "link": "u1"},
        {"publisher": "v.daum.net", "cluster_id": None, "link": "u2"},
        {"publisher": "", "cluster_id": "f71f", "link": "u3"},
    ]
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        result = article_store.filter_duplicates(incoming)
    assert len(result) == 3


def test_filter_duplicates_blocks_same_title_different_publisher(tmp_path):
    """같은 기사가 구글판('- 파이낸셜뉴스')과 직접판('- fnnews.com')으로 발행처 표기만
    달라도, 정규화 제목이 같으면 중복으로 차단한다."""
    articles_file = str(tmp_path / "articles.json")
    existing = [{
        "keyword": "k", "publisher": "fnnews.com", "cluster_id": "a22b",
        "title": "K-FINCO, 보증수수료 할인·2663억원 특별융자 지원 - fnnews.com",
        "link": "direct", "collected_at": "2026-06-01T13:44:00+09:00",
    }]
    incoming = [{
        "keyword": "k", "publisher": "파이낸셜뉴스", "cluster_id": "a22b",
        "title": "K-FINCO, 보증수수료 할인·2663억원 특별융자 지원 - 파이낸셜뉴스",
        "link": "google",
    }]
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        article_store.save_articles(existing)
        result = article_store.filter_duplicates(incoming)
    assert result == []  # 정규화 제목 동일 → 발행처 달라도 차단


def test_save_articles_dedupes_same_title_different_publisher(tmp_path):
    """저장본에 같은 기사의 구글판/직접판이 섞여 있으면(발행처만 다름) 정규화 제목 기준으로
    가장 오래된 하나만 남긴다."""
    articles_file = str(tmp_path / "articles.json")
    items = [
        {"is_company": True, "publisher": "파이낸셜뉴스", "cluster_id": "a22b",
         "title": "K-FINCO 특별융자 지원 - 파이낸셜뉴스", "link": "google",
         "collected_at": "2026-06-01T15:19:00+09:00"},
        {"is_company": True, "publisher": "fnnews.com", "cluster_id": "a22b",
         "title": "K-FINCO 특별융자 지원 - fnnews.com", "link": "direct",
         "collected_at": "2026-06-01T13:44:00+09:00"},
    ]
    with patch("article_store.ARTICLES_FILE", articles_file), \
         patch("article_store.RETENTION_DAYS_COMPANY", 100000):
        import article_store
        article_store.save_articles(items)
        result = article_store.load_articles()
    links = {a["link"] for a in result}
    assert links == {"direct"}  # 가장 오래된(직접판)만 남음


def test_is_empty_stub_blocks_short_descriptions():
    from article_store import is_empty_stub
    # 실제 문제 케이스 — Google News 가 발급한 "장관 - 국토교통부" entry
    title = "장관 - 국토교통부"
    desc = '<a href="https://news.google.com/...">장관</a>&nbsp;&nbsp;<font color="#6f6f6f">국토교통부</font>'
    assert is_empty_stub(title, desc) is True


def test_is_empty_stub_keeps_normal_articles():
    from article_store import is_empty_stub
    title = "오산시, 우기·폭염 대비 공동주택 건설현장 합동 안전점검 실시 - 한국시사경제"
    desc = '<a href="https://news.google.com/...">오산시, 우기·폭염 대비 공동주택 건설현장 합동 안전점검 실시</a>&nbsp;&nbsp;<font>한국시사경제</font>'
    assert is_empty_stub(title, desc) is False


def test_is_empty_stub_handles_empty_title():
    from article_store import is_empty_stub
    assert is_empty_stub("", "<a>some content</a>") is True
    assert is_empty_stub("   ", "<a>some content</a>") is True


def test_save_articles_drops_empty_stub_entries(tmp_path):
    """기존 articles.json 에 누적된 빈 껍데기 entry 도 save_articles 호출 시 자동 청소."""
    articles_file = str(tmp_path / "articles.json")
    items = [
        {"is_company": True, "title": "장관 - 국토교통부", "link": "stub",
         "description": '<a>장관</a>&nbsp;<font>국토교통부</font>'},
        {"is_company": True, "title": "정상 제목 - 한국시사경제", "link": "good",
         "description": '<a>오산시, 우기·폭염 대비 공동주택 건설현장 합동 안전점검 실시</a>&nbsp;<font>한국시사경제</font>'},
    ]
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        article_store.save_articles(items)
        result = article_store.load_articles()
    links = {a["link"] for a in result}
    assert links == {"good"}


def test_save_articles_dedupes_existing_keeping_oldest(tmp_path):
    """save_articles 가 기존 articles.json 의 (publisher, cluster_id) 중복을 정리하되
    가장 오래된 collected_at 을 유지해야 함 — 사용자가 인지하는 "최초 기사 시점" 보존.
    """
    articles_file = str(tmp_path / "articles.json")
    items = [
        # 최신 우선 정렬 가정 — 가장 앞이 가장 최근
        {"publisher": "v.daum.net", "cluster_id": "f71f", "is_company": True,
         "link": "newest", "collected_at": "2026-06-02T07:57:57+09:00"},
        {"publisher": "v.daum.net", "cluster_id": "f71f", "is_company": True,
         "link": "middle", "collected_at": "2026-06-02T06:18:01+09:00"},
        {"publisher": "v.daum.net", "cluster_id": "f71f", "is_company": True,
         "link": "oldest", "collected_at": "2026-06-01T14:22:46+09:00"},
        {"publisher": "뉴시스", "cluster_id": "f71f", "is_company": True,
         "link": "different-publisher", "collected_at": "2026-06-01T15:00:00+09:00"},
    ]
    with patch("article_store.ARTICLES_FILE", articles_file), \
         patch("article_store.RETENTION_DAYS_COMPANY", 100000):   # 보존기간 무관하게 dedup 만 검증
        import article_store
        article_store.save_articles(items)
        result = article_store.load_articles()
    links = {a["link"] for a in result}
    assert links == {"oldest", "different-publisher"}  # 가장 오래된 + 다른 매체


def test_company_article_pruned_after_30_days(tmp_path, monkeypatch):
    import article_store
    from datetime import datetime, timedelta
    monkeypatch.setattr(article_store, "ARTICLES_FILE", str(tmp_path / "articles.json"))
    now = datetime.now().astimezone()
    old = article_store.format_collected_at(now - timedelta(days=40))
    recent = article_store.format_collected_at(now - timedelta(days=5))
    article_store.save_articles([
        {"is_company": True, "title": "오래된 조합기사입니다", "link": "c1",
         "collected_at": old, "publisher": "p", "cluster_id": "1"},
        {"is_company": True, "title": "최근 조합기사입니다", "link": "c2",
         "collected_at": recent, "publisher": "p", "cluster_id": "2"},
    ])
    links = {a["link"] for a in article_store.load_articles()}
    assert "c2" in links       # 30일 이내 유지
    assert "c1" not in links    # 30일 초과 제거
