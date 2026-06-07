# 관련도 게이트 v2 설계 — 추적 조직 전체(별칭 포함) 기준

**작성일:** 2026-06-08
**상태:** 승인됨

---

## 개요

관련도 게이트 v1(2026-06-08 배포)은 `is_company` 기사를 **매칭된 키워드 하나**에 대해 "이게 거기에 관한 뉴스냐?"고 AI에 물었다. 일회성 청소 dry-run에서 **진짜 조합/협회 뉴스를 무관으로 잘못 판정(false positive)** 하는 게 드러났다:

- **"K-FINCO, 피치 신용등급 'A+' 유지"** → `org=전문건설공제조합`으로 물으니 AI가 "K-FINCO ≠ 전문건설공제조합"으로 보고 무관 판정. (K-FINCO가 전문건설공제조합의 영문 브랜드인 걸 모름)
- **"대한기계설비건설협회, 직접 발주 법제화 추진"** → *조합*(기계설비건설공제조합) 키워드에 걸려, AI에 "이게 *조합* 뉴스냐?"고 물음 → "아니, *협회* 얘기" → 무관 판정. (협회도 추적 대상인데 엉뚱한 키워드로 판정)

이 결함은 청소뿐 아니라 **운영 게이트도 진짜 뉴스를 떨구고 있다**는 뜻이다(앞으로 K-FINCO·협회 뉴스가 막힘).

근본 원인: **"매칭된 키워드 하나" 기준 판정** — 브랜드 별칭과 키워드 교차매칭(협회↔조합)에 취약.

## 목표 / 비목표

**목표:** 게이트 질문을 **"추적 조직들 중 *어느 하나라도*에 관한 뉴스인가?"**(별칭 포함)로 바꿔, 진짜 조합/협회 뉴스를 안 떨구게 한다.

**비목표:**
- dedup(박종학 부고 중복 푸시) — 별도 사안.
- 기존 무관 기사 청소 — 이 수정 *후에* 별도로 실행(게이트 로직 재사용).
- 소스 키워드 매칭 변경.

**원칙(v1 유지):** 보수적 — **어느 조직과도 무관한 게 명백할 때만** 제외. 애매/누락/AI오류는 통과(진짜 뉴스 안 놓침).

---

## 아키텍처

`enrich.py` + `config.py`만 변경. v1과 동일하게 기존 Claude(Haiku) 호출에 판정을 얹는다(추가 호출 0). 차이는 **단일 org 대신 추적 조직 전체 목록(별칭 포함)** 으로 묻는 것.

```
config: COMPANY_KEYWORDS(추적 조직) + COMPANY_ALIASES(영문 브랜드)
enrich: 목록 → 프롬프트 "다음 중 하나라도에 관한 뉴스인가?" → about_org
enrich_articles: 조합기사면 이 목록으로 판정(매칭 키워드 아님)
```

`main.py`·소스·notifier 무변경.

---

## 변경 파일

| 파일 | 변경 |
|------|------|
| `config.py` | `COMPANY_ALIASES = {"전문건설공제조합": ["K-FINCO"], "기계설비건설공제조합": ["CIG"]}` 추가 |
| `enrich.py` | 추적 조직 참조 문자열 빌더 + `_RELEVANCE_CRITERIA`를 목록 기준으로; `enrich_article(title, description, orgs=None)`(단일 `org`→목록 `orgs`); `enrich_articles`가 조합기사에 전체 목록 전달 |
| `tests/test_enrich.py` | v2에 맞춰 갱신(목록·별칭 프롬프트 포함, 단일 키워드 미사용) |

---

## 컴포넌트 (enrich.py)

### 추적 조직 참조 문자열
`config.COMPANY_KEYWORDS` + `config.COMPANY_ALIASES`로 빌드. 별칭 있는 곳은 표기:
> `전문건설공제조합(=K-FINCO), 기계설비건설공제조합(=CIG), 엔지니어링공제조합, 건설공제조합, 대한기계설비건설협회`

모듈 로드 시 1회 계산(`_TRACKED_ORGS`).
(한글 약칭 "기계설비협회"·"기계설비건설협회" 등은 AI가 full name으로 인식하므로 별칭 불필요. 영문 브랜드만 명시.)

### 프롬프트 (`_RELEVANCE_CRITERIA`)
> - about_org: 이 기사가 다음 조직 **중 하나라도**에 관한 뉴스인지 판단: {orgs}
>   · true: 목록 중 한 곳의 활동·발표·실적·인사·사건 등을 직접 다루거나 의미 있게 관련됨 (별칭 포함 — 예: K-FINCO=전문건설공제조합)
>   · false: 목록의 **어느 조직과도** 무관한 게 명백한 경우만 (일반 칼럼·법률해설·사설, 무관한 부고종합/인사 목록, 단순 벤더·타기관 뉴스, 본문에 없고 사이트 메뉴·관련기사 링크로만 걸린 경우 등). 애매하면 true.

### `enrich_article(title, description, orgs=None) -> dict`
- `orgs=None`(비조합): v1과 동일 — 관련도 질문 없이 `{summary, sentiment}`.
- `orgs` 있음(조합): 프롬프트에 목록 포함, `about_org`(bool) 반환. 문자열 응답 안전 처리(v1 유지).
- 폴백(AI 오류): `{summary, sentiment}`만, about_org 없음 → 호출측 보수적 통과.

### `enrich_articles`
- `orgs = _TRACKED_ORGS if a.get("is_company") else None` → `enrich_article(title_clean, desc, orgs=orgs)`.
- `a.get("is_company") and ai.get("about_org") is False` → 제외(v1과 동일).
- **매칭 키워드(`a["keyword"]`)는 더 이상 게이트에 안 씀.**

---

## 엣지 케이스

- 브랜드 별칭: K-FINCO/CIG가 프롬프트에 명시돼 AI가 해당 조합으로 인식 → 통과.
- 키워드 교차매칭: 협회 기사가 조합 키워드에 걸려도, 목록에 협회가 있으니 통과.
- 별칭 목록에 없는 신규 브랜드: AI가 모르면 무관 판정 위험 → 발견 시 `COMPANY_ALIASES`에 추가(설정만). 보수적 원칙상 애매하면 true라 위험 최소.
- about_org 누락/문자열/AI오류 → v1과 동일 보수적 통과.

---

## 테스트 (TDD)

`tests/test_enrich.py`(v1 테스트를 v2 시그니처로 갱신 + 추가):
1. **프롬프트에 전체 목록+별칭 포함** — `enrich_article(orgs=_TRACKED_ORGS)` 호출 시 프롬프트에 `전문건설공제조합`·`K-FINCO`·`대한기계설비건설협회`·`CIG` 모두 등장.
2. **about_org=false → about_org False 반환 / true → True** (v1 유지).
3. **orgs=None이면 관련도 질문·about_org 없음** (비조합 동일).
4. **문자열 "false"/"true" 안전 처리** (v1 유지).
5. **enrich_articles: 조합기사 about_org=false → 제외 / true·누락·AI오류 → 통과 / 비조합 → 미적용**(v1 유지, orgs 목록 전달로).
6. **config.COMPANY_ALIASES 존재 + enrich가 K-FINCO/CIG를 프롬프트에 반영**.

---

## 배포 / 후속

`main` 머지 → VM cron 자동 반영. 배포 후:
1. **청소 dry-run 재실행**(`cleanup_relevance.py`) — 제거 목록에서 진짜 조합/협회 뉴스(K-FINCO 피치·협회 활동·박종학 부고)가 빠졌는지 확인.
2. 괜찮으면 `--apply`로 실제 청소.
3. 이후 dedup 개선.

---

## 예상 효과

dry-run에서 잘못 찍혔던 K-FINCO 피치 A+·협회 직접발주·박종학 부고 → 모두 **통과(보존)**. 칼럼·전세사기·벤더뉴스 → 여전히 **제거**. 운영 게이트도 진짜 뉴스를 안 떨굼.
