# 종합건설사 뉴스 한정어 필터 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종합건설사 카테고리 기사 중 건설 활동 한정어(수주·공사·현장·착공·준공·재건축)가 제목·요약에 없는 것을 수집 게이트에서 제외해, 조선·원전·주가 등 무관 뉴스 홍수를 끊는다.

**Architecture:** 회사명 검색·표시 로직은 그대로 두고(요청 증가 0), `crawler.fetch_new_articles`의 기존 게이트(is_blocked_domain/has_blocked_content) 옆에 `lacks_corp_qualifier` 필터를 추가한다. 한정어 목록은 `config.CORP_QUALIFIERS`.

**Tech Stack:** Python 3.9+, pytest. 신규 의존성 없음.

설계 스펙: `docs/superpowers/specs/2026-07-04-corp-news-qualifier-filter-design.md`

## Global Constraints

- 한정어 목록: `CORP_QUALIFIERS = ["수주", "공사", "현장", "착공", "준공", "재건축"]` (config 값, 조정 용이).
- 필터는 **종합건설사 카테고리에만** 적용. 조합 기사(is_company)·기타 카테고리는 절대 필터 안 됨.
- 한정어 판정 대상 = 기사 `title` + `description`(부분문자열 매칭).
- 검색·표시·소스 로직 무변경(포스트필터). 요청 증가 없음.

---

### Task 1: config 한정어 + crawler 게이트

**Files:**
- Modify: `config.py` (하단 상수 추가)
- Modify: `crawler.py` (import, `has_blocked_content` 옆 함수 추가, `fetch_new_articles` 게이트)
- Test: `tests/test_crawler.py` (확장)

**Interfaces:**
- Produces: `crawler.lacks_corp_qualifier(article: dict) -> bool` — 배포 정리 스크립트도 재사용.
- Consumes: `config.CORP_QUALIFIERS`, `config.CORP_CATEGORY`.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_crawler.py` 끝에 추가:

```python
import crawler


def test_lacks_corp_qualifier_drops_corp_without_qualifier():
    a = {"category": "종합건설사", "title": "삼성중공업 조선 수출 호조", "description": "방산 실적"}
    assert crawler.lacks_corp_qualifier(a) is True


def test_lacks_corp_qualifier_keeps_corp_with_qualifier():
    a = {"category": "종합건설사", "title": "대우건설 성수 재건축 수주", "description": ""}
    assert crawler.lacks_corp_qualifier(a) is False


def test_lacks_corp_qualifier_ignores_non_corp_category():
    # 조합·협회 등 다른 카테고리는 한정어 없어도 필터 대상 아님
    a = {"category": "조합·협회", "title": "기계설비건설공제조합 신규 공시", "description": ""}
    assert crawler.lacks_corp_qualifier(a) is False


def test_lacks_corp_qualifier_matches_qualifier_in_description():
    a = {"category": "종합건설사", "title": "롯데건설 소식", "description": "신규 아파트 착공 예정"}
    assert crawler.lacks_corp_qualifier(a) is False


def test_fetch_new_articles_drops_corp_without_qualifier():
    src = type("S", (), {"fetch": staticmethod(lambda seen=None: [
        {"category": "종합건설사", "title": "삼성중공업 방산 수출", "description": "", "link": "http://x/1"},
        {"category": "종합건설사", "title": "대우건설 현장 안전점검", "description": "", "link": "http://x/2"},
    ]), "__name__": "s"})
    with patch.object(crawler, "SOURCES", [src]):
        result = crawler.fetch_new_articles(set())
    links = {a["link"] for a in result}
    assert links == {"http://x/2"}   # 한정어(현장) 있는 것만 유지
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_crawler.py -k "corp_qualifier or drops_corp" -q`
Expected: FAIL — `AttributeError: module 'crawler' has no attribute 'lacks_corp_qualifier'`

- [ ] **Step 3: `config.py` 에 상수 추가** — 파일 하단(TRADE_RSS_FEEDS 아래 등)에:

```python
# 종합건설사 카테고리명 (article_store 와 동일 값 — crawler 필터가 참조)
CORP_CATEGORY = "종합건설사"

# 종합건설사 뉴스 한정어 — 이 중 하나가 제목·요약에 있어야 수집(건설 활동 뉴스만).
# 없으면 조선·방산·원전·주가·실적 등 무관 뉴스로 보고 제외. 놓치는 게 있으면 단어 추가.
CORP_QUALIFIERS = ["수주", "공사", "현장", "착공", "준공", "재건축"]
```

- [ ] **Step 4: `crawler.py` 수정** — (a) import 확장, (b) 함수 추가, (c) 게이트 삽입.

(a) 상단 import:

```python
from config import BLOCKED_DOMAINS, BLOCKED_CONTENT_KEYWORDS, CORP_CATEGORY, CORP_QUALIFIERS
```

(b) `has_blocked_content` 함수 바로 아래 추가:

```python
def lacks_corp_qualifier(article: dict) -> bool:
    """종합건설사 카테고리인데 제목·요약에 활동 한정어가 하나도 없으면 True(제외 대상).

    조합 기사·기타 카테고리는 항상 False(필터 대상 아님)."""
    if article.get("category") != CORP_CATEGORY:
        return False
    hay = (article.get("title", "") or "") + " " + (article.get("description", "") or "")
    return not any(q in hay for q in CORP_QUALIFIERS)
```

(c) `fetch_new_articles` 루프의 `has_blocked_content` 게이트 다음에 추가:

```python
            if has_blocked_content(a):
                logger.info("차단 키워드 제외: %s", (a.get("title", "") or "")[:40])
                continue
            if lacks_corp_qualifier(a):
                logger.info("종건사 한정어 없음 제외: %s", (a.get("title", "") or "")[:40])
                continue
            out.append(a)
            collected.add(link)
```

- [ ] **Step 5: 통과 확인**

Run: `python3 -m pytest tests/test_crawler.py -q`
Expected: PASS — 신규 5개 + 기존 aggregator 테스트 전부 통과

- [ ] **Step 6: 커밋**

```bash
git add config.py crawler.py tests/test_crawler.py
git commit -m "feat: 종합건설사 한정어 필터 — 활동 뉴스만 수집(조선·원전 노이즈 컷)"
```

---

### Task 2: 전체 회귀

- [ ] **Step 1: 전체 테스트 + 스모크**

Run: `python3 -m pytest -q`
Expected: 전체 통과(신규 5개 포함, 회귀 없음)

Run: `python3 -c "import main, crawler, config; print('OK')"`
Expected: `OK`

---

## 배포 & 검증 (구현·테스트 완료 후)

1. `main` 머지 → push → VM 반영(flock pull).

2. **기존 종건사 대량 정리(1회, VM flock)** — 한정어 없는 종건사 기사 제거:

```bash
ssh -i ~/.ssh/oracle_cig.key ubuntu@140.245.72.164 \
  'cd cig-monitor && flock -w 120 /tmp/cig-monitor.lock ./venv/bin/python -c "
import json, crawler
d = json.load(open(\"articles.json\"))
kept = [a for a in d if not crawler.lacks_corp_qualifier(a)]
json.dump(kept, open(\"articles.json\",\"w\"), ensure_ascii=False, indent=2)
print(f\"{len(d)} -> {len(kept)} (removed {len(d)-len(kept)})\")
"'
```
Expected: `1998 -> ~1100대 (removed ~800)` 근처(종건사 한정어 없는 것 제거).

3. **커밋·push(VM, flock)**:

```bash
ssh -i ~/.ssh/oracle_cig.key ubuntu@140.245.72.164 \
  'cd cig-monitor && flock -w 120 /tmp/cig-monitor.lock bash -c "git add articles.json && git commit -m \"chore: 종건사 한정어 없는 기사 정리\" && git pull --rebase origin main && git push origin main"'
```

4. `raw.githubusercontent.com/.../main/articles.json` 로 종합건설사 카테고리가 수백→수십으로 줄었는지 확정 검증(GitHub Pages 캐시 지연 감안).
5. 대시보드에서 종건사가 활동 뉴스만 남고 조합 신호가 드러나는지 확인.
6. 로컬 `git pull --rebase origin main` 동기화.

---

## Self-Review 결과

- **스펙 커버리지:** CORP_QUALIFIERS(Task 1 config)·lacks_corp_qualifier + 게이트(Task 1 crawler)·카테고리 한정/조합 안전(Task 1 test 3·4)·기존 대량 정리(배포 2)·검증(배포 4·5) — 스펙 전 항목 대응.
- **플레이스홀더:** 코드/명령/기대출력 실제 내용. `~1100대`·`removed ~800`은 실측 근사치 표기.
- **타입 일관성:** `lacks_corp_qualifier(article: dict) -> bool` 가 Task 1 구현·테스트·배포 정리 스크립트에서 일치. `CORP_CATEGORY`/`CORP_QUALIFIERS` config 상수명 일치. 게이트는 `has_blocked_content` 다음 삽입(기존 흐름 보존).
- **주의:** `article_store.py` 에도 동일 `CORP_CATEGORY="종합건설사"` 리터럴이 존재(중복). 이번엔 crawler 가 config 값을 참조하고 article_store 는 무변경(리스크 최소화) — 향후 article_store 도 config 참조로 통일 가능.
