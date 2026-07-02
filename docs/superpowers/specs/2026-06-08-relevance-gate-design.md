# 관련도 게이트 설계 — 조합기사 AI 관련도 판정

**작성일:** 2026-06-08
**상태:** 승인됨

---

## 개요

`is_company`(조합기사 여부, 푸시를 트리거)가 **키워드 글자 매칭만**으로 결정돼, 조직과 무관한 기사가 푸시된다.

실측: "(10) 성과급에 대한 단체교섭 대상여부에 관한 논쟁 - 기계설비신문" — 일반 노동법 칼럼. 원문 본문에 "대한기계설비건설협회"가 **한 번도 안 나오고**, 그 단어는 기계설비신문 페이지의 **사이트 메뉴·푸터·관련기사 사이드바**에만 존재. 그런데 구글이 페이지 전체를 색인 → "대한기계설비건설협회" 검색에 이 칼럼이 잡힘 → `source_google`은 키워드가 본문에 있는지 확인 없이 결과를 신뢰 → `keyword="대한기계설비건설협회"`, `is_company=True` → 푸시.

근본 원인: **"조직 이름이 글자로 언급됨" ≠ "그 조직에 관한 뉴스"** 인데 시스템이 둘을 구분 못 함. 칼럼·판례·목록·지나가는 언급·사이트 chrome 매칭까지 푸시로 샌다.

## 목표 / 비목표

**목표:** 조합기사 중 **조직과 명백히 무관한 것**을 AI가 판정해 제외(저장·이메일·푸시 어디에도 안 들어감).

**비목표:**
- 산업/종합건설사 등 **비조합 기사**(is_company=False, 어차피 푸시 안 함) — 이번 범위 밖.
- dedup 개선(박종학 부고 24회) — 별도 사안.
- 소스의 키워드 매칭 로직 변경.

**핵심 원칙 — 보수적:** **명백히 무관할 때만** 제외한다. 조금이라도 조합 관련 가능성이 있거나 AI 판단이 애매하면 **통과**(진짜 조합 뉴스 절대 안 놓침). 안전장치는 "기사 남겨두기"가 아니라 "판정을 보수적으로".

---

## 아키텍처

변경은 `enrich.py` 한 파일. enrich는 이미 새 기사마다 Claude(Haiku)를 호출해 `{summary, sentiment}`를 받는다. 그 **같은 호출**에 관련도 판정을 추가(추가 API 호출 0).

```
crawler → enrich_articles
            └─ 각 조합기사: 기존 Claude 호출 프롬프트에 "이 기사가 {조직}에 관한 뉴스인가?" 추가
               → about_org=false(명백 무관)면 그 기사를 결과에서 제외
            → (제외 안 된 기사만) → article_store / mailer / notifier
```

`main.py`·`article_store`·`notifier`·소스 무변경.

---

## 변경 파일

| 파일 | 변경 |
|------|------|
| `enrich.py` | `_ENRICH_PROMPT`에 조직 관련도 판정 추가; `enrich_article(title, description, org=None)` 시그니처; `enrich_articles`에서 `about_org=false`인 조합기사 제외 |
| `tests/test_enrich.py` | 관련도 게이트 테스트 추가 |

---

## 컴포넌트 (enrich.py)

### 프롬프트
조직(`org`)이 주어질 때만 관련도 질문과 `about_org` 필드를 포함한다. 보수적 지시:

> 이 기사가 실제로 "{org}"에 관한 뉴스인지 판단:
> - true: {org}의 활동·발표·실적·인사·사건 등을 직접 다루거나, {org}가 기사 주제에 의미 있게 관련됨
> - false: **{org}가 본문 주제와 사실상 무관한 게 명백한 경우만** (일반 칼럼/사설/법률해설, 부고종합·인사 목록의 타인 항목, 단순 나열, 본문에 등장하지 않고 사이트 메뉴·관련기사 링크로만 걸린 경우 등)
> - 애매하면 true.
> JSON에 `"about_org": true|false` 포함.

### `enrich_article(title, description, org=None) -> dict`
- `org=None`(비조합 기사): 기존과 동일 — 관련도 질문 없이 `{summary, sentiment}`.
- `org` 있음(조합 기사): 프롬프트에 관련도 질문 포함, 반환에 `about_org` 추가.
- 파싱 실패/AI 오류 폴백: 기존대로 `{summary(설명 앞부분), sentiment:neutral}` — **about_org 없음**(→ 호출측이 보수적으로 "통과" 처리).

### `enrich_articles` 변경
각 기사 루프에서:
- `org = a.get("keyword") if a.get("is_company") else None` → `enrich_article(title_clean, desc, org=org)`.
- **조합기사이고 `ai.get("about_org") is False`** → 이 기사를 enrich 결과에서 **제외**(append 안 함).
- 그 외(True / 키 없음 / 비조합) → 기존대로 포함.
- (제외는 cluster_id 부여·importance 계산 전후 어디서든 결과 리스트에서 빠지면 됨 — 제외된 기사는 downstream에 아예 안 감.)

조합기사의 `keyword`는 매칭된 조직(예: `대한기계설비건설협회`)이다(멀티소스 모두 조합기사는 매칭 키워드를 keyword로 설정).

---

## 데이터 흐름 / 영향

- 제외된 기사: `enrich_articles` 출력에 없음 → `main.py`의 `add_articles`/`send_email`/`send_company_push` 어디에도 안 들어감. articles.json·이메일·푸시·웹 전부 미노출.
- `seen` 처리: `main.py`는 enrich **후** `save_seen(seen | new_urls)`로 enrich된 기사 URL을 seen에 넣는다. 제외된 기사의 URL은 enrich 출력에 없으므로 seen에 안 들어가 **다음 런에 또 크롤·판정될 수 있다**(매 런 같은 칼럼에 Claude 1회). 비용 미미하나, `main.py`가 seen 갱신에 쓰는 집합 확인 필요(현재 `new_urls = {a["link"] for a in enriched}` — enriched에서 빠지면 seen 미포함). → **보수적 수용**: 재판정돼도 매번 false로 제외되어 푸시는 안 감. (원하면 후속에서 제외분도 seen에 넣어 재판정 방지 가능 — 이번 범위 밖.)

---

## 엣지 케이스

- `about_org` 필드 없음(구버전 응답/폴백) → 제외 안 함(통과). 보수적.
- AI가 false를 줬는데 사실은 관련 기사였던 경우(오판) → 그 기사 누락. 이를 막기 위해 프롬프트가 **"애매하면 true"**를 강제. 임계값 보수성으로 위험 최소화.
- 조합기사인데 `keyword`가 비어있음(이론상) → org=None → 관련도 질문 없이 통과.

---

## 테스트 (TDD)

`tests/test_enrich.py`:
1. **무관 칼럼 제외** — 조합기사(is_company=True, keyword="대한기계설비건설협회") + Claude가 `about_org=false` 반환(목) → `enrich_articles` 결과에 그 기사 없음.
2. **관련 기사 통과** — 같은 조건 + `about_org=true` → 결과에 포함, is_company 유지.
3. **about_org 누락 시 통과(보수적)** — Claude 응답에 about_org 없음 → 포함.
4. **AI 오류 폴백 시 통과** — Claude 예외 → 폴백 + 기사 포함.
5. **비조합 기사엔 관련도 질문 안 함** — is_company=False 기사 → `enrich_article` org 인자 None(또는 about_org 미요청), 기사 포함.
6. `enrich_article(org=...)` 단위: org 있을 때 프롬프트에 조직명 포함·about_org 파싱.

---

## 배포

`main` 머지 → VM cron 자동 반영. 머지 후 `monitor.log`에서 무관 조합기사 제외가 일어나는지(예: 동일 칼럼이 더는 저장/푸시 안 됨) + 진짜 조합 뉴스는 정상 푸시되는지 확인.

---

## 예상 효과

"대한기계설비건설협회"가 사이드바에만 있던 노동법 칼럼 → enrich AI가 "본문 주제와 무관" 명백 판정 → 제외 → **푸시·웹·이메일 어디에도 안 뜸.** 진짜 조합 뉴스는 보수적 판정으로 그대로 통과.

---
> 📑 관련 문서 전체 지도: [CIG 이슈 모니터 문서 인덱스](../CIG-MONITOR-INDEX.md)
