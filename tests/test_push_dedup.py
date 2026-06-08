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
    entries = [{"tokens": {"피치", "유지", "a+"}, "canon": "전문건설공제조합",
                "pushed_at": _now().isoformat(), "title": "t"}]
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.save_pushed(entries, _now())
        loaded = push_dedup.load_pushed(_now())
    assert len(loaded) == 1
    assert loaded[0]["tokens"] == {"피치", "유지", "a+"}
    assert loaded[0]["canon"] == "전문건설공제조합"
    assert loaded[0]["title"] == "t"


def test_load_pushed_drops_entries_older_than_window(tmp_path):
    f = tmp_path / "pushed.json"
    fresh = (_now() - timedelta(hours=1)).isoformat()
    stale = (_now() - timedelta(hours=200)).isoformat()   # 7일(168h) 초과
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
    stale = {"tokens": {"stale"}, "pushed_at": (_now() - timedelta(hours=200)).isoformat(), "title": "stale"}
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.save_pushed([fresh, stale], _now())
    on_disk = _json.loads(f.read_text(encoding="utf-8"))
    assert len(on_disk) == 1
    assert on_disk[0]["title"] == "fresh"
    assert isinstance(on_disk[0]["tokens"], list)


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
        later = _now() + timedelta(hours=192)   # 7일 창 만료
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


def test_story_lead_extracts_org_before_first_comma():
    assert push_dedup.story_lead("전문건설공제조합, 피치 신용등급 A+ 유지 - 이데일리") == "전문건설공제조합"
    assert push_dedup.story_lead("") == ""
    assert push_dedup.story_lead(None) == ""


def test_story_lead_strips_publisher_and_punctuation():
    # 매체명 접미사 제거 후, 첫 쉼표 앞 정규화
    assert push_dedup.story_lead("기계설비건설공제조합, 창립 30주년 - 매체") == "기계설비건설공제조합"


def test_filter_does_not_suppress_across_different_orgs(tmp_path):
    # 다른 조직의 동일 이벤트는 각각 발송 (사용자 자기 조합 뉴스가 묻히지 않도록)
    f = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.filter_unpushed([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - 네이트")], _now())
        to_push, suppressed = push_dedup.filter_unpushed(
            [_article("기계설비건설공제조합, 피치 신용등급 A+ 유지 - 이데일리")], _now() + timedelta(hours=1)
        )
    assert len(to_push) == 1     # 다른 조직 → 억제 안 함
    assert suppressed == []


def test_filter_merges_brand_alias_same_batch(tmp_path):
    # v2: K-FINCO 와 전문건설공제조합 은 같은 조직(별칭) → 같은 사건이면 1건만
    arts = [
        _article("K-FINCO, 피치 신용등급 A+ 유지 - 네이트"),
        _article("전문건설공제조합, 피치 신용등급 A+ 유지 - 이데일리"),
    ]
    with patch("push_dedup.PUSHED_FILE", str(tmp_path / "pushed.json")):
        to_push, suppressed = push_dedup.filter_unpushed(arts, _now())
    assert len(to_push) == 1
    assert len(suppressed) == 1


def test_filter_still_suppresses_same_org_variant(tmp_path):
    # 같은 조직의 표현 차이(국제신용등급 vs 신용등급)는 여전히 억제 (1차 목표 보존)
    f = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.filter_unpushed([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - 네이트")], _now())
        to_push, suppressed = push_dedup.filter_unpushed(
            [_article("전문건설공제조합, 피치 국제신용등급 'A+' 유지 - 이데일리")], _now() + timedelta(hours=2)
        )
    assert to_push == []
    assert len(suppressed) == 1


def test_story_lead_strips_leading_bracket_section():
    assert push_dedup.story_lead("[마켓인]나신평, 삼성중공업 신용등급 상향 - 이데일리") == "나신평"
    # 대괄호 유무만 다른 같은 조직은 같은 lead
    assert push_dedup.story_lead("[마켓인]나신평, 삼성중공업 신용등급 상향 - 이데일리") == \
           push_dedup.story_lead("나신평, 삼성중공업 신용등급 상향 - 뉴스1")


def test_filter_suppresses_bracketed_and_plain_same_org(tmp_path):
    f = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.filter_unpushed([_article("나신평, 삼성중공업 신용등급 상향 - 뉴스1")], _now())
        to_push, suppressed = push_dedup.filter_unpushed(
            [_article("[마켓인]나신평, 삼성중공업 신용등급 상향 - 이데일리")], _now() + timedelta(hours=1)
        )
    assert to_push == []
    assert len(suppressed) == 1


def test_canonical_org_maps_aliases_to_canonical():
    # 전문건설공제조합 별칭들
    assert push_dedup.canonical_org("전문조합, 보험지급능력 A+ 유지 - 대한경제") == "전문건설공제조합"
    assert push_dedup.canonical_org("K-FINCO, 피치 신용등급 'A+' 유지 - 뉴스핌") == "전문건설공제조합"
    assert push_dedup.canonical_org("전문건설공제조합, 피치 A+ 유지 - 국토일보") == "전문건설공제조합"


def test_canonical_org_maps_our_coop_aliases():
    assert push_dedup.canonical_org("CIG, 창립 30주년 - 매체") == "기계설비건설공제조합"
    assert push_dedup.canonical_org("기계설비건설공제조합, 신규 사업 - 매체") == "기계설비건설공제조합"


def test_canonical_org_unknown_returns_lead():
    # 별칭 목록에 없는 조직 → 선두 lead 원본(정규화) 그대로
    assert push_dedup.canonical_org("나신평, 삼성중공업 신용등급 상향 - 이데일리") == "나신평"


def test_canonical_org_does_not_cross_groups():
    # 우리 조합과 전문건설은 다른 그룹 — 절대 같은 canon 아님
    a = push_dedup.canonical_org("기계설비건설공제조합, 피치 A+ 유지 - 매체")
    b = push_dedup.canonical_org("전문건설공제조합, 피치 A+ 유지 - 매체")
    assert a != b


def test_canonical_org_no_substring_false_positive():
    # "전문조합" 별칭이 "전문조합원협회" 안에 부분일치하면 안 됨 (다른 조직)
    assert push_dedup.canonical_org("전문조합원협회, 정기총회 개최 - 매체") == "전문조합원협회"
    # "cig" 가 "cigna" 안에 부분일치하면 안 됨
    assert push_dedup.canonical_org("CIGNA Korea, 보험 신상품 출시 - 매체") != "기계설비건설공제조합"


def test_canonical_org_matches_org_with_prefix():
    # 선두에 수식어가 붙어도 조직 토큰이 온전히 있으면 매칭
    assert push_dedup.canonical_org("한국 전문건설공제조합, 피치 A+ 유지 - 매체") == "전문건설공제조합"


def test_canonical_org_kfinco_without_separator():
    # "KFINCO"(구분자 없음) → "kfinco" 별칭으로 매칭
    assert push_dedup.canonical_org("KFINCO, 피치 신용등급 A+ 유지 - 매체") == "전문건설공제조합"


def test_overlap_subset_is_one():
    # 짧은 집합이 긴 집합에 완전히 포함되면 1.0
    assert push_dedup.overlap({"피치", "a+", "유지"}, {"피치", "a+", "유지", "자본력", "탄탄"}) == 1.0


def test_overlap_value_is_intersection_over_min():
    a = {"전문건설공제조합", "피치", "신용등급", "a+", "유지"}              # 5
    b = {"전문건설공제조합", "피치", "국제신용등급", "a+", "유지", "자본력"}  # 6, 교집합 4
    assert push_dedup.overlap(a, b) == 4 / 5   # min(5,6)=5


def test_overlap_empty_is_zero():
    assert push_dedup.overlap(set(), {"a"}) == 0.0
    assert push_dedup.overlap({"a"}, set()) == 0.0
    assert push_dedup.overlap(set(), set()) == 0.0


# 2026-06-05 실측 "피치/신용등급" 표현 계열 5변형 (매체·표기·수식어 상이, 같은 사건)
FITCH_V2 = [
    "K-FINCO, 피치 신용등급 'A+' 유지…6.5조 자본력 인정 - 뉴스핌",
    "전문건설공제조합, 피치 신용등급 'A+' 유지 - 국토일보",
    "전문건설공제조합, 피치 국제신용등급 'A+'…자본력 탄탄 - 데일리안",
    "전문건설공제조합, 글로벌 신용평가사 피치 국제신용등급'A+' 유지 - kscnews",
    "K-FINCO, 글로벌 신용평가사 피치 국제신용등급 'A+' 유지 - 대한전문건설신문",
]


def test_filter_v2_reduces_fitch_variants(tmp_path):
    # 표현이 꽤 다른 5변형 — 0.7에서 일부는 묶이고 일부는 각도가 달라 남음(과대약속 안 함).
    # 핵심: 최소한 줄어든다. (정확히 1로 수렴한다고 단언하지 않음)
    arts = [_article(t) for t in FITCH_V2]
    with patch("push_dedup.PUSHED_FILE", str(tmp_path / "pushed.json")):
        to_push, suppressed = push_dedup.filter_unpushed(arts, _now())
    assert len(to_push) < len(arts)
    assert len(suppressed) >= 1


def test_filter_v2_suppresses_cross_brand_reword_of_same_event(tmp_path):
    # 사용자 실측 케이스: 00:07 전문건설판 발송 후, 13:57 K-FINCO 재보도(거의 동일 표현)는 억제.
    f = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.filter_unpushed(
            [_article("전문건설공제조합, 글로벌 신용평가사 피치 국제신용등급 'A+' 유지 - kscnews")], _now())
        to_push, suppressed = push_dedup.filter_unpushed(
            [_article("K-FINCO, 글로벌 신용평가사 피치 국제신용등급 'A+' 유지 - 대한전문건설신문")],
            _now() + timedelta(hours=2))
    assert to_push == []
    assert len(suppressed) == 1


def test_filter_v2_our_coop_not_suppressed_by_sibling(tmp_path):
    f = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.filter_unpushed([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - A")], _now())
        to_push, suppressed = push_dedup.filter_unpushed(
            [_article("기계설비건설공제조합, 피치 신용등급 A+ 유지 - B")], _now() + timedelta(hours=1)
        )
    assert len(to_push) == 1
    assert suppressed == []


def test_filter_v2_same_org_different_event_not_suppressed(tmp_path):
    f = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.filter_unpushed([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - A")], _now())
        to_push, suppressed = push_dedup.filter_unpushed(
            [_article("전문건설공제조합, ESG 경영 평가 최우수 등급 - B")], _now() + timedelta(hours=1)
        )
    assert len(to_push) == 1
    assert suppressed == []


def test_filter_v2_rating_change_not_suppressed_by_maintain(tmp_path):
    # 등급 '상향'은 직전 '유지' 알림에 묻히면 안 됨 (홍보상 놓치면 치명적)
    f = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.filter_unpushed([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - A")], _now())
        to_push, suppressed = push_dedup.filter_unpushed(
            [_article("전문건설공제조합, 피치 신용등급 A+ 상향 - B")], _now() + timedelta(hours=2))
    assert len(to_push) == 1     # 상향은 별개로 발송
    assert suppressed == []


def test_filter_v2_same_direction_still_merges(tmp_path):
    # 둘 다 '유지' → 같은 사건으로 여전히 묶임 (방향 가드가 정상 병합을 깨지 않음)
    f = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.filter_unpushed([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - A")], _now())
        to_push, suppressed = push_dedup.filter_unpushed(
            [_article("전문건설공제조합, 피치 국제신용등급 A+ 유지 - B")], _now() + timedelta(hours=2))
    assert to_push == []
    assert len(suppressed) == 1


def test_label_canon_finds_tracked_org():
    assert push_dedup.label_canon("대한기계설비건설협회 박종학 회장 별세") == "대한기계설비건설협회"
    assert push_dedup.label_canon("K-FINCO 피치 신용등급 A+ 유지") == "전문건설공제조합"
    assert push_dedup.label_canon("전문건설공제조합 피치 A+ 유지") == "전문건설공제조합"


def test_label_canon_fallback_when_no_tracked_org():
    c = push_dedup.label_canon("어떤 벤더 신제품 출시")
    assert c not in ("", None)
    assert "어떤" in c


def _labeled(title, label):
    return {"title": title, "event_label": label, "is_company": True, "link": title}


def test_filter_unpushed_merges_obituary_by_label(tmp_path):
    arts = [
        _labeled("기계설비산업 발전 이끈 박종학 전 기계설비건설협회장 별세 - 이데일리", "대한기계설비건설협회 박종학 회장 별세"),
        _labeled("박종학 대한기계설비건설협회 제6대 회장 별세 - 한국경제", "대한기계설비건설협회 박종학 회장 별세"),
        _labeled("[부고] 박종학씨 外 - 중앙", "대한기계설비건설협회 박종학 회장 별세"),
    ]
    with patch("push_dedup.PUSHED_FILE", str(tmp_path / "pushed.json")):
        to_push, suppressed = push_dedup.filter_unpushed(arts, _now())
    assert len(to_push) == 1
    assert len(suppressed) == 2


def test_filter_unpushed_different_org_labels_not_merged(tmp_path):
    arts = [
        _labeled("기계설비건설공제조합 신용등급 A+ - A", "기계설비건설공제조합 피치 신용등급 A+ 유지"),
        _labeled("전문건설공제조합 신용등급 A+ - B", "전문건설공제조합 피치 신용등급 A+ 유지"),
    ]
    with patch("push_dedup.PUSHED_FILE", str(tmp_path / "pushed.json")):
        to_push, suppressed = push_dedup.filter_unpushed(arts, _now())
    assert len(to_push) == 2
    assert suppressed == []


def test_filter_unpushed_falls_back_to_title_without_label(tmp_path):
    arts = [
        {"title": "전문건설공제조합, 피치 신용등급 A+ 유지 - 네이트", "is_company": True, "link": "a"},
        {"title": "전문건설공제조합, 피치 국제신용등급 'A+' 유지 - 이데일리", "is_company": True, "link": "b"},
    ]
    with patch("push_dedup.PUSHED_FILE", str(tmp_path / "pushed.json")):
        to_push, suppressed = push_dedup.filter_unpushed(arts, _now())
    assert len(to_push) == 1
    assert len(suppressed) == 1


def test_filter_unpushed_v2_title_history_dedups_v3_label(tmp_path):
    # 전환기: 제목 기반(v2)으로 먼저 푸시된 사건이, 나중에 라벨 달고 온 같은 사건(v3)을 억제해야 함
    f = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.filter_unpushed(
            [{"title": "전문건설공제조합, 피치 신용등급 A+ 유지 - 네이트", "is_company": True, "link": "a"}],
            _now())
        to_push, suppressed = push_dedup.filter_unpushed(
            [{"title": "K-FINCO 피치 A+ - 이데일리",
              "event_label": "전문건설공제조합 피치 신용등급 A+ 유지",
              "is_company": True, "link": "b"}],
            _now() + timedelta(hours=1))
    assert to_push == []
    assert len(suppressed) == 1
