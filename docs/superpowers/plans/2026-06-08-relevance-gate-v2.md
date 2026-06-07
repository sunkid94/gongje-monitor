# 관련도 게이트 v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관련도 게이트가 "매칭된 키워드 하나"가 아니라 "추적 조직 전체(별칭 포함) 중 하나라도에 관한 뉴스인가"를 판정하게 바꿔, K-FINCO·협회 같은 진짜 조합 뉴스를 떨구지 않게 한다.

**Architecture:** `config.py`에 영문 브랜드 별칭(`COMPANY_ALIASES`)을 추가하고, `enrich.py`가 `COMPANY_KEYWORDS`+별칭으로 추적 조직 참조 문자열(`_TRACKED_ORGS`)을 1회 빌드한다. `enrich_article`의 단일 `org` 파라미터를 목록 `orgs`로 바꾸고, 프롬프트가 그 목록 기준으로 묻는다. `enrich_articles`는 조합기사에 매칭 키워드 대신 전체 목록을 전달한다. 보수적 동작(애매/누락/AI오류 통과)은 v1 유지.

**Tech Stack:** Python 3.10+, anthropic SDK(기존), pytest 8.3.4.

설계 스펙: `docs/superpowers/specs/2026-06-08-relevance-gate-v2-design.md`
대상: `config.py`, `enrich.py`(게이트 v1: `_RELEVANCE_CRITERIA`/`enrich_article(title, description, org=None)`/`enrich_articles`), `tests/test_enrich.py`

---

## File Structure

| 파일 | 변경 |
|------|------|
| `config.py` | `COMPANY_ALIASES` dict 추가 |
| `enrich.py` | `from config import COMPANY_KEYWORDS, COMPANY_ALIASES`; `_TRACKED_ORGS` 빌더; `_RELEVANCE_CRITERIA`를 목록 기준으로; `enrich_article(title, description, orgs=None)`; `enrich_articles`가 `_TRACKED_ORGS` 전달 |
| `tests/test_enrich.py` | enrich_article 테스트 `org`→`orgs` 갱신 + 목록/별칭 포함 검증; enrich_articles가 전체 목록 사용 검증 |

**계약:** `enrich_article(title, description, orgs=None) -> dict` — `orgs`(추적 조직 참조 문자열)가 있으면 프롬프트에 목록 포함 + `about_org` 반환. `None`이면 v1 비조합과 동일.

---

### Task 1: config 별칭 + enrich_article 목록 기준 판정

**Files:**
- Modify: `config.py`, `enrich.py`
- Test: `tests/test_enrich.py`

- [ ] **Step 1: `config.py`에 별칭 추가** — `COMPANY_KEYWORDS` 정의 아래(파일의 키워드 영역)에 추가:

```python
# 영문/특수 브랜드 별칭 — AI가 모를 수 있는 것만 (한글 약칭은 AI가 인식)
COMPANY_ALIASES = {
    "전문건설공제조합": ["K-FINCO"],
    "기계설비건설공제조합": ["CIG"],   # 우리 조합
}
```

- [ ] **Step 2: enrich_article 테스트를 v2(`orgs`)로 갱신 + 추가.** `tests/test_enrich.py`에서 아래 5개 기존 테스트를 찾아 `org=`→`orgs=`로 바꾼다(본문 전체 교체).

기존 `test_enrich_article_returns_about_org_when_org_given` → 교체:
```python
def test_enrich_article_returns_about_org_when_orgs_given():
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "neutral", "about_org": false}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("성과급 칼럼", "노동법 해설", orgs=enrich._TRACKED_ORGS)
    assert result["about_org"] is False
    sent_prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    # 프롬프트에 추적 조직 전체 + 영문 별칭이 들어감
    assert "전문건설공제조합" in sent_prompt
    assert "K-FINCO" in sent_prompt
    assert "대한기계설비건설협회" in sent_prompt
    assert "CIG" in sent_prompt
```

기존 `test_enrich_article_about_org_true` → 교체:
```python
def test_enrich_article_about_org_true():
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "positive", "about_org": true}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("조합 수주", "내용", orgs=enrich._TRACKED_ORGS)
    assert result["about_org"] is True
```

기존 `test_enrich_article_no_org_omits_about_org_and_question` → 교체(이름·동작 동일, orgs 없음):
```python
def test_enrich_article_no_orgs_omits_about_org_and_question():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "neutral"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용")   # orgs 없음
    assert "about_org" not in result
    sent_prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "about_org" not in sent_prompt
```

기존 `test_enrich_article_org_given_but_field_missing_omits_about_org` → 교체:
```python
def test_enrich_article_orgs_given_but_field_missing_omits_about_org():
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "neutral"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용", orgs=enrich._TRACKED_ORGS)
    assert "about_org" not in result
```

기존 `test_enrich_article_about_org_string_false_treated_as_drop` 와 `..._string_true_treated_as_keep` → 두 함수의 `org="건설공제조합"`을 `orgs=enrich._TRACKED_ORGS`로 바꾸고 함수 상단에 `import enrich` 추가(나머지 동일). 교체본:
```python
def test_enrich_article_about_org_string_false_treated_as_drop():
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "neutral", "about_org": "false"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용", orgs=enrich._TRACKED_ORGS)
    assert result["about_org"] is False


def test_enrich_article_about_org_string_true_treated_as_keep():
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "neutral", "about_org": "true"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용", orgs=enrich._TRACKED_ORGS)
    assert result["about_org"] is True
```

- [ ] **Step 3: 실패 확인**

Run: `python3 -m pytest tests/test_enrich.py -k "orgs or about_org" -v`
Expected: FAIL — `module 'enrich' has no attribute '_TRACKED_ORGS'` / `unexpected keyword argument 'orgs'`

- [ ] **Step 4: `enrich.py` 구현.**

(a) 임포트 추가 — 기존 `from article_store import format_collected_at, parse_collected_at` 아래에:
```python
from config import COMPANY_KEYWORDS, COMPANY_ALIASES
```

(b) `_TRACKED_ORGS` 빌더 추가 — `_VALID_SENTIMENTS = ...` 줄 아래(상수 영역)에:
```python
def _build_tracked_orgs() -> str:
    parts = []
    for org in COMPANY_KEYWORDS:
        aliases = COMPANY_ALIASES.get(org)
        parts.append(f"{org}(={'/'.join(aliases)})" if aliases else org)
    return ", ".join(parts)


_TRACKED_ORGS = _build_tracked_orgs()
```

(c) `_RELEVANCE_CRITERIA` 교체(단일 org → 목록 orgs):
```python
_RELEVANCE_CRITERIA = """
- about_org: 이 기사가 다음 조직 중 하나라도에 관한 뉴스인지 판단: {orgs}
  · true: 목록 중 한 곳의 활동·발표·실적·인사·사건 등을 직접 다루거나 의미 있게 관련됨 (별칭 포함 — 예: K-FINCO=전문건설공제조합)
  · false: 목록의 어느 조직과도 무관한 게 명백한 경우만 (일반 칼럼·법률해설·사설, 무관한 부고종합/인사 목록, 단순 벤더·타기관 뉴스, 본문에 등장하지 않고 사이트 메뉴·관련기사 링크로만 걸린 경우 등). 애매하면 true."""
```

(d) `enrich_article` 시그니처·본문에서 `org`→`orgs`:
- `def enrich_article(title: str, description: str, org: Optional[str] = None) -> dict:` → `def enrich_article(title: str, description: str, orgs: Optional[str] = None) -> dict:`
- `relevance_criteria = _RELEVANCE_CRITERIA.format(org=org) if org else ""` → `relevance_criteria = _RELEVANCE_CRITERIA.format(orgs=orgs) if orgs else ""`
- `relevance_field = _RELEVANCE_FIELD if org else ""` → `relevance_field = _RELEVANCE_FIELD if orgs else ""`
- `if org and "about_org" in data:` → `if orgs and "about_org" in data:`
(string-safe 파싱 블록 내부는 그대로.)

- [ ] **Step 5: 통과 확인**

Run: `python3 -m pytest tests/test_enrich.py -v`
Expected: 갱신된 enrich_article 테스트 + 기존 전부 PASS. 그다음 전체 `python3 -m pytest -q` → green(enrich_articles는 아직 단일 keyword를 쓰지만 Task 2 전까지 `org`→`orgs` 호출부 미변경이라 깨질 수 있음 — 아래 주의).

**주의:** 이 시점에서 `enrich_articles`는 아직 `enrich_article(..., org=org)`로 호출한다 → `org`는 더 이상 유효 인자가 아니므로 `TypeError`. 따라서 Task 1 Step 5의 전체 스위트는 enrich_articles 테스트에서 실패할 수 있다. **Task 1에서는 enrich_article 단위 테스트(`-k "orgs or about_org"`)만 통과시키고**, enrich_articles 호출부는 Task 2에서 고친다. (커밋은 enrich_article 단위 그린 기준.)

- [ ] **Step 6: 커밋**

```bash
git add config.py enrich.py tests/test_enrich.py
git commit -m "feat: 관련도 게이트 v2 — enrich_article을 추적 조직 전체(별칭) 기준으로"
```

---

### Task 2: enrich_articles가 전체 목록으로 판정

**Files:**
- Modify: `enrich.py` (`enrich_articles` 루프)
- Test: `tests/test_enrich.py`

- [ ] **Step 1: 검증 테스트 추가** (`tests/test_enrich.py` 끝에)

```python
def test_enrich_articles_gate_uses_full_org_list_not_keyword():
    # 조합기사 판정 시 매칭 키워드 하나가 아니라 추적 조직 전체(별칭 포함)가 프롬프트에 들어가야 함
    import enrich
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "s", "sentiment": "neutral", "about_org": true}')]
    )
    # keyword 는 "엉뚱한" 조합인데도, 게이트는 전체 목록으로 물어야 함
    articles = [{"title": "대한기계설비건설협회, 직접발주 법제화 추진 - 매체", "description": "협회 활동",
                 "link": "http://x/협회", "keyword": "기계설비건설공제조합",
                 "category": "조합·협회", "is_company": True}]
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_articles
        result = enrich_articles(articles)
    assert len(result) == 1   # 협회 뉴스 → 통과
    sent_prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "대한기계설비건설협회" in sent_prompt   # 전체 목록 포함
    assert "K-FINCO" in sent_prompt               # 별칭 포함
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_enrich.py::test_enrich_articles_gate_uses_full_org_list_not_keyword -v`
Expected: FAIL — `enrich_articles`가 아직 `org=a["keyword"]`(단일)로 호출 → `TypeError: unexpected keyword argument 'org'` 또는 프롬프트에 별칭 없음.

- [ ] **Step 3: `enrich_articles` 루프 수정.** 기존:
```python
        org = a.get("keyword") if a.get("is_company") else None
        ai = enrich_article(title_clean, a.get("description", ""), org=org)
        # 조합기사인데 조직과 명백히 무관(about_org=false) → 제외 (보수적: 애매/누락은 통과)
        if a.get("is_company") and ai.get("about_org") is False:
            logger.info("관련도 게이트 제외 (조직=%s): %s", org, title_clean[:40])
            continue
```
교체:
```python
        orgs = _TRACKED_ORGS if a.get("is_company") else None
        ai = enrich_article(title_clean, a.get("description", ""), orgs=orgs)
        # 조합기사인데 추적 조직 어디와도 명백히 무관(about_org=false) → 제외 (보수적: 애매/누락은 통과)
        if a.get("is_company") and ai.get("about_org") is False:
            logger.info("관련도 게이트 제외: %s", title_clean[:40])
            continue
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest tests/test_enrich.py -v`
Expected: 신규 테스트 + 기존 enrich_articles 테스트(excludes/keeps 류) + 전부 PASS. 그다음 전체:

Run: `python3 -m pytest -q`
Expected: 전체 green(회귀 없음).

- [ ] **Step 5: 임포트 스모크 + 커밋**

Run: `python3 -c "import main, enrich, config; print(enrich._TRACKED_ORGS)"`
Expected: `전문건설공제조합(=K-FINCO), 기계설비건설공제조합(=CIG), 엔지니어링공제조합, 건설공제조합, 대한기계설비건설협회`

```bash
git add enrich.py tests/test_enrich.py
git commit -m "feat: enrich_articles 관련도 게이트를 추적 조직 전체 기준으로 전환"
```

---

## Self-Review 결과

- **스펙 커버리지:** COMPANY_ALIASES(Task 1)↔스펙 "config.py"; _TRACKED_ORGS 빌더+프롬프트 목록화(Task 1)↔"컴포넌트"; enrich_article(orgs)(Task 1)↔"enrich_article"; enrich_articles 전체목록(Task 2)↔"enrich_articles"; 보수적 유지(string-safe·누락·오류 통과)↔"원칙". 테스트 1~6 대응. 후속(청소 dry-run 재실행)은 배포 후 운영 절차(코드 아님).
- **플레이스홀더:** 없음 — 모든 코드/테스트 실제 내용.
- **타입 일관성:** `enrich_article(title, description, orgs=None)`·`_TRACKED_ORGS:str`·`_RELEVANCE_CRITERIA.format(orgs=)`·enrich_articles `orgs=_TRACKED_ORGS` 일치. v1의 `org` 잔재 없음(전부 `orgs`로 교체).
- **주의(Task 1 중간 상태):** Task 1 후 enrich_articles는 아직 `org=` 호출이라 전체 스위트가 빨갛다 — 의도된 전환 중 상태(Task 2에서 녹색). Task 1 커밋은 enrich_article 단위 테스트 그린 기준.
