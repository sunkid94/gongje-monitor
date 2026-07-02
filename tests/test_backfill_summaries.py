import backfill_summaries


def test_backfill_reenriches_fallback_articles():
    desc = "원문 내용 " * 30
    articles = [{
        "title": "조합 수주 - 매체", "title_clean": "조합 수주",
        "description": desc, "summary": desc[:200], "sentiment": "neutral",
        "is_company": False, "link": "l1",
    }]

    def fake_enrich(title, description, orgs=None):
        return {"summary": "진짜 AI 요약", "sentiment": "positive"}

    n = backfill_summaries.backfill_articles(articles, enrich_fn=fake_enrich)
    assert n == 1
    assert articles[0]["summary"] == "진짜 AI 요약"
    assert articles[0]["sentiment"] == "positive"


def test_backfill_skips_non_fallback_articles():
    articles = [{
        "title": "t - m", "title_clean": "t",
        "description": "원문 매우 긴 내용 " * 20, "summary": "이미 좋은 AI 요약",
        "sentiment": "positive", "is_company": False, "link": "l2",
    }]
    called = []

    def fake_enrich(title, description, orgs=None):
        called.append(1)
        return {"summary": "x", "sentiment": "neutral"}

    n = backfill_summaries.backfill_articles(articles, enrich_fn=fake_enrich)
    assert n == 0
    assert called == []
    assert articles[0]["summary"] == "이미 좋은 AI 요약"


def test_backfill_passes_orgs_for_company_and_attaches_event_label():
    desc = "회사 내용 " * 30
    articles = [{
        "title": "전문건설공제조합 A+ - 매체", "title_clean": "전문건설공제조합 A+",
        "description": desc, "summary": desc[:200], "sentiment": "neutral",
        "is_company": True, "link": "l3",
    }]
    captured = {}

    def fake_enrich(title, description, orgs=None):
        captured["orgs"] = orgs
        return {"summary": "요약", "sentiment": "neutral",
                "event_label": "전문건설공제조합 피치 A+ 유지"}

    backfill_summaries.backfill_articles(articles, enrich_fn=fake_enrich)
    assert captured["orgs"] is not None
    assert articles[0]["event_label"] == "전문건설공제조합 피치 A+ 유지"


def test_backfill_passes_none_orgs_for_non_company():
    desc = "내용 " * 60
    articles = [{
        "title": "현대건설 수주 - 매체", "title_clean": "현대건설 수주",
        "description": desc, "summary": desc[:200], "sentiment": "neutral",
        "is_company": False, "link": "l4",
    }]
    captured = {}

    def fake_enrich(title, description, orgs=None):
        captured["orgs"] = orgs
        return {"summary": "s", "sentiment": "neutral"}

    backfill_summaries.backfill_articles(articles, enrich_fn=fake_enrich)
    assert captured["orgs"] is None
