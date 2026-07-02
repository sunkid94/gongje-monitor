# 멀티소스 크롤러 설계 — 네이버 + 구글 + 기계설비신문 RSS

**작성일:** 2026-06-07
**상태:** 승인됨

---

## 개요

현재 크롤러는 **구글 뉴스 RSS 검색만** 사용한다(`crawler.py`). 구글은 기사를 색인하는 데 지연이 커서, 발행된 지 몇 시간~10시간 지난 뒤에야 수집·푸시되는 일이 잦다(실측: K-FINCO 채용 기사 발행 08:00 → 수집 18:32).

소스를 늘려 **발행 직후에 잡아 제때 알림**하도록 한다:

- **네이버 뉴스 검색 API (주력)** — 한국 뉴스 색인이 빠르고 넓다. 실측: 전문지(koscaj) 08:00 발행분을 같은 시각에 노출. 검색 OpenAPI 키는 발급·저장 완료(`config.env`의 `NAVER_CLIENT_ID/SECRET`).
- **구글 뉴스 RSS (보조)** — 기존 로직 유지, 폭넓은 백업.
- **기계설비신문(kmecnews) RSS (우리 조합 보험, 피드 1개)** — 우리 조합(기계설비건설공제조합)의 핵심 공급원(데이터 출처 1위, 31건)인데 **네이버 색인이 얇음**(검증: 우리 조합 검색에 1건, "기계설비" 최신 30건엔 0건). 따라서 이 매체만 직접 RSS로 보장.

**비목표:** 다른 전문지 RSS 풀(네이버가 커버하므로 제외), 발행일 컷오프 필터(별도 사안), 이메일/웹/푸시 dedup 로직 변경(기존 유지).

---

## 아키텍처

소스를 **모듈로 분리**하고 `crawler`가 합친다. 각 소스는 **기존 구글과 동일한 형식의 원시 기사 dict**를 반환한다 — 특히 제목을 `"헤드라인 - 매체명"` 형식으로 맞춰, 기존 `enrich.extract_publisher`(접미사에서 매체 추출) + `cluster_id`(접미사 뗀 정규화 제목) 로직이 **수정 없이** 동작하게 한다.

```
source_google.fetch() ─┐
source_naver.fetch()  ─┼─→ crawler.fetch_new_articles(seen): 합치기 + seen(link) 중복 제거
source_rss.fetch()    ─┘        → enrich → article_store(저장·publisher/cluster dedup)
                                → mailer / notifier(canon·overlap 푸시 dedup)
```

소스 간 **같은 기사 중복**(구글 redirect link / 네이버 originallink / RSS 직접 link — URL이 달라 seen으론 못 거름)은 기존 `(publisher, cluster_id)` 저장 dedup + 신규 canon/overlap 푸시 dedup가 합쳐준다(제목 형식을 맞추므로 cluster_id 일치).

---

## 변경 파일

| 파일 | 변경 |
|------|------|
| `source_google.py` (신규) | 기존 `crawler.fetch_news_rss` + 구글 처리 로직 이전. `fetch() -> list[dict]` |
| `source_naver.py` (신규) | 네이버 검색 API 클라이언트 + `fetch() -> list[dict]` |
| `source_rss.py` (신규) | 전문지 RSS fetcher(키워드 관련도 필터 포함) + `fetch() -> list[dict]` |
| `crawler.py` (수정) | `fetch_new_articles(seen)` 가 세 소스를 호출·합치고 seen 중복만 제거 |
| `config.py` (수정) | `TRADE_RSS_FEEDS = [{"name":"기계설비신문","url":".../rss/allArticle.xml"}]`; 네이버 키는 env |
| `tests/test_source_*.py` (신규) | 소스별 단위 테스트 + 통합 |

---

## 컴포넌트

### 공통 출력 형식 (raw article dict)
`{"keyword", "category", "is_company", "title", "link", "description", "published_at"}` — `title`은 `"헤드라인 - 매체명"`, `published_at`은 tz-aware ISO. 각 소스가 자체적으로 발행시각 확정 + 최근성(24h) 필터까지 책임진다.

### source_google
기존 `fetch_news_rss` + `fetch_new_articles`의 구글 부분 이전. 구글은 옛 기사를 재색인하는 문제가 있어 기존 `resolve_published_time` + `ORIGINAL_PUB_MAX_AGE_DAYS` 폐기 로직을 그대로 유지.

### source_naver
- 각 키워드(`COMPANY_KEYWORDS`→is_company=True/"조합·협회", `CATEGORY_KEYWORDS`→False)로 `GET https://openapi.naver.com/v1/search/news.json?query="키워드"&display=20&sort=date` 호출. **정확검색(따옴표)** 으로 노이즈↓. 헤더에 `X-Naver-Client-Id/Secret`.
- 매핑: `title`=HTML 태그 제거한 headline **+ " - " + 매체명**(매체명 = `originallink` 도메인→이름; 알려진 도메인 소수는 매핑표, 그 외 도메인 그대로), `link`=`originallink`(없으면 `link`), `description`=태그 제거, `published_at`=`pubDate`(RFC822) 파싱.
- **관련도 필터:** 헤드라인+본문에 해당 키워드 토큰이 실제 포함된 것만 통과(네이버 광역 매칭 노이즈 제거). 24h 이내만.
- 키/네트워크 오류·`errorCode` 응답 시 빈 리스트 + 경고 로그(런 안 죽음).

### source_rss
- `TRADE_RSS_FEEDS`의 각 피드를 `feedparser`로 파싱(현재 kmecnews 1개). 피드는 "전체 기사"라 **관련도 필터 필수**: 헤드라인+본문에 `COMPANY_KEYWORDS`(→is_company=True/"조합·협회") 또는 산업 키워드(→해당 category) 포함분만 통과.
- 매핑: `title`=headline **+ " - " + 피드명**(예: "… - 기계설비신문"), `link`=item link, `published_at`=item pubDate, 24h 이내.
- 피드 fetch 실패 시 그 피드만 건너뛰고 경고 로그.

### crawler.fetch_new_articles(seen)
세 소스 `fetch()` 결과를 이어붙이고, `link`가 `seen`에 없는 것만 남겨 반환. (발행시각·관련도·매체형식은 소스가 이미 처리.) 시그니처·반환 형식은 기존과 동일 → `main.py` 무변경.

---

## 노이즈·비용 제어

- 네이버: 정확검색 + 키워드 실제 포함 필터 + 24h → enrich(Claude API)로 넘어가는 양 억제.
- RSS: 키워드 포함분만.
- 최종 푸시는 기존대로 **is_company 기사만** → 잔여 잡음은 웹 목록까지, 알림엔 안 감.
- **네이버 API 한도:** 키워드 27개(COMPANY 5 + INDUSTRY 22) × 일 ~288런 ≈ **7,776건/일** — 한도 25,000의 약 31%로 매 5분 캐던스 유지에 여유 충분.

---

## 에러 처리

각 소스는 독립적으로 try/except — 한 소스(네이버 rate limit·다운, 피드 깨짐)가 실패해도 **나머지 소스 결과로 정상 진행**, 실패는 로그만. `crawler`는 어떤 소스가 비어도 동작.

---

## 테스트 (TDD)

- `source_naver`: 목 응답으로 — 정상 파싱(매체명 접미사 부착, originallink 사용), 관련도 필터(키워드 없는 항목 제외), `errorCode`/네트워크 오류 시 빈 리스트, 24h 컷오프.
- `source_rss`: 목 피드로 — 관련도 필터(조합 키워드 포함분만, 무관 기사 제외), 피드명 접미사 부착, 발행시각.
- `source_google`: 기존 동작 보존(리팩터 회귀 없음).
- 통합: 세 소스 합치기 + seen 중복 제거; **같은 기사가 구글/네이버/RSS로 들어와도** 제목 형식이 같아 enrich의 cluster_id가 일치(→ 저장/푸시 dedup가 1건으로) 검증.

---

## 배포

`main` 머지 시 VM cron `git pull --rebase`로 자동 반영(코드). 네이버 키는 이미 `config.env`에 있음. 머지 후 `monitor.log`에서 소스별 수집 로그 + 발행~수집 지연이 줄었는지 확인.

---

## 예상 효과

전문지가 08:00에 낸 기사를 네이버(또는 우리 조합은 kmecnews RSS)가 **그 시각에** 잡아 제때 알림 — 구글 색인 지연(수 시간)을 더는 기다리지 않는다. 우리 조합 뉴스는 kmecnews RSS로 직접 보장.

---

## 후속 과제 (이번 범위 밖, 최종 리뷰 발견)

1. **소스 간 저장/이메일 중복 (Issue 1)** — `article_store.filter_duplicates`가 `(publisher, cluster_id)` 기준이라, 같은 매체·같은 기사라도 네이버(도메인 라벨, 예: `pinpointnews.co.kr`)와 구글(한글 라벨, 예: "핀포인트뉴스")의 매체명이 달라 웹/이메일에 2건으로 저장될 수 있다. **푸시는 canon/overlap로 정상 중복제거되어 영향 없음.** 해결 방향(별도 결정 필요): (a) 매체명 정규화(공유 도메인→이름 맵 확장 또는 구글 링크를 원문 URL로 디코딩해 link 일치) 또는 (b) "사건당 1카드" 정책으로 dedup을 cluster_id 기준으로 전환. "매체별 카드 유지(커버리지) vs 사건당 1카드" 제품 결정과 얽힘.
2. **네이버 호출량 모니터링 (Issue 2)** — 27키워드 × ~288런/일 ≈ 7,776건/일(한도 25,000의 31%). 키워드·캐던스 증가 시 한도 근접 가능 — 운영 로그로 추적, 필요 시 캐싱/백오프.

---
> 📑 관련 문서 전체 지도: [CIG 이슈 모니터 문서 인덱스](../CIG-MONITOR-INDEX.md)
