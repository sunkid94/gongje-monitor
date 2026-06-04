import push_dedup


def test_story_key_strips_publisher_suffix():
    key = push_dedup.story_key("전문건설공제조합, 피치 국제신용등급 'A+' 유지 - 이데일리")
    assert "이데일리" not in key
    assert "전문건설공제조합" in key
    assert "피치" in key
    assert "유지" in key


def test_story_key_keeps_rating_token_and_drops_punctuation():
    key = push_dedup.story_key("K-FINCO, 피치 신용등급 'A+' 유지 - 네이트")
    assert "a+" in key          # 'A+' 는 소문자화되어 토큰으로 유지
    assert "," not in "".join(key)


def test_story_key_drops_single_char_tokens():
    key = push_dedup.story_key("A B 전문건설공제조합 - 매체")
    assert "a" not in key       # 길이 1 토큰 제거
    assert "b" not in key
    assert "전문건설공제조합" in key


def test_story_key_empty_title_returns_empty_set():
    assert push_dedup.story_key("") == set()
    assert push_dedup.story_key(None) == set()


def test_similarity_identical_sets_is_one():
    s = {"a", "b", "c"}
    assert push_dedup.similarity(s, s) == 1.0


def test_similarity_disjoint_sets_is_zero():
    assert push_dedup.similarity({"a"}, {"b"}) == 0.0


def test_similarity_jaccard_value():
    # 교집합 4, 합집합 6 → 0.666...
    a = {"전문건설공제조합", "피치", "국제신용등급", "a+", "유지"}
    b = {"전문건설공제조합", "피치", "신용등급", "a+", "유지"}
    assert push_dedup.similarity(a, b) == 4 / 6


def test_similarity_empty_sets_is_zero():
    assert push_dedup.similarity(set(), set()) == 0.0
    assert push_dedup.similarity({"a"}, set()) == 0.0


import json as _json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

KST = timezone(timedelta(hours=9))


def _now():
    return datetime(2026, 6, 4, 17, 0, 0, tzinfo=KST)


def test_load_pushed_missing_file_returns_empty(tmp_path):
    with patch("push_dedup.PUSHED_FILE", str(tmp_path / "pushed.json")):
        assert push_dedup.load_pushed(_now()) == []


def test_load_pushed_corrupt_file_returns_empty(tmp_path):
    f = tmp_path / "pushed.json"
    f.write_text("{ not valid json", encoding="utf-8")
    with patch("push_dedup.PUSHED_FILE", str(f)):
        assert push_dedup.load_pushed(_now()) == []


def test_save_then_load_roundtrip_tokens_as_set(tmp_path):
    f = tmp_path / "pushed.json"
    entries = [{"tokens": {"피치", "유지", "a+"}, "pushed_at": _now().isoformat(), "title": "t"}]
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.save_pushed(entries, _now())
        loaded = push_dedup.load_pushed(_now())
    assert len(loaded) == 1
    assert loaded[0]["tokens"] == {"피치", "유지", "a+"}   # set 으로 복원
    assert loaded[0]["title"] == "t"


def test_load_pushed_drops_entries_older_than_window(tmp_path):
    f = tmp_path / "pushed.json"
    fresh = (_now() - timedelta(hours=1)).isoformat()
    stale = (_now() - timedelta(hours=25)).isoformat()
    raw = [
        {"tokens": ["fresh"], "pushed_at": fresh, "title": "fresh"},
        {"tokens": ["stale"], "pushed_at": stale, "title": "stale"},
    ]
    f.write_text(_json.dumps(raw), encoding="utf-8")
    with patch("push_dedup.PUSHED_FILE", str(f)):
        loaded = push_dedup.load_pushed(_now())
    titles = {e["title"] for e in loaded}
    assert titles == {"fresh"}


def test_save_pushed_prunes_stale_and_writes_lists(tmp_path):
    f = tmp_path / "pushed.json"
    fresh = {"tokens": {"fresh"}, "pushed_at": (_now() - timedelta(hours=1)).isoformat(), "title": "fresh"}
    stale = {"tokens": {"stale"}, "pushed_at": (_now() - timedelta(hours=30)).isoformat(), "title": "stale"}
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.save_pushed([fresh, stale], _now())
    on_disk = _json.loads(f.read_text(encoding="utf-8"))
    assert len(on_disk) == 1
    assert on_disk[0]["title"] == "fresh"
    assert isinstance(on_disk[0]["tokens"], list)   # 직렬화는 list


def _article(title, is_company=True):
    return {"title": title, "is_company": is_company, "link": title}


# 2026-06-04 실제 "전문건설공제조합 … 피치 … A+ 유지" 변형 7건 (매체만 다름)
FITCH_GONGJE = [
    "전문건설공제조합, 피치 국제신용등급 'A+' 유지 - 뉴스1",
    "전문건설공제조합, 피치 신용등급 A+ 유지 - 기계설비신문",
    "전문건설공제조합, 피치 신용등급 A+ 유지 - 연합뉴스 한민족센터",
    "전문건설공제조합, 피치 국제신용등급 'A+' 유지 - 네이트",
    "전문건설공제조합, 피치 신용등급 A+ 유지 - 연합뉴스",
    "전문건설공제조합, 피치 신용등급 A+ 유지 - 네이트",
    "전문건설공제조합, 피치 국제신용등급 'A+' 유지 - 이데일리",
]


def test_filter_collapses_same_brand_variants_to_one(tmp_path):
    arts = [_article(t) for t in FITCH_GONGJE]
    with patch("push_dedup.PUSHED_FILE", str(tmp_path / "pushed.json")):
        to_push, suppressed = push_dedup.filter_unpushed(arts, _now())
    assert len(to_push) == 1
    assert len(suppressed) == 6


def test_filter_distinct_stories_both_pushed(tmp_path):
    arts = [
        _article("기계설비건설공제조합, 창립 30주년 기념식 개최 - 매체"),
        _article("전문건설공제조합, 피치 신용등급 A+ 유지 - 매체"),
    ]
    with patch("push_dedup.PUSHED_FILE", str(tmp_path / "pushed.json")):
        to_push, suppressed = push_dedup.filter_unpushed(arts, _now())
    assert len(to_push) == 2
    assert suppressed == []


def test_filter_suppresses_story_already_pushed_in_history(tmp_path):
    f = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(f)):
        # 1차: 발송 기록 남김
        push_dedup.filter_unpushed([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - 네이트")], _now())
        # 2차: 같은 스토리 다른 매체 → 억제
        later = _now() + timedelta(hours=3)
        to_push, suppressed = push_dedup.filter_unpushed(
            [_article("전문건설공제조합, 피치 국제신용등급 'A+' 유지 - 이데일리")], later
        )
    assert to_push == []
    assert len(suppressed) == 1


def test_filter_repushes_after_window_expires(tmp_path):
    f = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.filter_unpushed([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - 네이트")], _now())
        later = _now() + timedelta(hours=25)   # 창 만료
        to_push, suppressed = push_dedup.filter_unpushed(
            [_article("전문건설공제조합, 피치 신용등급 A+ 유지 - 이데일리")], later
        )
    assert len(to_push) == 1
    assert suppressed == []


def test_filter_empty_key_article_is_pushed_not_recorded(tmp_path):
    f = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(f)):
        to_push, suppressed = push_dedup.filter_unpushed([_article("")], _now())
        assert len(to_push) == 1     # 키 없으면 안전쪽: 발송
        on_disk = _json.loads(f.read_text(encoding="utf-8"))
    assert on_disk == []             # 키 없는 건 이력에 안 남김
