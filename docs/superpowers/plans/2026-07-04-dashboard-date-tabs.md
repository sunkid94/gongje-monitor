# 대시보드 탭 발행일 기준 + 정렬 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대시보드 기간 탭 필터·정렬을 발행일(없으면 수집일) 기준으로 통일하고, 오늘/어제를 달력일로 분리하며, 목록을 발행일 최신순으로 정렬한다.

**Architecture:** index.html 전용. `effectiveDate(a)=published_at||collected_at` 헬퍼를 추가하고, `inPeriod`에 오늘(달력) 분기를 넣고, 필터 호출부 2곳을 effectiveDate로 바꾸고, `filtered()` 결과를 발행일 desc 정렬한다.

**Tech Stack:** 바닐라 JS(index.html). JS 테스트 하네스 없음 — 파이썬 로직 재현 + 브라우저 수동 검증.

설계 스펙: `docs/superpowers/specs/2026-07-04-dashboard-date-tabs-design.md`

## Global Constraints

- 백엔드/수집/저장 무변경 — index.html 만.
- 기준 날짜 = `published_at` 우선, 없으면 `collected_at`.
- 오늘 = 달력상 오늘(로컬 KST 0시~지금), 어제 = 달력상 어제(0~24시, 오늘과 disjoint), 7일/30일 = 롤링, 전체 = 전부.
- 정렬 = effective date 내림차순(발행일 없으면 수집일로 참여, 최하단).

## File Structure

| 파일 | 변경 |
|------|------|
| `index.html` (수정) | `effectiveDate()` 추가 · `inPeriod` 오늘 달력 분기 · 필터 호출부 2곳 · `filtered()` 정렬 |

---

### Task 1: index.html 탭 발행일 기준 + 정렬

**Files:**
- Modify: `index.html` (`inPeriod` 846~873, `filtered` 902~906, `updateCatCounts` ~939)

- [ ] **Step 1: `effectiveDate` 헬퍼 추가** — `filtered()` 정의(902행) 바로 위에 삽입:

```javascript
    function effectiveDate(a) { return a.published_at || a.collected_at || ''; }

```

- [ ] **Step 2: `inPeriod`에 오늘(달력) 분기 추가** — 현재 마지막 두 줄:

```javascript
      return (Date.now() - t) <= state.period * 86400000;
    }
```

을 다음으로 교체(오늘 분기를 롤링 앞에):

```javascript
      if (state.period === 1) {
        // 달력상 오늘 (로컬=KST 0시 ~ 지금)
        const now = new Date();
        const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
        return t >= startToday;
      }
      return (Date.now() - t) <= state.period * 86400000;   // 7일/30일 = 롤링
    }
```

- [ ] **Step 3: `filtered()` — effectiveDate 필터 + 발행일 desc 정렬** — 현재:

```javascript
    function filtered() {
      return allArticles.filter(a =>
        inPeriod(a.collected_at) && matchesGroup(a) && matchesQuery(a)
      );
    }
```

교체:

```javascript
    function filtered() {
      return allArticles
        .filter(a => inPeriod(effectiveDate(a)) && matchesGroup(a) && matchesQuery(a))
        .sort((x, y) => new Date(effectiveDate(y) || 0) - new Date(effectiveDate(x) || 0));
    }
```

- [ ] **Step 4: `updateCatCounts()` 카운트 호출부 교체** — 현재:

```javascript
      const base = allArticles.filter(a => inPeriod(a.collected_at) && matchesQuery(a));
```

교체:

```javascript
      const base = allArticles.filter(a => inPeriod(effectiveDate(a)) && matchesQuery(a));
```

- [ ] **Step 5: 로직 파이썬 재현 검증** — 오늘/어제 disjoint + 정렬 확인:

Run:
```bash
cd /Users/2wodms/workspace/claude-introduction && python3 - <<'PY'
import json
from datetime import datetime, timezone, timedelta
d = json.load(open('articles.json'))
now = datetime.now().astimezone()
def eff(a):
    s = a.get('published_at') or a.get('collected_at') or ''
    try: return datetime.fromisoformat(s)
    except ValueError: return None
start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
today = {id(a) for a in d if (t:=eff(a)) and t >= start_today}
yday  = {id(a) for a in d if (t:=eff(a)) and start_today - timedelta(days=1) <= t < start_today}
print('오늘', len(today), '| 어제', len(yday), '| 교집합', len(today & yday), '(0이어야 함)')
# 전체 발행일 desc 정렬이 단조인지 표본 확인
allsorted = sorted([a for a in d if eff(a)], key=lambda a: eff(a), reverse=True)
descs = [eff(a) for a in allsorted[:5]]
print('정렬 상위5 발행일:', [x.isoformat()[:16] for x in descs], '| 내림차순:', descs == sorted(descs, reverse=True))
PY
```
Expected: `교집합 0`, `내림차순: True`.

- [ ] **Step 6: 브라우저 수동 확인**

Run: `cd /Users/2wodms/workspace/claude-introduction && python3 -m http.server 8767`
브라우저 `http://localhost:8767/` →
- **오늘** 탭: 오늘(달력) 발행 기사만.
- **어제** 탭: 어제(달력) 발행 기사만 — 오늘과 겹치지 않음.
- 각 탭 목록이 **발행일 최신순**(위가 최신).
- **전체** 탭: 전부, 발행일순.
확인 후 `Ctrl+C`.

- [ ] **Step 7: 커밋**

```bash
git add index.html
git commit -m "feat: 탭 발행일 기준+달력일(오늘/어제 분리)+발행일순 정렬"
```

---

### Task 2: 배포 & 검증

- [ ] **Step 1: 머지·push** — feature 브랜치 → `main` 머지 후 `git pull --rebase origin main && git push`(VM 기사 커밋과 rebase).

- [ ] **Step 2: 라이브 확인** — GitHub Pages(main root) 서빙. `https://sunkid94.github.io/gongje-monitor/` 에서 오늘/어제 분리·발행일순 확인. (Pages 캐시 지연 수 분 감안)

*(index.html 은 VM 실행과 무관 — GitHub Pages 가 main 에서 직접 서빙. VM pull 불필요.)*

---

## Self-Review 결과

- **스펙 커버리지:** effectiveDate(Task1 S1)·inPeriod 오늘 달력+어제 기존+롤링(S2)·호출부 2곳(S3·S4)·발행일 desc 정렬(S3)·검증(S5·S6) — 스펙 전 항목 대응. 어제 분기는 기존 코드에 이미 존재(재사용).
- **플레이스홀더:** 코드/명령/기대출력 실제 내용. JS 하네스 부재를 파이썬 재현 + 브라우저로 대체(플레이스홀더 아님).
- **타입 일관성:** `effectiveDate(a)` 가 S1 정의·S3·S4 사용 일치. inPeriod 오늘=`state.period === 1`(칩 data-period="1"과 일치), 어제=`'yesterday'`(기존). 정렬은 Date 뺄셈(절대시각, tz 혼재 안전).
