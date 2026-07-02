# 푸시 스토리 단위 중복제거 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 같은 뉴스 사건이 여러 매체/cluster_id로 흩어져 24시간 내 여러 번 푸시되는 문제를, 푸시 직전 스토리 단위 중복제거 필터로 해결한다(첫 알람·웹·이메일 동작 불변).

**Architecture:** 신규 모듈 `push_dedup.py`가 제목 핵심어 집합(`story_key`) + Jaccard 유사도 0.6 + 24시간 창으로 "이미 알린 스토리"를 판정하고, 발송 이력을 `pushed.json`에 원자적으로 저장한다. `notifier.send_company_push`는 실제 발송이 가능함을 확인한 뒤 이 필터를 태워 신규 스토리만 webpush로 보낸다.

**Tech Stack:** Python 3.10+, 표준 라이브러리(json/re/os/datetime), pytest 8.3.4, pywebpush(기존). 신규 의존성 없음.

설계 스펙: `docs/superpowers/specs/2026-06-04-push-story-dedup-design.md`

---

## File Structure

| 파일 | 책임 |
|------|------|
| `push_dedup.py` (신규) | 스토리 키 생성, Jaccard 유사도, 푸시 이력 로드/원자적 저장, 중복 필터 |
| `notifier.py` (수정) | `send_company_push`에서 발송 가능 확인 후 `filter_unpushed` 호출, 억제 로깅, `to_push`만 발송 |
| `tests/test_push_dedup.py` (신규) | `story_key`/`similarity`/`load`/`save`/`filter_unpushed` 단위·통합 테스트 |
| `tests/test_notifier.py` (신규) | `send_company_push` 통합 테스트(중복 스토리 미발송, 발송불가 시 미기록) |
| `.gitignore` (수정) | `pushed.json` 무시 추가 |

**핵심 인터페이스 (Task 간 계약):**
- `story_key(title: str) -> set[str]`
- `similarity(a: set, b: set) -> float`
- `load_pushed(now: datetime) -> list[dict]` — 각 dict: `{"tokens": set[str], "pushed_at": str, "title": str}`
- `save_pushed(entries: list[dict], now: datetime) -> None`
- `filter_unpushed(company_articles: list[dict], now: datetime) -> tuple[list[dict], list[dict]]`
- 모듈 상수: `PUSHED_FILE`, `SIMILARITY_THRESHOLD = 0.6`, `WINDOW_HOURS = 24`

모든 시각은 tz-aware datetime. 테스트는 고정 `now`를 주입한다.

---

### Task 1: `story_key` + `similarity` (순수 함수)

**Files:**
- Create: `push_dedup.py`
- Test: `tests/test_push_dedup.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_push_dedup.py`:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_push_dedup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'push_dedup'`

- [ ] **Step 3: 최소 구현 작성**

`push_dedup.py`:

```python
"""푸시 스토리 단위 중복제거.

같은 뉴스 사건이 여러 매체/cluster_id 로 흩어져 24시간 내 반복 푸시되는 것을 막는다.
제목 핵심어 집합(story_key) 의 Jaccard 유사도가 임계값 이상이면 같은 스토리로 간주한다.
"""
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timedelta
from typing import List, Tuple

logger = logging.getLogger(__name__)

PUSHED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pushed.json")
SIMILARITY_THRESHOLD = 0.6
WINDOW_HOURS = 24
_MIN_TOKEN_LEN = 2

# 매체명 접미사 분리용: 제목은 "… 본문 - 매체명" 형태
_PUBLISHER_SEP = " - "
# 토큰 경계로 치환할 기호 (단, '+' 는 'A+' 같은 등급 표기 보존 위해 제외)
_PUNCT_RE = re.compile(r"""["'‘’“”()\[\]<>·,.\-–—:;!?…“”‘’]+""")


def story_key(title: str) -> set:
    """제목을 정규화해 핵심어 토큰 집합을 반환."""
    if not title:
        return set()
    body = title.rsplit(_PUBLISHER_SEP, 1)[0] if _PUBLISHER_SEP in title else title
    cleaned = _PUNCT_RE.sub(" ", body).lower()
    return {tok for tok in cleaned.split() if len(tok) >= _MIN_TOKEN_LEN}


def similarity(a: set, b: set) -> float:
    """Jaccard 유사도. 합집합이 비면 0."""
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_push_dedup.py -v`
Expected: PASS (위 8개 테스트)

- [ ] **Step 5: 커밋**

```bash
git add push_dedup.py tests/test_push_dedup.py
git commit -m "feat: push_dedup story_key/similarity 순수 함수"
```

---

### Task 2: `load_pushed` / `save_pushed` (24h 창 + 원자적 쓰기)

**Files:**
- Modify: `push_dedup.py`
- Test: `tests/test_push_dedup.py`

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_push_dedup.py` 끝에 추가)

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_push_dedup.py -k "pushed and (load or save or roundtrip)" -v`
Expected: FAIL — `AttributeError: module 'push_dedup' has no attribute 'load_pushed'`

- [ ] **Step 3: 최소 구현 추가** (`push_dedup.py`의 `similarity` 아래에 추가)

```python
def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def load_pushed(now: datetime) -> List[dict]:
    """pushed.json 로드 — WINDOW_HOURS 이내 항목만, tokens 를 set 으로 복원.

    파일 없음/JSON 손상 시 빈 리스트(안전쪽: 이력 없으면 발송 진행 → 알림 누락 방지).
    """
    try:
        with open(PUSHED_FILE, "r", encoding="utf-8") as fp:
            raw = json.load(fp)
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("pushed.json 로드 실패(빈 이력으로 진행): %s", e)
        return []

    cutoff = now - timedelta(hours=WINDOW_HOURS)
    out = []
    for item in raw if isinstance(raw, list) else []:
        try:
            pushed_at = _parse_dt(item["pushed_at"])
        except (KeyError, ValueError, TypeError):
            continue
        if pushed_at < cutoff:
            continue
        out.append({
            "tokens": set(item.get("tokens", [])),
            "pushed_at": item["pushed_at"],
            "title": item.get("title", ""),
        })
    return out


def save_pushed(entries: List[dict], now: datetime) -> None:
    """WINDOW_HOURS 경과분 정리 후 원자적(temp + os.replace)으로 저장. tokens 는 list 직렬화."""
    cutoff = now - timedelta(hours=WINDOW_HOURS)
    serializable = []
    for e in entries:
        try:
            if _parse_dt(e["pushed_at"]) < cutoff:
                continue
        except (KeyError, ValueError, TypeError):
            continue
        serializable.append({
            "tokens": sorted(e.get("tokens", [])),
            "pushed_at": e["pushed_at"],
            "title": e.get("title", ""),
        })
    dir_ = os.path.dirname(os.path.abspath(PUSHED_FILE))
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".pushed-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(serializable, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, PUSHED_FILE)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_push_dedup.py -v`
Expected: PASS (Task 1 + Task 2 전체)

- [ ] **Step 5: 커밋**

```bash
git add push_dedup.py tests/test_push_dedup.py
git commit -m "feat: push_dedup 24h 창 load/save 원자적 쓰기"
```

---

### Task 3: `filter_unpushed` (중복 판정 + 피치 통합 시나리오)

**Files:**
- Modify: `push_dedup.py`
- Test: `tests/test_push_dedup.py`

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_push_dedup.py` 끝에 추가)

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_push_dedup.py -k filter -v`
Expected: FAIL — `AttributeError: module 'push_dedup' has no attribute 'filter_unpushed'`

- [ ] **Step 3: 최소 구현 추가** (`push_dedup.py` 끝에 추가)

```python
def filter_unpushed(company_articles: List[dict], now: datetime) -> Tuple[List[dict], List[dict]]:
    """24h 내 이미 푸시한 스토리와 Jaccard >= 임계값이면 억제.

    반환: (to_push, suppressed). 새로 채택한 스토리는 pushed.json 에 기록한다.
    제목 키가 비면(추출 실패) 안전쪽으로 발송하되 이력에는 남기지 않는다.
    """
    accepted = load_pushed(now)          # 비교 기준: 이력 + 이번 배치에서 채택된 것
    now_iso = now.isoformat()
    to_push: List[dict] = []
    suppressed: List[dict] = []

    for art in company_articles:
        key = story_key(art.get("title", ""))
        if key and any(
            similarity(key, e["tokens"]) >= SIMILARITY_THRESHOLD
            for e in accepted if e["tokens"]
        ):
            suppressed.append(art)
            continue
        to_push.append(art)
        if key:
            accepted.append({"tokens": key, "pushed_at": now_iso, "title": art.get("title", "")})

    save_pushed(accepted, now)
    return to_push, suppressed
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_push_dedup.py -v`
Expected: PASS (Task 1~3 전체)

- [ ] **Step 5: 커밋**

```bash
git add push_dedup.py tests/test_push_dedup.py
git commit -m "feat: push_dedup filter_unpushed 스토리 중복 억제"
```

---

### Task 4: `notifier.send_company_push` 통합

**Files:**
- Modify: `notifier.py` (`send_company_push` 함수, 현재 파일 끝 함수)
- Test: `tests/test_notifier.py` (신규)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_notifier.py`:

```python
from unittest.mock import patch
import notifier


def _article(title):
    return {"title": title, "is_company": True, "link": title}


@patch("notifier.webpush")
@patch("notifier._load_subscriptions")
def test_duplicate_story_not_sent_on_second_batch(mock_subs, mock_webpush, tmp_path, monkeypatch):
    mock_subs.return_value = [{"sub": {"endpoint": "https://x"}, "name": "tester"}]
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "dummy-key")
    with patch("push_dedup.PUSHED_FILE", str(tmp_path / "pushed.json")):
        notifier.send_company_push([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - 네이트")])
        first_calls = mock_webpush.call_count
        notifier.send_company_push([_article("전문건설공제조합, 피치 국제신용등급 'A+' 유지 - 이데일리")])
        second_calls = mock_webpush.call_count - first_calls
    assert first_calls == 1     # 첫 스토리 발송
    assert second_calls == 0    # 같은 스토리 재발송 안 함


@patch("notifier.webpush")
@patch("notifier._load_subscriptions")
def test_no_record_when_no_subscribers(mock_subs, mock_webpush, tmp_path, monkeypatch):
    # 구독자 없음 → filter_unpushed 호출 전 반환, 이력 미생성 → 나중에 정상 발송 가능
    mock_subs.return_value = []
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "dummy-key")
    pushed = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(pushed)):
        notifier.send_company_push([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - 네이트")])
    assert not pushed.exists()  # 발송 못 했으면 스토리를 '푸시됨'으로 기록하지 않음
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_notifier.py -v`
Expected: FAIL — 두 번째 배치도 webpush 호출됨(`second_calls == 1`), 그리고 `pushed.json` 이 생성됨(현재 코드엔 필터/순서 변경 없음)

- [ ] **Step 3: 구현 — `send_company_push` 교체**

`notifier.py` 상단 import 에 추가 (기존 `import os` 등과 함께):

```python
from datetime import datetime

import push_dedup
```

기존 `send_company_push` 함수 전체를 아래로 교체. **변경 핵심:** (1) 구독자·VAPID 키 확인을 먼저 해 발송 불가 시 필터를 타지 않게 하고(미발송 스토리를 '푸시됨'으로 기록하는 버그 방지), (2) `filter_unpushed` 로 거른 `to_push` 만 payload·발송에 사용.

```python
def send_company_push(articles: Iterable[dict]) -> None:
    """is_company 기사 중 최근 24h 내 미발송 스토리만 구독자 전원에게 푸시."""
    company = [a for a in articles if a.get("is_company")]
    if not company:
        logger.info("조합 기사 없음 — 푸시 알림 건너뜀")
        return

    subs = _load_subscriptions()
    if not subs:
        logger.info("구독자 없음 — 푸시 알림 건너뜀")
        return

    private_key = (os.environ.get("VAPID_PRIVATE_KEY") or "").strip()
    if not private_key:
        logger.warning("VAPID_PRIVATE_KEY 미설정 — 푸시 알림 건너뜀")
        return

    # 발송 가능 확인 후에 스토리 중복 필터 (미발송 스토리를 기록하지 않도록 순서 중요)
    to_push, suppressed = push_dedup.filter_unpushed(company, datetime.now().astimezone())
    if suppressed:
        logger.info("스토리 중복 %d건 푸시 억제", len(suppressed))
    if not to_push:
        logger.info("모두 기존 스토리 중복 — 푸시 알림 건너뜀")
        return

    payload = _build_payload(to_push)
    sent, expired, auth_failed, other_failed = 0, [], [], 0
    for item in subs:
        try:
            webpush(
                subscription_info=item["sub"],
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
            )
            sent += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None) if e.response is not None else None
            if status in EXPIRED_STATUS:
                expired.append(item)
            elif status in AUTH_FAILED_STATUS:
                auth_failed.append(item)
            else:
                other_failed += 1
            logger.error("Web Push 실패 [%s] (status=%s, name=%s)", (item["sub"].get("endpoint") or "")[:50], status, item["name"])

    logger.info(
        "Web Push 발송 결과: 성공 %d / 만료 %d / 인증실패 %d / 기타실패 %d (신규 스토리 %d건)",
        sent, len(expired), len(auth_failed), other_failed, len(to_push),
    )
    _send_admin_alert(expired, auth_failed)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_notifier.py -v`
Expected: PASS (2개 테스트)

- [ ] **Step 5: 커밋**

```bash
git add notifier.py tests/test_notifier.py
git commit -m "feat: send_company_push 스토리 중복 필터 통합"
```

---

### Task 5: `pushed.json` gitignore + 전체 회귀 검증

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: `.gitignore` 에 추가**

`.gitignore` 끝에 한 줄 추가(이미 있으면 생략):

```
pushed.json
```

- [ ] **Step 2: 전체 테스트 스위트 실행**

Run: `python3 -m pytest -q`
Expected: PASS — 신규 `test_push_dedup.py`(Task 1~3의 18개) + `test_notifier.py`(2개) 포함, 기존 테스트 전부 통과(회귀 없음)

- [ ] **Step 3: import 스모크 체크**

Run: `python3 -c "import main, notifier, push_dedup; print('import OK')"`
Expected: `import OK`

- [ ] **Step 4: 커밋**

```bash
git add .gitignore
git commit -m "chore: pushed.json gitignore 추가"
```

---

## 배포 (구현·검증 완료 후, 사용자 확인 하에)

`reference_cig_monitor_deploy.md` 워크플로 — Oracle VM(140.245.72.164)에 `push_dedup.py`, `notifier.py` scp 반영. `pushed.json` 은 첫 실행 시 자동 생성. scp 후 VM working tree 정리(미정리 시 cron git push 깨짐), 수동 검증은 cron 5분 마크를 피해 1회 실행하고 `monitor.log` 에서 "스토리 중복 N건 푸시 억제" 로그 확인.

---

## Self-Review 결과

- **스펙 커버리지:** push_dedup 모듈(Task 1~3) ↔ 스펙 "컴포넌트" 절, notifier 통합(Task 4) ↔ "통합 지점", 24h 창/원자적 쓰기(Task 2) ↔ "엣지 케이스", 테스트 6종(Task 1~4) ↔ 스펙 "테스트(TDD)" 1~6 전부 대응. 배포 절 대응.
- **플레이스홀더:** 없음 — 모든 코드 단계에 실제 코드 포함.
- **타입 일관성:** `story_key`(set 반환), `similarity`(set,set→float), `load_pushed`(tokens를 set으로 복원), `save_pushed`(tokens를 list 직렬화), `filter_unpushed`(tuple 반환) — Task 간 시그니처/속성명(`tokens`/`pushed_at`/`title`) 일치 확인.
- **알려진 한계(스펙과 합치):** 브랜드명이 다른 변형(K-FINCO ↔ 전문건설공제조합)은 같은 조직 단정의 과잉 억제 위험 때문에 병합하지 않음. ~10회 → 2~3회 감소가 목표.

---
> 📑 관련 문서 전체 지도: [CIG 이슈 모니터 문서 인덱스](../CIG-MONITOR-INDEX.md)
