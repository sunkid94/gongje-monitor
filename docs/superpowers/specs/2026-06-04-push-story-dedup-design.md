# 푸시 스토리 단위 중복제거 설계

**작성일:** 2026-06-04
**상태:** 승인됨

---

## 개요

CIG 이슈 모니터의 웹푸시 알림이 **같은 뉴스 사건을 몇 시간에 걸쳐 여러 번** 발송하는 문제를 해결한다.

근본 원인: 푸시 발송 조건(`notifier.send_company_push`)은 "그 5분 런에서 새로 들어온 `is_company` 기사가 1건이라도 있으면 발송"이며, **"이 스토리를 이미 알렸는가"를 기록하지 않는다.** 중복제거(`article_store.filter_duplicates`)는 `(publisher, cluster_id)` 기준이라 매체가 다르면 같은 사건도 통과하고, `cluster_id`(정규화 제목 해시)는 제목 표현이 조금만 달라도 다른 클러스터로 쪼개진다.

실측 사례 (2026-06-04, "피치 신용등급 A+ 유지" 단일 사건):

| 시각 | 매체 | cluster_id |
|------|------|-----------|
| 09:38 | 네이트(K-FINCO) | 66ec |
| 09:58 | 뉴스1 | 721e |
| 10:13 | 경남대방송국 | 6077 |
| 10:17 | 기계설비신문 | 8c9a |
| 10:23 | 연합뉴스한민족 | 8c9a |
| 10:53 | 네이트 | 721e |
| 12:02 | 핀포인트뉴스 | 66ec |
| 12:22 | 연합뉴스 | 8c9a |
| 13:17 | 네이트 | 8c9a |
| 16:37 | 이데일리 | 721e |

한 사건이 4개 cluster_id로 흩어져 약 10회 푸시되었다. 사용자 체감: "크롤링되고 몇 시간 후에 한 번씩 알람이 온다."

**참고:** 첫 알람과 웹 표시·푸시 타이밍 자체는 정상이다(16:37 런에서 푸시 16:37:37 → 웹 갱신 16:37:44). 고칠 대상은 **두 번째 이후의 중복 푸시뿐**이다.

---

## 목표 / 비목표

**목표**
- 같은 뉴스 사건은 24시간 내 **한 번만** 푸시한다.
- 첫 알람은 지금처럼 즉시 발송한다(지연 추가 없음).
- 기사 저장·웹 대시보드 표시·이메일은 **일절 변경하지 않는다**(전건 그대로).

**비목표**
- `cluster_id` 생성 로직(enrich) 변경 — 건드리지 않는다.
- 이메일 다이제스트화, 푸시 배칭 — 이번 범위 아님.
- articles.json 원자적 쓰기 개선 — 별개 이슈(아래 부록 참조).

---

## 아키텍처

기존 흐름에 푸시 직전 **중복제거 필터** 1단계만 삽입한다:

```
crawler → enrich → article_store(저장, 웹 표시 전건 유지) → mailer
                                                          → notifier.send_company_push
                                                              └─ push_dedup.filter_unpushed  ← 신규
                                                                  └─ 신규 스토리만 webpush 발송
```

푸시 이외 경로(웹/이메일/저장)는 필터를 거치지 않는다.

---

## 변경 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `push_dedup.py` | 신규 — 스토리 키 생성, 푸시 이력 로드/저장, 중복 필터 |
| `notifier.py` | `send_company_push`에서 발송 직전 `filter_unpushed` 호출, 억제 건수 로깅 |
| `pushed.json` | 신규 데이터 파일 — 최근 푸시한 스토리 이력 (gitignore 또는 커밋 정책은 부록 참조) |
| `tests/test_push_dedup.py` | 신규 — 단위/통합 테스트 |

---

## 컴포넌트: `push_dedup.py`

### `story_key(title: str) -> set[str]`
제목을 정규화해 핵심어 집합을 반환한다.

1. `" - "` 뒤 매체명 제거 (예: `"… 유지 - 이데일리"` → `"… 유지"`)
2. 따옴표·괄호·기호 제거, 소문자화(영문)
3. 토큰화 후 핵심어 집합 생성

**한국어 토큰화 주의:** `국제신용등급` vs `신용등급`처럼 형태가 달라 공백 토큰 정확매칭만으론 약하다. 구현 단계에서 두 후보를 **실제 피치 제목 픽스처로 측정**해 채택한다:
- (A) 공백 토큰 집합 + 핵심어 정규화
- (B) 문자 n-gram(bigram) 집합

임계값 0.6의 "의미"(중간 정도 겹침)는 유지하되, 실측에서 피치 10건이 1건으로 수렴하고 서로 다른 스토리는 분리되도록 토큰화 방식과 정확한 수치를 보정한다.

### `similarity(a: set, b: set) -> float`
Jaccard 유사도 `|a∩b| / |a∪b|`.

### `load_pushed(now) -> list[dict]`
`pushed.json`을 읽어 `pushed_at`이 24시간 이내인 항목만 반환. 파일 없음/JSON 깨짐 → 빈 리스트 반환 + 경고 로그(안전쪽: 이력 없으면 발송 진행 → 알림 누락 방지).

각 항목 형식: `{"tokens": [...], "pushed_at": "2026-06-04T16:37:37+09:00", "title": "원문 제목"}`

### `save_pushed(entries, now) -> None`
24시간 경과분 정리 후 **원자적 쓰기**(임시파일 + `os.replace`)로 저장.

### `filter_unpushed(company_articles, now) -> (to_push, suppressed)`
1. `recent = load_pushed(now)`
2. 각 기사에 대해 `story_key` 계산, `recent`의 모든 항목 + **같은 배치에서 앞서 to_push로 채택된 기사들**과 `similarity` 비교
3. 최대 유사도 ≥ 임계값 → `suppressed`에, 아니면 `to_push`에 추가하고 `recent`에도 편입(배치 내 자기중복 차단)
4. 채택된 스토리들을 `save_pushed`로 기록
5. `(to_push, suppressed)` 반환

상수: `SIMILARITY_THRESHOLD = 0.6`, `WINDOW_HOURS = 24` (모듈 상단 상수로 노출, 보정 가능).

---

## 통합: `notifier.send_company_push`

```
company = [is_company 기사]
if not company: return (기존과 동일)
to_push, suppressed = push_dedup.filter_unpushed(company, now)
if suppressed:
    logger.info("스토리 중복 %d건 푸시 억제", len(suppressed))
if not to_push:
    logger.info("새 스토리 없음 — 푸시 알림 건너뜀")
    return
# 이하 기존 발송 로직을 to_push 대상으로 수행
```

`save_pushed`는 발송 **시도** 시점에 기록한다(구독 만료 등 수신자측 실패는 스토리 잘못이 아니므로 재푸시 트리거가 되면 안 됨).

---

## 엣지 케이스

- `pushed.json` 없음/깨짐 → 빈 이력, 정상 발송(알림 누락보다 중복 허용이 안전).
- 모든 시각은 tz-aware(`article_store.format_collected_at`/`parse_collected_at`와 동일 규약).
- 24시간 경과한 같은 스토리(이틀 연속 재보도) → 다음날 1회 재알림. **의도된 동작.**
- 동시 쓰기: cron은 5분 간격·런 ~15초라 겹치지 않고 `:17`(풀)과 `*/5`(푸시)는 분이 겹치지 않음. 그래도 `save_pushed`는 원자적 쓰기로 방어한다.

---

## 테스트 (TDD)

`tests/test_push_dedup.py`:

1. **피치 통합 시나리오** — 2026-06-04 실제 "전문건설공제조합 … 피치 … A+ 유지" 변형 7건을 시각순으로 `filter_unpushed`에 흘려보내면 첫 1건만 `to_push`, 나머지 6건 `suppressed`(`신용등급`↔`국제신용등급` 차이만 있는 변형들이 1건으로 수렴). 주의: 브랜드명이 다른 "K-FINCO …" 계열은 같은 조직임을 단정하지 않으므로 별도 1건으로 발송될 수 있음 — 과잉 억제(다른 조직 뉴스 누락) 방지가 우선이다. 전체적으로 ~10회 → 2~3회로 감소.
2. **창 만료** — 같은 스토리를 25시간 뒤에 넣으면 다시 `to_push`.
3. **서로 다른 스토리** — 관계없는 두 조합기사는 둘 다 `to_push`(과잉 억제 없음).
4. **story_key 정규화** — 매체명 접미사 제거·기호 제거 단위 검증.
5. **similarity** — 경계값(정확히 임계값) 동작 검증.
6. **손상된 pushed.json** — 빈 이력으로 처리되고 전건 `to_push`.

먼저 1~6을 실패하는 테스트로 작성 → `push_dedup.py` 구현 → 통과 확인. 구현 중 토큰화 방식/임계값은 테스트 1·3이 동시에 통과하도록 보정.

---

## 배포

`reference_cig_monitor_deploy.md` 워크플로(scp + cron)에 따라 `push_dedup.py`, 수정된 `notifier.py`를 Oracle VM에 반영한다. `pushed.json`은 첫 실행 시 자동 생성. cron 5분 마크를 피해 수동 검증 1회.

---

## 부록: 범위 밖 발견 사항 (별도 메모)

조사 중 `articles.json`을 읽다 일시적 JSON 파싱 에러를 겪었다 — `save_articles`가 비원자적으로 직접 파일을 덮어써, 읽는 쪽이 반쯤 쓰인 파일을 볼 수 있다. cron 간격상 실질 위험은 낮지만, 추후 `save_articles`도 원자적 쓰기로 바꾸면 git/외부 리더의 레이스를 없앨 수 있다. **이번 범위 밖.**
