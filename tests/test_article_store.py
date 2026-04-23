from unittest.mock import patch


SAMPLE_ARTICLES = [
    {
        "keyword": "기계설비건설공제조합",
        "title": "기계설비건설공제조합 신규 발표",
        "link": "http://news.google.com/1",
        "description": "신규 사업 발표",
    },
    {
        "keyword": "건설공제조합",
        "title": "건설공제조합 소식",
        "link": "http://news.google.com/2",
        "description": "건설 소식",
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
    many = [{"keyword": "k", "title": f"t{i}", "link": f"http://l/{i}", "description": ""} for i in range(600)]
    with patch("article_store.ARTICLES_FILE", articles_file), \
         patch("article_store.MAX_ARTICLES", 10):
        import article_store
        article_store.save_articles(many)
        result = article_store.load_articles()
    assert len(result) == 10


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
    existing = [{"keyword": "k", "title": "old", "link": "http://old/1", "description": "", "collected_at": "2026-01-01T00:00:00"}]
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        article_store.save_articles(existing)
        article_store.add_articles([SAMPLE_ARTICLES[0]])
        result = article_store.load_articles()
    assert result[0]["link"] == "http://news.google.com/1"
    assert result[1]["link"] == "http://old/1"
