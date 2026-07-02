# 관련도 게이트 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 조합기사(is_company) 중 조직과 명백히 무관한 기사를 enrich 단계의 AI 판정으로 제외해, 무관한 알림(예: 사이트 chrome에만 조직명이 있는 노동법 칼럼)이 푸시되지 않게 한다.

**Architecture:** `enrich.py` 한 파일만 변경. enrich는 이미 새 기사마다 Claude(Haiku)를 호출하므로, 그 프롬프트에 `about_org` 판정을 추가(추가 API 호출 0). 조합기사이고 AI가 `about_org=false`(명백 무관)라고 한 것만 `enrich_articles` 출력에서 제외한다. 보수적: 애매/누락/AI오류면 통과.

**Tech Stack:** Python 3.10+, anthropic SDK(기존), pytest 8.3.4.

설계 스펙: `docs/superpowers/specs/2026-06-08-relevance-gate-design.md`
대상: `enrich.py`(현재 `_ENRICH_PROMPT`, `enrich_article(title, description)`, `enrich_articles`), `tests/test_enrich.py`

---

## File Structure

| 파일 | 변경 |
|------|------|
| `enrich.py` | `_RELEVANCE_CRITERIA`/`_RELEVANCE_FIELD` 상수 추가; `_ENRICH_PROMPT`에 삽입점 추가; `enrich_article(title, description, org=None)`; `enrich_articles`에서 `about_org=false` 조합기사 제외 |
| `tests/test_enrich.py` | enrich_article(org) + enrich_articles 제외 테스트 추가 |

**계약:** `enrich_article(title, description, org=None) -> dict` — 항상 `{summary, sentiment}`, `org`가 있고 응답에 about_org가 있으면 `about_org: bool` 추가. `org=None`이면 about_org 없음(기존과 동일).

---

### Task 1: `enrich_article`에 조직 관련도 판정 추가

**Files:**
- Modify: `enrich.py`
- Test: `tests/test_enrich.py`

- [ ] **Step 1: 실패 테스트 작성** (`tests/test_enrich.py` 끝에 추가)

```python
def test_enrich_article_returns_about_org_when_org_given():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "neutral", "about_org": false}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("성과급 칼럼", "노동법 해설", org="대한기계설비건설협회")
    assert result["about_org"] is False
    # 프롬프트에 조직명이 들어갔는지
    sent_prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "대한기계설비건설협회" in sent_prompt


def test_enrich_article_about_org_true():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "positive", "about_org": true}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("조합 수주", "내용", org="건설공제조합")
    assert result["about_org"] is True


def test_enrich_article_no_org_omits_about_org_and_question():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "neutral"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용")   # org 없음
    assert "about_org" not in result
    sent_prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "about_org" not in sent_prompt


def test_enrich_article_org_given_but_field_missing_omits_about_org():
    # 응답에 about_org 없음 → 결과에도 없음(호출측이 보수적으로 통과 처리)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약", "sentiment": "neutral"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용", org="건설공제조합")
    assert "about_org" not in result
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_enrich.py -k "about_org or no_org_omits" -v`
Expected: FAIL — `enrich_article() got an unexpected keyword argument 'org'`

- [ ] **Step 3: 구현** — `enrich.py` 수정.

(a) 기존 `_ENRICH_PROMPT`(아래)를 찾아 교체:
```python
_ENRICH_PROMPT = """다음 뉴스 기사를 분석해 JSON으로 답하세요.

제목: {title}
내용: {description}

판단 기준:
- 감정 톤은 "건설업계 전반과 기계설비건설공제조합" 시점에서 평가합니다.
  · positive: 업계 호재 (수주 증가, 규제 완화, 시장 확대 등)
  · negative: 업계 악재 (사고, 규제 강화, PF 위기, 부정 이슈 등)
  · neutral: 사실 보도, 양면적, 판단 어려움
- 요약은 한국어 2~3줄, 핵심만.

JSON 형식 (다른 텍스트 없이 이것만):
{{"summary": "...", "sentiment": "positive|neutral|negative"}}"""
```
교체 후:
```python
_RELEVANCE_CRITERIA = """
- about_org: 이 기사가 실제로 "{org}"에 관한 뉴스인지 판단.
  · true: "{org}"의 활동·발표·실적·인사·사건 등을 직접 다루거나, "{org}"가 기사 주제에 의미 있게 관련됨
  · false: "{org}"가 본문 주제와 사실상 무관한 게 명백한 경우만 (일반 칼럼·법률해설·사설, 부고종합/인사 목록의 타인 항목, 단순 나열, 본문에 등장하지 않고 사이트 메뉴·관련기사 링크로만 걸린 경우 등). 애매하면 true."""

_RELEVANCE_FIELD = ', "about_org": true|false'

_ENRICH_PROMPT = """다음 뉴스 기사를 분석해 JSON으로 답하세요.

제목: {title}
내용: {description}

판단 기준:
- 감정 톤은 "건설업계 전반과 기계설비건설공제조합" 시점에서 평가합니다.
  · positive: 업계 호재 (수주 증가, 규제 완화, 시장 확대 등)
  · negative: 업계 악재 (사고, 규제 강화, PF 위기, 부정 이슈 등)
  · neutral: 사실 보도, 양면적, 판단 어려움
- 요약은 한국어 2~3줄, 핵심만.{relevance_criteria}

JSON 형식 (다른 텍스트 없이 이것만):
{{"summary": "...", "sentiment": "positive|neutral|negative"{relevance_field}}}"""
```

(b) 기존 `enrich_article`(아래)을 찾아 교체:
```python
def enrich_article(title: str, description: str) -> dict:
    fallback = {
        "summary": (description or "")[:200],
        "sentiment": "neutral",
    }
    try:
        msg = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": _ENRICH_PROMPT.format(title=title, description=description)}],
        )
        raw = _strip_code_fence(msg.content[0].text)
        data = json.loads(raw)
        sentiment = data.get("sentiment", "neutral")
        if sentiment not in _VALID_SENTIMENTS:
            sentiment = "neutral"
        return {
            "summary": data.get("summary", "").strip() or fallback["summary"],
            "sentiment": sentiment,
        }
    except Exception as e:
        logger.warning("enrich_article 폴백 (title=%s): %s", title[:30], e)
        return fallback
```
교체 후:
```python
def enrich_article(title: str, description: str, org: Optional[str] = None) -> dict:
    fallback = {
        "summary": (description or "")[:200],
        "sentiment": "neutral",
    }
    relevance_criteria = _RELEVANCE_CRITERIA.format(org=org) if org else ""
    relevance_field = _RELEVANCE_FIELD if org else ""
    prompt = _ENRICH_PROMPT.format(
        title=title, description=description,
        relevance_criteria=relevance_criteria, relevance_field=relevance_field,
    )
    try:
        msg = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _strip_code_fence(msg.content[0].text)
        data = json.loads(raw)
        sentiment = data.get("sentiment", "neutral")
        if sentiment not in _VALID_SENTIMENTS:
            sentiment = "neutral"
        result = {
            "summary": data.get("summary", "").strip() or fallback["summary"],
            "sentiment": sentiment,
        }
        if org and "about_org" in data:
            result["about_org"] = bool(data["about_org"])
        return result
    except Exception as e:
        logger.warning("enrich_article 폴백 (title=%s): %s", title[:30], e)
        return fallback
```
(`Optional`은 이미 `from typing import Optional`로 임포트돼 있음.)

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest tests/test_enrich.py -v`
Expected: 신규 4개 + 기존 enrich_article 테스트 전부 PASS(기존은 org 없이 호출 → about_org 없음, 기존 동작 보존).

- [ ] **Step 5: 커밋**

```bash
git add enrich.py tests/test_enrich.py
git commit -m "feat: enrich_article에 조직 관련도(about_org) 판정 추가"
```

---

### Task 2: `enrich_articles`에서 무관 조합기사 제외

**Files:**
- Modify: `enrich.py` (`enrich_articles` 루프)
- Test: `tests/test_enrich.py`

- [ ] **Step 1: 실패 테스트 작성** (`tests/test_enrich.py` 끝에 추가)

```python
def _mock_text(payload):
    return MagicMock(content=[MagicMock(text=payload)])


def test_enrich_articles_excludes_irrelevant_company_article():
    # 조합기사인데 AI가 about_org=false → 결과에서 제외
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_text('{"summary": "s", "sentiment": "neutral", "about_org": false}')
    articles = [{"title": "성과급 단체교섭 칼럼 - 기계설비신문", "description": "노동법 해설",
                 "link": "http://x/1", "keyword": "대한기계설비건설협회",
                 "category": "조합·협회", "is_company": True}]
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_articles
        result = enrich_articles(articles)
    assert result == []


def test_enrich_articles_keeps_relevant_company_article():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_text('{"summary": "s", "sentiment": "positive", "about_org": true}')
    articles = [{"title": "전문건설공제조합 피치 A+ 유지 - 이데일리", "description": "신용등급",
                 "link": "http://x/2", "keyword": "전문건설공제조합",
                 "category": "조합·협회", "is_company": True}]
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_articles
        result = enrich_articles(articles)
    assert len(result) == 1
    assert result[0]["is_company"] is True


def test_enrich_articles_keeps_when_about_org_missing():
    # about_org 없음(보수적 통과)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_text('{"summary": "s", "sentiment": "neutral"}')
    articles = [{"title": "조합 관련 - 매체", "description": "내용", "link": "http://x/3",
                 "keyword": "건설공제조합", "category": "조합·협회", "is_company": True}]
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_articles
        result = enrich_articles(articles)
    assert len(result) == 1


def test_enrich_articles_keeps_on_api_error():
    # AI 오류 → 폴백, about_org 없음 → 통과(보수적)
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("down")
    articles = [{"title": "조합 관련 - 매체", "description": "내용", "link": "http://x/4",
                 "keyword": "건설공제조합", "category": "조합·협회", "is_company": True}]
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_articles
        result = enrich_articles(articles)
    assert len(result) == 1


def test_enrich_articles_non_company_not_relevance_filtered():
    # 비조합 기사: about_org=false 응답이 와도 제외 안 함(애초에 org 안 물음)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_text('{"summary": "s", "sentiment": "neutral", "about_org": false}')
    articles = [{"title": "삼성중공업 수주 - 매체", "description": "내용", "link": "http://x/5",
                 "keyword": "삼성중공업", "category": "종합건설사", "is_company": False}]
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_articles
        result = enrich_articles(articles)
    assert len(result) == 1
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_enrich.py -k "excludes_irrelevant or keeps_relevant_company or keeps_when_about_org or keeps_on_api_error or non_company_not_relevance" -v`
Expected: `test_enrich_articles_excludes_irrelevant_company_article` FAIL (제외 로직 없어 1건 반환). 나머지는 우연히 통과 가능.

- [ ] **Step 3: 구현** — `enrich.py`의 `enrich_articles` 루프 본문 교체.

기존:
```python
    for a in clustered:
        title = a["title"]
        publisher = extract_publisher(title)
        title_clean = _PUBLISHER_SUFFIX_RE.sub("", title)
        ai = enrich_article(title_clean, a.get("description", ""))
        out = {
            **a,
            "publisher": publisher,
            "title_clean": title_clean,
            "summary": ai["summary"],
            "sentiment": ai["sentiment"],
            # collected_at 가짜 세팅 — calc_importance 의 24h 가산점 활성화용.
            # article_store.add_articles 가 나중에 진짜 시각으로 덮어쓰지만 importance 는 유지.
            "collected_at": a.get("collected_at") or now_str,
        }
        out["importance"] = calc_importance(out, cluster_sizes[a["cluster_id"]], now=now)
        enriched.append(out)
```
교체 후:
```python
    for a in clustered:
        title = a["title"]
        publisher = extract_publisher(title)
        title_clean = _PUBLISHER_SUFFIX_RE.sub("", title)
        org = a.get("keyword") if a.get("is_company") else None
        ai = enrich_article(title_clean, a.get("description", ""), org=org)
        # 조합기사인데 조직과 명백히 무관(about_org=false) → 제외 (보수적: 애매/누락은 통과)
        if a.get("is_company") and ai.get("about_org") is False:
            logger.info("관련도 게이트 제외 (조직=%s): %s", org, title_clean[:40])
            continue
        out = {
            **a,
            "publisher": publisher,
            "title_clean": title_clean,
            "summary": ai["summary"],
            "sentiment": ai["sentiment"],
            # collected_at 가짜 세팅 — calc_importance 의 24h 가산점 활성화용.
            # article_store.add_articles 가 나중에 진짜 시각으로 덮어쓰지만 importance 는 유지.
            "collected_at": a.get("collected_at") or now_str,
        }
        out["importance"] = calc_importance(out, cluster_sizes[a["cluster_id"]], now=now)
        enriched.append(out)
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest tests/test_enrich.py -v`
Expected: 신규 5개 + Task 1의 4개 + 기존 전부 PASS. 그다음 전체:

Run: `python3 -m pytest -q`
Expected: 전체 그린(회귀 없음). 기존 `test_enrich_articles_full_pipeline` 등은 입력 기사에 `is_company` 키가 없거나 about_org 없는 응답이라 제외 안 됨 → 그대로 통과.

- [ ] **Step 5: 커밋**

```bash
git add enrich.py tests/test_enrich.py
git commit -m "feat: enrich_articles에서 조직 무관 조합기사 제외(관련도 게이트)"
```

---

## Self-Review 결과

- **스펙 커버리지:** 프롬프트 about_org 추가(Task 1) ↔ 스펙 "프롬프트"; `enrich_article(org=)`(Task 1) ↔ "컴포넌트"; `enrich_articles` 제외(Task 2) ↔ "enrich_articles 변경"; 보수적(애매/누락/오류 통과)(Task 1·2 테스트) ↔ "핵심 원칙"; 비조합 미적용(Task 2) ↔ "비목표". 테스트 6종 스펙 1~6 대응.
- **플레이스홀더:** 없음 — 모든 코드/테스트 실제 내용.
- **타입 일관성:** `enrich_article(title, description, org=None)`·반환 `{summary, sentiment[, about_org]}`·`enrich_articles` 제외 조건 `ai.get("about_org") is False` 일치. `_RELEVANCE_CRITERIA`/`_RELEVANCE_FIELD`/`_ENRICH_PROMPT` 삽입점 이름 일치. 기존 enrich_article 무인자 호출 호환(org 기본 None).
- **주의:** 기존 `test_enrich_articles_full_pipeline`/`preserves_original_fields`/`importance_boost`가 `is_company`를 안 넣거나 about_org 없는 mock을 쓰면 제외 안 됨 — 구현 시 이 기존 테스트들이 깨지지 않는지 확인(깨지면 그 테스트의 입력에 is_company 유무를 점검).

---
> 📑 관련 문서 전체 지도: [CIG 이슈 모니터 문서 인덱스](../CIG-MONITOR-INDEX.md)
