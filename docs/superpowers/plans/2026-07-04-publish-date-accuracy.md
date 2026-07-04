# 발행일 정확도 개선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이트·다음 포털 발행일을 파싱해 커버리지를 올리고(B), 못 뽑은 기사는 대시보드에서 "수집 N시간 전"으로 정직 표시(A)해 속보 착시를 없앤다.

**Architecture:** `pub_date._extract_published_time`에 표준 메타 이후 폴백으로 다음(`og:regDate`)·네이트(`firstDate`) 파서를 추가(KST 부착). `index.html`은 발행일 없을 때 수집시각임을 명시. 기존 `backfill_pubdate.py`를 "채우기만, 삭제 안 함"으로 바꿔 과거 333건을 1회 소급.

**Tech Stack:** Python 3.9+ (`re`, `datetime.strptime`), `pytest`, 바닐라 JS(index.html). 신규 의존성 없음.

설계 스펙: `docs/superpowers/specs/2026-07-04-publish-date-accuracy-design.md`

## Global Constraints

- 신규 의존성 금지.
- 새로 파싱한 발행일은 **KST(+09:00) tz-aware**로 저장 — 기존 published_at이 전부 tz有(naive 0건)라 일관성 유지, index.html 표시 안 깨짐.
- 파싱 우선순위: **표준 메타 5종 → og:regDate → 네이트 firstDate**. 첫 매치 반환.
- 대상 포털은 **네이트·다음만**(YAGNI — MSN·꼬리 매체 제외).
- 백필은 **채우기만, 기사 삭제 안 함**(조합 기사 무기한 보존 보호). 알림 재발송 없음.

---

### Task 1: `pub_date.py` 포털 발행일 파서 + 폴백 연결

**Files:**
- Modify: `pub_date.py` (import 18행; `_META_PATTERNS` 뒤 71행; `_extract_published_time` 113-124행)
- Test: `tests/test_pub_date.py`

**Interfaces:**
- Consumes: 없음(순수 문자열 파싱).
- Produces: `_parse_regdate(html) -> Optional[datetime]`, `_parse_nate_firstdate(html) -> Optional[datetime]`; `_extract_published_time`이 이 둘을 폴백으로 사용(반환 타입 불변 `Optional[datetime]`).

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_pub_date.py` 끝에 추가:

```python
def test_extract_daum_og_regdate():
    from datetime import timedelta
    html = '<meta property="og:regDate" content="20260624160119">'
    dt = pub_date._extract_published_time(html)
    assert dt == datetime(2026, 6, 24, 16, 1, 19, tzinfo=timezone(timedelta(hours=9)))


def test_extract_nate_firstdate():
    from datetime import timedelta
    html = '<span class="firstDate">기사전송 <em>2026-07-03 13:57</em></span>'
    dt = pub_date._extract_published_time(html)
    assert dt == datetime(2026, 7, 3, 13, 57, tzinfo=timezone(timedelta(hours=9)))


def test_standard_meta_takes_priority_over_regdate():
    html = ('<meta property="article:published_time" content="2026-01-01T00:00:00+09:00">'
            '<meta property="og:regDate" content="20260624160119">')
    dt = pub_date._extract_published_time(html)
    assert dt.month == 1 and dt.day == 1   # 표준 메타가 우선


def test_regdate_before_nate_when_both_present():
    from datetime import timedelta
    html = ('<meta property="og:regDate" content="20260624160119">'
            '<span class="firstDate">기사전송 <em>2026-07-03 13:57</em></span>')
    dt = pub_date._extract_published_time(html)
    assert dt == datetime(2026, 6, 24, 16, 1, 19, tzinfo=timezone(timedelta(hours=9)))


def test_returns_none_when_no_date_anywhere():
    assert pub_date._extract_published_time('<html><body>날짜 없음</body></html>') is None
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_pub_date.py -k "regdate or firstdate or priority or no_date" -v`
Expected: FAIL — `test_extract_daum_og_regdate` 등이 None을 받아 assert 실패

- [ ] **Step 3: `pub_date.py` 구현** — (a) import 수정, (b) 파서 추가, (c) 폴백 연결.

(a) 18행 `from datetime import datetime` → 교체:

```python
from datetime import datetime, timedelta, timezone
```

(b) `_META_PATTERNS` 리스트 정의 끝(71행) 바로 아래에 추가:

```python
_KST = timezone(timedelta(hours=9))

_REGDATE_RE = re.compile(
    r'<meta[^>]+property=["\']og:regDate["\'][^>]+content=["\'](\d{14})["\']', re.I)
_NATE_FIRSTDATE_RE = re.compile(
    r'firstDate["\'][^>]*>[^<]*<em>\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', re.I)


def _parse_regdate(html: str):
    """다음 등: og:regDate=YYYYMMDDHHMMSS (KST naive) → KST-aware datetime."""
    m = _REGDATE_RE.search(html)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=_KST)
    except ValueError:
        return None


def _parse_nate_firstdate(html: str):
    """네이트: firstDate <em>YYYY-MM-DD HH:MM</em> (KST naive) → KST-aware datetime."""
    m = _NATE_FIRSTDATE_RE.search(html)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=_KST)
    except ValueError:
        return None
```

(c) `_extract_published_time`의 마지막 `return None`을 교체:

```python
def _extract_published_time(html: str) -> Optional[datetime]:
    for pat in _META_PATTERNS:
        m = pat.search(html)
        if not m:
            continue
        # "Z" 접미사는 3.11 이전 fromisoformat이 처리 못함 → +00:00 으로 정규화
        value = m.group(1).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            continue
    return _parse_regdate(html) or _parse_nate_firstdate(html)
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest tests/test_pub_date.py -v`
Expected: PASS — 신규 5개 + 기존 전부 통과(기존 표준 메타 테스트 회귀 없음)

- [ ] **Step 5: 커밋**

```bash
git add pub_date.py tests/test_pub_date.py
git commit -m "feat: 네이트·다음 포털 발행일 파싱(og:regDate/firstDate, KST)"
```

---

### Task 2: `index.html` 발행일 없을 때 "수집 N시간 전" 표시

**Files:**
- Modify: `index.html` (`renderCard` 834-835행)

**Interfaces:**
- Consumes: 기존 `relativeTime`, `formatPublishedDate`, `escapeHtml`, 기사 객체 `a.published_at`/`a.collected_at`.
- Produces: 없음(표시 로직 변경).

*(JS 테스트 하네스 없음 — 수동/시각 확인. 브라우저에서만 검증 가능하므로 TDD 대신 편집 후 확인.)*

- [ ] **Step 1: `index.html` 834행 교체** — 현재:

```html
            <span class="time">${escapeHtml(relativeTime(a.published_at || a.collected_at))}</span>
```

교체:

```html
            <span class="time">${a.published_at ? escapeHtml(relativeTime(a.published_at)) : '수집 ' + escapeHtml(relativeTime(a.collected_at))}</span>
```

(835행 "발행 날짜" 라인은 그대로 — 발행일 있을 때만 표시.)

- [ ] **Step 2: 로컬 브라우저 확인**

Run: `cd /Users/2wodms/workspace/claude-introduction && python3 -m http.server 8765`
그다음 브라우저에서 `http://localhost:8765/` 열기.
Expected:
- 발행일 **없는** 카드(예: 네이트 기사) → 시각이 **"수집 N시간 전"**으로 표시.
- 발행일 **있는** 카드 → 기존대로 "N시간 전 · 발행 YYYY-MM-DD".
확인 후 `Ctrl+C`로 서버 종료.

- [ ] **Step 3: 커밋**

```bash
git add index.html
git commit -m "feat: 발행일 없는 기사는 '수집 N시간 전'으로 표시(속보 착시 제거)"
```

---

### Task 3: `backfill_pubdate.py` "채우기만, 삭제 안 함" 모드

**Files:**
- Modify: `backfill_pubdate.py` (결과 처리 89-103행)

**Interfaces:**
- Consumes: Task 1의 개선된 `resolve_published_time`(내부적으로 새 파서 사용).
- Produces: 없음(1회성 마이그레이션 스크립트).

*(네트워크+파일 IO 스크립트라 단위 테스트 대신 편집 검증 + 배포 시 실행 검증.)*

- [ ] **Step 1: 결과 처리 블록 교체** — 현재 89-103행:

```python
            if dt is None:
                unresolved += 1
            else:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    drops.add(i)
                    seen.add(a.get('link'))
                    log.info("DROP [%s] %s | %s",
                             dt.date().isoformat(),
                             a.get('keyword') or a.get('category'),
                             (a.get('title_clean') or a.get('title') or '')[:60])
                else:
                    a['published_at'] = dt.isoformat()
                    resolved += 1
```

교체 (7일 초과 삭제 제거 — 항상 채움):

```python
            if dt is None:
                unresolved += 1
            else:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                # 채우기 전용: 7일 초과도 삭제하지 않고 실제 발행일을 기록
                # (조합 기사 무기한 보존 보호). drops 는 항상 비어 있음.
                a['published_at'] = dt.isoformat()
                resolved += 1
```

- [ ] **Step 2: 임포트 스모크 + drop 미사용 확인**

Run: `python3 -c "import backfill_pubdate; print('import OK')"`
Expected: `import OK`

Run: `grep -n "drops.add\|DROP" backfill_pubdate.py`
Expected: 출력 없음(삭제 로직 제거됨 — `drops`는 빈 집합으로만 유지)

- [ ] **Step 3: 커밋**

```bash
git add backfill_pubdate.py
git commit -m "feat: backfill 채우기 전용 모드 — 7일 초과 기사 삭제 안 함"
```

---

### Task 4: 전체 회귀

**Files:** 없음(검증만)

- [ ] **Step 1: 전체 테스트 + 임포트 스모크**

Run: `python3 -m pytest -q`
Expected: 전체 통과(신규 pub_date 5개 포함, 회귀 없음)

Run: `python3 -c "import pub_date, backfill_pubdate; print('OK')"`
Expected: `OK`

---

## 배포 & 검증 (구현·테스트 완료 후)

코드는 `main` 머지 → push. index.html 은 GitHub Pages(main root)로 서빙되어 push 시 대시보드 갱신. articles.json 도 main 으로 서빙.

- [ ] **1. 머지·push** — feature 브랜치 → `main` 머지 후 `git pull --rebase origin main && git push`(VM 기사 커밋과 rebase).

- [ ] **2. VM 코드 반영** — VM에서 flock 걸고 수동 pull(heartbeat 배포와 동일):

```bash
ssh -i ~/.ssh/oracle_cig.key ubuntu@140.245.72.164 \
  'cd cig-monitor && flock -w 90 /tmp/cig-monitor.lock git pull --rebase origin main'
```

- [ ] **3. 백필 1회 실행 (VM, flock)** — 라이브 articles.json 대상:

```bash
ssh -i ~/.ssh/oracle_cig.key ubuntu@140.245.72.164 \
  'cd cig-monitor && flock -w 600 /tmp/cig-monitor.lock ./venv/bin/python backfill_pubdate.py'
```
Expected: 로그에 `resolved=N`(>0), `dropped=0`, `kept == total`(기사 수 불변).

- [ ] **4. 백필 결과 커밋·push (VM, flock)**:

```bash
ssh -i ~/.ssh/oracle_cig.key ubuntu@140.245.72.164 \
  'cd cig-monitor && flock -w 90 /tmp/cig-monitor.lock bash -c "git add articles.json seen.json && git commit -m \"chore: 포털 발행일 백필\" && git pull --rebase origin main && git push origin main"'
```

- [ ] **5. 대시보드 확인** — `https://sunkid94.github.io/gongje-monitor/`:
  - 네이트/다음 기사에 **발행일**이 뜨는지(백필 성공분).
  - 아직 발행일 없는 잔여 기사는 **"수집 N시간 전"**으로 뜨는지.

- [ ] **6. 로컬 동기화** — 로컬에서 `git pull --rebase origin main`로 백필된 articles.json 받기.

---

## Self-Review 결과

- **스펙 커버리지:** B 파서(Task 1: og:regDate/네이트 + 우선순위 + KST)·A 표시(Task 2)·백필 채우기전용(Task 3)·전체회귀(Task 4)·VM 백필 실행(배포)·대시보드 검증(배포) — 스펙 전 항목 대응.
- **플레이스홀더:** 코드/명령/기대출력 전부 실제 내용. index.html·backfill 은 테스트 하네스 부재를 명시하고 수동/운영 검증으로 대체(플레이스홀더 아님).
- **타입 일관성:** `_parse_regdate`/`_parse_nate_firstdate` → `Optional[datetime]`, `_extract_published_time` 반환 타입 불변. KST tz는 Task 1 구현·테스트·스펙에서 `timezone(timedelta(hours=9))`로 일치. index.html은 `a.published_at` 유무로만 분기(기존 함수 재사용).
