import json

import archive_store


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_appends_only_company(tmp_path, monkeypatch):
    f = tmp_path / "archive.json"
    monkeypatch.setattr(archive_store, "ARCHIVE_FILE", str(f))
    archive_store.append_articles([
        {"is_company": True, "title": "조합기사", "link": "http://a/1",
         "published_at": "2026-07-03T10:00:00+09:00", "keyword": "기계설비건설공제조합"},
        {"is_company": False, "title": "산업기사", "link": "http://a/2"},
    ])
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert len(saved) == 1
    assert saved[0] == {"title": "조합기사", "link": "http://a/1",
                        "date": "2026-07-03T10:00:00+09:00", "keyword": "기계설비건설공제조합"}


def test_dedup_existing_links(tmp_path, monkeypatch):
    f = tmp_path / "archive.json"
    _write(f, [{"title": "old", "link": "http://a/1", "date": "x", "keyword": "k"}])
    monkeypatch.setattr(archive_store, "ARCHIVE_FILE", str(f))
    archive_store.append_articles([{"is_company": True, "title": "dup", "link": "http://a/1"}])
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert len(saved) == 1   # 이미 있는 link → 추가 안 함


def test_lean_uses_title_clean_and_collected_fallback(tmp_path, monkeypatch):
    f = tmp_path / "archive.json"
    monkeypatch.setattr(archive_store, "ARCHIVE_FILE", str(f))
    archive_store.append_articles([
        {"is_company": True, "title": "원제목 - 매체", "title_clean": "깨끗한제목",
         "link": "http://a/3", "collected_at": "2026-07-04T09:00:00+09:00"},
    ])
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert saved[0]["title"] == "깨끗한제목"                       # title_clean 우선
    assert saved[0]["date"] == "2026-07-04T09:00:00+09:00"        # published_at 없으면 collected_at


def test_corrupt_archive_not_overwritten(tmp_path, monkeypatch):
    f = tmp_path / "archive.json"
    f.write_text("{ broken json", encoding="utf-8")
    monkeypatch.setattr(archive_store, "ARCHIVE_FILE", str(f))
    archive_store.append_articles([{"is_company": True, "title": "x", "link": "http://a/9"}])
    assert f.read_text(encoding="utf-8") == "{ broken json"       # 파손 파일 덮어쓰지 않음
