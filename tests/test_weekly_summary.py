import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


def _article(title, importance, cluster_id, category="시장·경기", days_ago=2):
    collected = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "title": title, "title_clean": title,
        "link": f"l-{title}",
        "summary": f"요약-{title}",
        "category": category,
        "cluster_id": cluster_id,
        "importance": importance,
        "collected_at": collected,
        "sentiment": "negative",
    }


def test_select_top_clusters_deduplicates_by_cluster():
    from weekly_summary import select_top_clusters
    arts = [
        _article("A", 9, "c1"),
        _article("A2", 8, "c1"),  # 같은 cluster — 최상위만 채택
        _article("B", 7, "c2"),
    ]
    now = datetime.now()
    result = select_top_clusters(arts, now=now)
    cluster_ids = [a["cluster_id"] for a in result]
    assert cluster_ids.count("c1") == 1


def test_select_top_clusters_respects_7_day_window():
    from weekly_summary import select_top_clusters
    arts = [
        _article("recent", 8, "c1", days_ago=2),
        _article("old", 10, "c2", days_ago=30),
    ]
    now = datetime.now()
    result = select_top_clusters(arts, now=now)
    links = [a["link"] for a in result]
    assert "l-recent" in links
    assert "l-old" not in links


def test_select_top_clusters_fallback_threshold_when_below_5():
    from weekly_summary import select_top_clusters
    # 6 이상 기사가 2개만 있으면 4 이상까지 확장
    arts = [
        _article("high1", 9, "c1"),
        _article("high2", 7, "c2"),
        _article("mid1", 5, "c3"),
        _article("mid2", 4, "c4"),
        _article("mid3", 4, "c5"),
        _article("low", 2, "c6"),
    ]
    now = datetime.now()
    result = select_top_clusters(arts, now=now)
    assert len(result) == 5


def test_generate_weekly_summary_writes_json(tmp_path):
    from weekly_summary import generate_weekly_summary

    arts = [_article("t", 8, f"c{i}") for i in range(5)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(content=[MagicMock(text=json.dumps({
        "period": "2026-04-14 ~ 2026-04-20",
        "items": [
            {"category": "시장·경기", "headline": "태영건설", "brief": "1주년..."},
            {"category": "안전·사고", "headline": "중대재해", "brief": "통과..."},
            {"category": "시장·경기", "headline": "PF", "brief": "확대..."},
            {"category": "정책·규제", "headline": "법개정", "brief": "개정..."},
            {"category": "종합건설사", "headline": "수주", "brief": "확대..."},
        ],
    }))])

    out = tmp_path / "weekly.json"
    with patch("weekly_summary._get_client", return_value=mock_client), \
         patch("weekly_summary.load_articles", return_value=arts):
        generate_weekly_summary(output_path=str(out), now=datetime.now())

    data = json.loads(out.read_text())
    assert len(data["items"]) == 5
    assert data["items"][0]["headline"] == "태영건설"


def test_generate_weekly_summary_handles_api_failure(tmp_path):
    from weekly_summary import generate_weekly_summary

    arts = [_article("t", 8, f"c{i}") for i in range(5)]
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API down")

    out = tmp_path / "weekly.json"
    with patch("weekly_summary._get_client", return_value=mock_client), \
         patch("weekly_summary.load_articles", return_value=arts):
        generate_weekly_summary(output_path=str(out), now=datetime.now())

    # 실패 시 파일 만들지 않음 (기존 주간 카드 유지)
    assert not out.exists()
