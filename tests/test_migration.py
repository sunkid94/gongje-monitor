import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def test_migrate_fills_defaults(tmp_path, monkeypatch):
    src = tmp_path / "articles.json"
    old_data = [
        {
            "keyword": "기계설비건설공제조합",
            "title": "조합 신규 사업 - 조선비즈",
            "link": "l1",
            "description": "d",
            "summary": "요약",
            "collected_at": "2026-04-01T12:00:00",
        },
        {
            "keyword": "건설 PF",
            "title": "PF 위기 심화",
            "link": "l2",
            "description": "d",
            "summary": None,
            "collected_at": "2026-04-02T12:00:00",
        },
    ]
    src.write_text(json.dumps(old_data, ensure_ascii=False))

    from migrate_articles import migrate
    migrate(str(src))

    result = json.loads(src.read_text())

    assert result[0]["category"] == "조합·협회"
    assert result[0]["is_company"] is True
    assert result[0]["title_clean"] == "조합 신규 사업"
    assert result[0]["publisher"] == "조선비즈"
    assert result[0]["sentiment"] == "neutral"
    assert result[0]["importance"] == 0
    assert "cluster_id" in result[0]

    assert result[1]["category"] == "시장·경기"
    assert result[1]["is_company"] is False
    assert result[1]["publisher"] == ""


def test_migrate_is_idempotent(tmp_path):
    src = tmp_path / "articles.json"
    old_data = [{
        "keyword": "기계설비건설공제조합",
        "title": "제목",
        "link": "l1",
        "description": "d",
        "summary": "s",
        "collected_at": "2026-04-01T12:00:00",
    }]
    src.write_text(json.dumps(old_data, ensure_ascii=False))

    from migrate_articles import migrate
    migrate(str(src))
    first = json.loads(src.read_text())
    migrate(str(src))
    second = json.loads(src.read_text())

    assert first == second


def test_migrate_unknown_keyword_maps_to_uncategorized(tmp_path):
    src = tmp_path / "articles.json"
    src.write_text(json.dumps([{
        "keyword": "알수없는키워드",
        "title": "t",
        "link": "l",
        "description": "d",
        "summary": None,
        "collected_at": "2026-04-01T12:00:00",
    }]))

    from migrate_articles import migrate
    migrate(str(src))

    result = json.loads(src.read_text())
    assert result[0]["category"] == "(미분류)"
    assert result[0]["is_company"] is False
