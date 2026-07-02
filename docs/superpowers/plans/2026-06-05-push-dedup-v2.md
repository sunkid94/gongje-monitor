# 푸시 중복제거 v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 같은 뉴스 사건이 조직 이름 표기·헤드라인 수식어가 달라 여러 번 푸시되는 것을, 조직 별칭 통합 + 포함도(overlap) 매칭 + 7일 창으로 잡는다.

**Architecture:** 기존 `push_dedup.py`를 확장한다. 순수 함수 `canonical_org`(별칭→대표조직)와 `overlap`(포함도 계수)를 추가하고, `filter_unpushed`의 억제 조건을 "lead 일치 + Jaccard≥0.6"에서 "대표조직(canon) 일치 + overlap≥0.7"로 교체한다. 창은 24h→168h(7일). `pushed.json` 엔트리의 `lead` 필드는 `canon`으로 대체한다. 외부 인터페이스(`filter_unpushed`)와 notifier 연동은 불변.

**Tech Stack:** Python 3.10+, 표준 라이브러리, pytest 8.3.4. 신규 의존성 없음.

설계 스펙: `docs/superpowers/specs/2026-06-05-push-dedup-v2-org-alias-design.md`
대상 파일 현재 상태: `push_dedup.py` (v1, 158줄), `tests/test_push_dedup.py` (v1 테스트 25개)

---

## File Structure

| 파일 | 변경 |
|------|------|
| `push_dedup.py` | `ORG_ALIASES` 상수 + `canonical_org()` 추가; `overlap()` 추가; `similarity()` 제거; `WINDOW_HOURS` 24→168; `load_pushed`/`save_pushed`의 `lead`→`canon`; `filter_unpushed` 매칭 교체 |
| `tests/test_push_dedup.py` | `canonical_org`/`overlap` 테스트 추가; `similarity` 테스트 제거; 창·필드 변경에 맞춰 기존 테스트 갱신; v2 통합 테스트(피치 5변형 수렴 등) 추가 |

**인터페이스 (Task 간 계약):**
- `canonical_org(title: str) -> str`
- `overlap(a: set, b: set) -> float`
- `ORG_ALIASES: dict[str, list[str]]`, `OVERLAP_THRESHOLD = 0.7`, `WINDOW_HOURS = 168`
- pushed 엔트리: `{"tokens": set, "canon": str, "pushed_at": str, "title": str}`

---

### Task 1: `ORG_ALIASES` + `canonical_org`

**Files:**
- Modify: `push_dedup.py`
- Test: `tests/test_push_dedup.py`

- [ ] **Step 1: 실패 테스트 작성** (`tests/test_push_dedup.py` 끝에 추가)

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_push_dedup.py -k canonical_org -v`
Expected: FAIL — `AttributeError: module 'push_dedup' has no attribute 'canonical_org'`

- [ ] **Step 3: 구현** — `push_dedup.py`의 `_LEADING_BRACKET_RE` 정의 아래(상수 영역)에 `ORG_ALIASES` 추가:

```python
# 같은 조직의 다른 표기 — 여기에 추가하면 묶임 (모두 소문자/정규화 형태로 비교됨)
ORG_ALIASES = {
    "전문건설공제조합": ["전문조합", "k finco", "kfinco", "k-finco"],
    "기계설비건설공제조합": ["cig", "기계설비공제조합"],   # 우리 조합
}
```

그리고 `story_lead` 함수 바로 아래에 `canonical_org` 추가:

```python
def canonical_org(title: str) -> str:
    """선두 조직명을 대표 이름으로 환산. 별칭이면 대표값, 아니면 lead 원본.

    ORG_ALIASES 의 대표명 또는 별칭 문자열이 정규화된 lead 에 포함되면 그 대표명을 반환한다.
    목록에 없으면 lead 를 그대로 돌려준다(보수적 = 안 묶음). 더 구체적인(긴) 후보부터
    검사해 짧은 별칭의 오매칭을 줄인다.
    """
    lead = story_lead(title)
    if not lead:
        return ""
    # (대표명 자신 + 별칭) 을 모두 후보로, 긴 문자열 우선
    candidates = []
    for canon, aliases in ORG_ALIASES.items():
        for name in [canon] + aliases:
            candidates.append((name.lower(), canon))
    candidates.sort(key=lambda x: len(x[0]), reverse=True)
    for name, canon in candidates:
        if name in lead:
            return canon
    return lead
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest tests/test_push_dedup.py -k canonical_org -v`
Expected: PASS (4개)

- [ ] **Step 5: 커밋**

```bash
git add push_dedup.py tests/test_push_dedup.py
git commit -m "feat: push_dedup ORG_ALIASES + canonical_org 조직 별칭 통합"
```

---

### Task 2: `overlap` 포함도 계수

**Files:**
- Modify: `push_dedup.py`
- Test: `tests/test_push_dedup.py`

- [ ] **Step 1: 실패 테스트 작성** (끝에 추가)

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_push_dedup.py -k overlap -v`
Expected: FAIL — `AttributeError: module 'push_dedup' has no attribute 'overlap'`

- [ ] **Step 3: 구현** — `push_dedup.py`의 `similarity` 함수 **바로 아래**에 추가(아직 `similarity` 는 지우지 말 것 — Task 4에서 제거):

```python
def overlap(a: set, b: set) -> float:
    """포함도 계수 = 교집합 / 더 짧은 쪽 크기. 둘 중 하나라도 비면 0.

    수식어가 붙어 길어진 헤드라인 변형(짧은 제목 ⊂ 긴 제목)을 Jaccard 보다 잘 잡는다.
    """
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest tests/test_push_dedup.py -k overlap -v`
Expected: PASS (3개)

- [ ] **Step 5: 커밋**

```bash
git add push_dedup.py tests/test_push_dedup.py
git commit -m "feat: push_dedup overlap 포함도 계수"
```

---

### Task 3: 7일 창 + `lead`→`canon` 필드 전환 (load/save)

**Files:**
- Modify: `push_dedup.py` (`WINDOW_HOURS`, `load_pushed`, `save_pushed`)
- Test: `tests/test_push_dedup.py` (창·필드 관련 기존 테스트 갱신)

- [ ] **Step 1: 상수 변경** — `push_dedup.py`:

기존:
```python
WINDOW_HOURS = 24
```
변경:
```python
WINDOW_HOURS = 168   # 7일 — 며칠 이어지는 사건도 1번만 알림
```

- [ ] **Step 2: `load_pushed` 의 반환 dict에서 `lead`→`canon`** — 해당 블록을 교체:

기존:
```python
        out.append({
            "tokens": set(item.get("tokens", [])),
            "lead": item.get("lead", ""),
            "pushed_at": item["pushed_at"],
            "title": item.get("title", ""),
        })
```
변경:
```python
        out.append({
            "tokens": set(item.get("tokens", [])),
            "canon": item.get("canon", ""),
            "pushed_at": item["pushed_at"],
            "title": item.get("title", ""),
        })
```

- [ ] **Step 3: `save_pushed` 의 직렬화 dict에서 `lead`→`canon`** — 교체:

기존:
```python
        serializable.append({
            "tokens": sorted(e.get("tokens", [])),
            "lead": e.get("lead", ""),
            "pushed_at": e["pushed_at"],
            "title": e.get("title", ""),
        })
```
변경:
```python
        serializable.append({
            "tokens": sorted(e.get("tokens", [])),
            "canon": e.get("canon", ""),
            "pushed_at": e["pushed_at"],
            "title": e.get("title", ""),
        })
```

- [ ] **Step 4: 창·필드 관련 기존 테스트 갱신.** `tests/test_push_dedup.py`에서 아래 4개 테스트를 찾아 교체한다(24h 가정 → 168h, `lead`→`canon`).

(a) `test_load_pushed_drops_entries_older_than_window` — stale 기준을 25h→200h로:
```python
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
```

(b) `test_save_pushed_prunes_stale_and_writes_lists` — stale 30h→200h:
```python
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
```

(c) `test_save_then_load_roundtrip_tokens_as_set` — `lead`→`canon`:
```python
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
```

(d) `test_filter_repushes_after_window_expires` — 25h→8일(192h) 후 재push:
```python
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
```

- [ ] **Step 5: 실행** — load/save/roundtrip/window 테스트 통과(필터 테스트는 Task 4 전이라 일부 실패 가능 — 아래 명령은 load/save/roundtrip만):

Run: `python3 -m pytest tests/test_push_dedup.py -k "load_pushed or save_pushed or roundtrip" -v`
Expected: PASS (해당 테스트들). 참고: `test_filter_repushes_after_window_expires` 는 Task 4에서 filter가 canon/overlap으로 바뀐 뒤 최종 통과한다.

- [ ] **Step 6: 커밋**

```bash
git add push_dedup.py tests/test_push_dedup.py
git commit -m "feat: push_dedup 7일 창 + pushed 엔트리 lead→canon 전환"
```

---

### Task 4: `filter_unpushed` v2 매칭 (canon 게이트 + overlap) + 정리

**Files:**
- Modify: `push_dedup.py` (`filter_unpushed`, `similarity` 제거, 모듈 docstring)
- Test: `tests/test_push_dedup.py` (`similarity` 테스트 제거, 브랜드 테스트 갱신, v2 통합 테스트 추가)

- [ ] **Step 1: v2 통합/갱신 테스트 작성.**

먼저 **제거**: `tests/test_push_dedup.py`에서 `similarity` 관련 테스트 4개를 삭제한다 — `test_similarity_identical_sets_is_one`, `test_similarity_disjoint_sets_is_zero`, `test_similarity_jaccard_value`, `test_similarity_empty_sets_is_zero`.

다음 **갱신**: `test_filter_does_not_suppress_different_brand_same_batch` 는 v2에서 의미가 반대가 된다(K-FINCO=전문건설공제조합 별칭이라 이제 묶여야 함). 함수 전체를 아래로 교체:
```python
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
```

다음 **추가**(끝에): 실제 피치 5변형 수렴 + 분리 케이스.
```python
# 2026-06-05 실측 "피치/신용등급" 표현 계열 5변형 (매체·표기·수식어 상이, 같은 사건)
FITCH_V2 = [
    "K-FINCO, 피치 신용등급 'A+' 유지…6.5조 자본력 인정 - 뉴스핌",
    "전문건설공제조합, 피치 신용등급 'A+' 유지 - 국토일보",
    "전문건설공제조합, 피치 국제신용등급 'A+'…자본력 탄탄 - 데일리안",
    "전문건설공제조합, 글로벌 신용평가사 피치 국제신용등급'A+' 유지 - kscnews",
    "K-FINCO, 글로벌 신용평가사 피치 국제신용등급 'A+' 유지 - 대한전문건설신문",
]


def test_filter_v2_collapses_fitch_variants_to_one(tmp_path):
    arts = [_article(t) for t in FITCH_V2]
    with patch("push_dedup.PUSHED_FILE", str(tmp_path / "pushed.json")):
        to_push, suppressed = push_dedup.filter_unpushed(arts, _now())
    assert len(to_push) == 1      # 첫 건만
    assert len(suppressed) == 4   # 나머지 4건 억제


def test_filter_v2_our_coop_not_suppressed_by_sibling(tmp_path):
    # 우리 조합(기계설비/CIG)은 전문건설과 다른 조직 → 같은 등급 이벤트라도 각각 발송
    f = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.filter_unpushed([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - A")], _now())
        to_push, suppressed = push_dedup.filter_unpushed(
            [_article("기계설비건설공제조합, 피치 신용등급 A+ 유지 - B")], _now() + timedelta(hours=1)
        )
    assert len(to_push) == 1
    assert suppressed == []


def test_filter_v2_same_org_different_event_not_suppressed(tmp_path):
    # 같은 조직이라도 다른 사건(피치 vs ESG)은 overlap 낮음 → 각각 발송
    f = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(f)):
        push_dedup.filter_unpushed([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - A")], _now())
        to_push, suppressed = push_dedup.filter_unpushed(
            [_article("전문건설공제조합, ESG 경영 평가 최우수 등급 - B")], _now() + timedelta(hours=1)
        )
    assert len(to_push) == 1
    assert suppressed == []
```

참고: 기존 `test_filter_collapses_same_brand_variants_to_one`(FITCH_GONGJE, 전부 전문건설공제조합), `test_filter_distinct_stories_both_pushed`, `test_filter_does_not_suppress_across_different_orgs`, `test_filter_suppresses_story_already_pushed_in_history`, `test_filter_still_suppresses_same_org_variant`, `test_filter_repushes_after_window_expires`, `test_filter_suppresses_bracketed_and_plain_same_org`, `test_filter_empty_key_article_is_pushed_not_recorded` 는 **그대로 통과해야 한다**(canon 은 lead 로 폴백, overlap 으로도 동일 결론). 수정하지 말 것.

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_push_dedup.py -k "v2 or merges_brand" -v`
Expected: FAIL — 아직 `filter_unpushed` 가 lead+similarity 기반이라 별칭/overlap 미적용

- [ ] **Step 3: 구현** — `push_dedup.py` 세 가지 변경.

(1) `filter_unpushed` 의 루프를 canon+overlap 으로 교체. 함수 본문에서 per-article 블록을 교체:

기존:
```python
    for art in company_articles:
        title = art.get("title", "")
        key = story_key(title)
        lead = story_lead(title)
        if key and any(
            e["tokens"] and e.get("lead", "") == lead
            and similarity(key, e["tokens"]) >= SIMILARITY_THRESHOLD
            for e in accepted
        ):
            suppressed.append(art)
            continue
        to_push.append(art)
        if key:
            accepted.append({"tokens": key, "lead": lead, "pushed_at": now_iso, "title": title})
```
변경:
```python
    for art in company_articles:
        title = art.get("title", "")
        key = story_key(title)
        canon = canonical_org(title)
        if key and any(
            e["tokens"] and e.get("canon", "") == canon
            and overlap(key, e["tokens"]) >= OVERLAP_THRESHOLD
            for e in accepted
        ):
            suppressed.append(art)
            continue
        to_push.append(art)
        if key:
            accepted.append({"tokens": key, "canon": canon, "pushed_at": now_iso, "title": title})
```

(2) 상수 추가/정리 — `SIMILARITY_THRESHOLD = 0.6` 줄을 아래로 교체:
```python
OVERLAP_THRESHOLD = 0.7
```

(3) `similarity` 함수 **제거**(54~61줄의 def similarity 블록 전체 삭제). 그리고 모듈 docstring(3~4줄)을 갱신:

기존:
```python
같은 뉴스 사건이 여러 매체/cluster_id 로 흩어져 24시간 내 반복 푸시되는 것을 막는다.
제목 핵심어 집합(story_key) 의 Jaccard 유사도가 임계값 이상이면 같은 스토리로 간주한다.
```
변경:
```python
같은 뉴스 사건이 여러 매체/표기/수식어로 흩어져 7일 내 반복 푸시되는 것을 막는다.
대표조직(canonical_org) 이 같고 핵심어 포함도(overlap) 가 임계값 이상이면 같은 스토리로 본다.
```

`filter_unpushed` 의 docstring 첫 줄도 갱신:
```python
    """7일 내 같은 대표조직·같은 사건(overlap>=임계값)으로 이미 푸시했으면 억제.
```

- [ ] **Step 4: 전체 테스트 통과 확인**

Run: `python3 -m pytest tests/test_push_dedup.py -v`
Expected: PASS — `similarity` 테스트 4개 삭제됨, 나머지 전부 통과(피치 5변형 1/4 수렴 포함). 그 다음 전체 스위트:

Run: `python3 -m pytest -q`
Expected: PASS (회귀 없음; v1 대비 similarity 테스트 4개 감소 + v2 테스트 추가)

- [ ] **Step 5: 커밋**

```bash
git add push_dedup.py tests/test_push_dedup.py
git commit -m "feat: filter_unpushed v2 — canon 게이트 + overlap 매칭, similarity 제거"
```

---

## Self-Review 결과

- **스펙 커버리지:** ORG_ALIASES/canonical_org(Task 1)↔스펙 "조직 별칭 통합"; overlap(Task 2)↔"매칭 방식 변경"; 7일 창·canon 필드(Task 3)↔"창 24h→7일"·"데이터/호환"; filter v2(Task 4)↔"filter_unpushed 변경"; 테스트(Task 1~4)↔스펙 "테스트(TDD)" 1~7 전부 대응(피치 수렴, 우리 조합 분리, 같은 조직 다른 사건 분리, 7일 창, canonical_org, overlap). 비목표(발행일 필터·이메일·구조변경)는 손대지 않음.
- **플레이스홀더:** 없음 — 모든 코드/테스트 단계에 실제 내용.
- **타입 일관성:** `canonical_org(str)->str`, `overlap(set,set)->float`, 엔트리 필드 `canon`(load/save/filter 일치), `OVERLAP_THRESHOLD`/`WINDOW_HOURS=168` 일관. `similarity` 제거에 맞춰 그 테스트도 제거.
- **현실 보정(스펙과 합치):** 피치 "보험지급능력 A+" 표현은 overlap 0.7에서 별개 가능 → 통합 테스트는 "피치/신용등급" 5변형의 1건 수렴만 단언(과대약속 회피). 사용자가 받은 13:57 알람은 억제됨.

---
> 📑 관련 문서 전체 지도: [CIG 이슈 모니터 문서 인덱스](../CIG-MONITOR-INDEX.md)
