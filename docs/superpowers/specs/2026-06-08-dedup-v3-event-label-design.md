# dedup v3 설계 — AI 이벤트 라벨 기반 푸시 중복제거

**작성일:** 2026-06-08
**상태:** 승인됨

---

## 개요

푸시 중복제거 v2는 **제목 토큰 + 선두 조직명(쉼표 앞) 앵커**로 같은 사건을 묶는다. 부고처럼 **제목에 쉼표가 없고 주인공이 사람**인 기사에서 무너진다.

실측: "박종학 회장 별세" 사건이 **24번 푸시**됨. 매체마다 제목이 "기계설비산업 발전 이끈 박종학 전 기계설비건설협회장 별세" / "박종학 대한기계설비건설협회 제6대 회장 별세" / "박종학씨 外" … 로 제각각이라, 쉼표 앞(=제목 전체)을 canon으로 잡아 매번 다른 canon → overlap 비교조차 안 됨.

근본 원인: **지저분한 제목에서 조직·사건을 추출하려는 휴리스틱의 한계.**

## 목표 / 비목표

**목표:** AI가 정규화한 **이벤트 라벨**(예: "대한기계설비건설협회 박종학 회장 별세")로 묶어, 표현·매체·사람·부고가 달라도 같은 사건은 **푸시 1회**.

**비목표:**
- 웹/이메일 저장 dedup — 별도 후속(이번은 **푸시만**).
- 관련도 게이트·소스·이메일 변경.

**원칙:** 다른 조직은 안 묶음(우리 조합이 형제 조합에 안 묻힘) — 라벨이 대표조직으로 시작하므로 조직이 다르면 canon이 달라 분리. AI 라벨이 없으면(크레딧 소진 등) **기존 제목 기반으로 폴백**(최소 동작 유지).

---

## 아키텍처

`enrich.py`(라벨 생성) + `push_dedup.py`(라벨로 묶기). 기존 overlap·7일 창·방향가드·pushed.json 구조는 그대로 재사용 — **입력만 제목에서 라벨로** 바꾼다.

```
enrich(기존 Claude 호출에 event_label 1필드 추가) → 조합기사에 event_label 부착
push_dedup.filter_unpushed:
  event_label 있으면 → key=story_key(label), canon=label_canon(label)
  없으면(폴백)      → key=story_key(title), canon=canonical_org(title)   (= v2)
  → _same_story(같은 canon + overlap>=0.7 + 방향가드) + 7일 창
```

`main.py`·소스·notifier 무변경. (notifier가 `art["event_label"]`을 push_dedup로 그대로 넘김 — enriched article에 이미 있음.)

---

## 변경 파일

| 파일 | 변경 |
|------|------|
| `enrich.py` | 프롬프트에 `event_label` 요청 추가; `enrich_article`가 라벨 반환(orgs 있을 때); `enrich_articles`가 조합기사에 `event_label` 부착 |
| `push_dedup.py` | `from config import COMPANY_KEYWORDS, COMPANY_ALIASES`; `label_canon(label)`(라벨에서 추적 조직 추출, 별칭 인식); `filter_unpushed`가 event_label 있으면 라벨로 key/canon 계산 |
| `tests/test_enrich.py`, `tests/test_push_dedup.py` | event_label 생성·부착, 라벨 기반 묶기 테스트 |

---

## 컴포넌트

### enrich — event_label
- 프롬프트(조직 목록이 주어지는 조합기사)에서 `event_label` 추가 요청:
  > event_label: 이 기사의 핵심 사건을 **"대표조직명 + 핵심사건"** 한 줄로 간결히. 대표조직은 위 목록의 **정식 명칭** 사용(예: K-FINCO → 전문건설공제조합). 매체·표현이 달라도 **같은 사건이면 같은 라벨**이 나오게. 예: "대한기계설비건설협회 박종학 회장 별세", "전문건설공제조합 피치 신용등급 A+ 유지".
- JSON에 `"event_label": "..."` 추가(orgs 있을 때만).
- `enrich_article` 반환에 `event_label`(문자열) 포함(orgs 있고 응답에 있을 때). 폴백/누락 시 없음.
- `enrich_articles`: 제외 안 된 조합기사에 `out["event_label"] = ai["event_label"]`(있으면).

### push_dedup — label_canon + 라벨 기반 묶기
- `label_canon(label) -> str`: `COMPANY_KEYWORDS`(+`COMPANY_ALIASES`)를 라벨에서 검색(더 긴 이름 우선, 소문자 비교), 처음 걸리는 대표조직 반환. 못 찾으면 정규화된 라벨 전체(보수적 — 라벨이 거의 같을 때만 묶임).
- `filter_unpushed`: 각 기사에서
  - `label = art.get("event_label")`; 있으면 `key = story_key(label)`, `canon = label_canon(label)`.
  - 없으면 `key = story_key(title)`, `canon = canonical_org(title)` (v2 폴백).
  - 이후 기존 `_same_story`(canon 일치 + overlap≥0.7 + 방향가드) + 7일 창 + pushed.json 저장 그대로.
- pushed.json 엔트리 스키마(`tokens, canon, pushed_at, title`) 불변 — tokens/canon이 라벨에서 오느냐 제목에서 오느냐 차이뿐.

---

## 데이터 흐름 / 호환

- 라벨은 enrich 출력 article dict에 실려 article_store(저장)·notifier(푸시)로 흐른다. 저장 dedup(`filter_duplicates`)·웹은 라벨 안 씀(푸시만).
- pushed.json 기존 엔트리(제목 기반 canon/tokens)와 라벨 기반 신규 엔트리가 섞여도 `_same_story`는 동일 로직 — 라벨끼리, 제목끼리 각각 잘 비교됨. 7일 내 자연 전환.

---

## 엣지 케이스

- event_label 누락(AI가 필드 안 줌)/AI 오류 → 제목 기반 폴백(v2). 크레딧 소진 시에도 최소 동작.
- 라벨에 추적 조직 없음 → label_canon 폴백(정규화 라벨) → 거의 동일 라벨만 묶임(보수적).
- 다른 조직: 라벨이 대표조직으로 시작 → canon 다름 → 안 묶임.
- 방향(상향/하향 vs 유지): 라벨에 포함 → 방향가드가 분리(기존 로직).

---

## 테스트 (TDD)

`tests/test_enrich.py`:
1. orgs 있을 때 프롬프트에 event_label 요청 포함, 응답의 라벨이 결과·article에 부착.
2. orgs 없으면 event_label 없음. 폴백/누락 시 없음.

`tests/test_push_dedup.py`:
3. **label_canon** — "대한기계설비건설협회 박종학 회장 별세" → "대한기계설비건설협회"; "전문건설공제조합 K-FINCO …"/"K-FINCO …" → "전문건설공제조합"(별칭); 추적 조직 없으면 폴백.
4. **부고 변형 수렴** — 같은 라벨류(대한기계설비건설협회 박종학 회장 별세)의 기사 여러 건이 event_label로 들어오면 첫 1건만 to_push, 나머지 suppressed.
5. **다른 조직 분리** — "기계설비건설공제조합 …"과 "전문건설공제조합 …" 라벨 → 각각 발송.
6. **폴백** — event_label 없는 기사는 기존 제목 기반 동작(v2 테스트 유지).

---

## 배포 / 후속

`main` 머지 → VM cron 자동 반영. 배포 후 `monitor.log`에서 같은 사건(부고 등)이 1회만 푸시되는지 확인. (웹/이메일 저장 dedup은 별도 후속.)

---

## 예상 효과

박종학 부고 24회 → **1회**. 라벨이 매체·표현 차이를 흡수하고, 대표조직이 라벨에 명시돼 조직 구분도 정확. AI 다운 시 제목 기반으로 폴백해 최소 동작 유지.
