# 이슈 모니터 임원 공개 개편 설계

**작성일**: 2026-04-23
**대상**: `gongje-monitor` (Google News 기반 이슈 수집·요약·아카이브 시스템)
**목적**: 임원진 공유에 앞서 시인성·편의성·카테고리 구조·AI 활용을 고도화

---

## 배경

현재 이슈 모니터는 4개 조합 + 9개 산업 키워드를 매시간 수집해 Haiku로 요약 후
이메일·정적 사이트로 노출한다. 임원진 공유가 결정되면서 다음 문제가 부각되었다.

- 산업 키워드가 평면적으로 나열되어 흐름 파악이 어렵다.
- 같은 사건의 중복 기사가 카드 5개로 도배된다.
- "지금 중요한 게 뭔가" 가 한눈에 안 들어온다.
- 위기 감지(부정 이슈)와 호재 구분이 시각적으로 없다.
- 종합건설사 동향과 해외수주 같은 임원 관심사가 빠져 있다.

본 스펙은 위 문제를 3단계로 해결한다(4단계 임원 대시보드는 별도 스펙).

## 범위

**포함 (Phase 1·2·3)**
- Phase 1 — UI/UX 개편: 톱 이슈 섹션, 검색·기간 필터, 중복 묶기, 언론사 표시, 링크 복사, 30주년 브로슈어 디자인 언어 적용
- Phase 2 — 카테고리 2단 구조: 4개 상위 카테고리 + 종합건설사(상위 10곳) 신규
- Phase 3 — AI 부가 활용: 규칙 기반 중요도 스코어, 감정 톤(업계 시점), 주간 요약 카드

**제외 (4단계 별도 스펙)**
- 시계열 차트 / 조합 언급량 비교 / 언론사 분포 차트
- 데이터 export (CSV/엑셀) / 사용자 인증 / 푸시 알림

---

## 결정 사항 (사용자 합의)

| 항목 | 결정 |
|---|---|
| 산업 카테고리 | 정책·규제 / 시장·경기 / 안전·사고 / 노동·인력 |
| 종합건설사 추가 | 상위 10개사 (시평 기준) |
| 톱 이슈 산정 | 하이브리드 — 조합 직접 언급 별도 + 카테고리별 중요도 상위 3건 |
| 중요도 스코어 | 규칙 기반 (설명 가능성·비용 0) |
| 감정 톤 | 3단계 (부정/중립/긍정), Haiku 1회 호출에 통합 |
| 감정 판단 시점 | 건설업계·조합 전반 입장 |
| 주간 요약 | Haiku 자동 생성 (일요일 23시 cron) |
| 검색 범위 | 제목 + AI 요약 |
| 기간 필터 기본 | 최근 7일 |
| 중복 기사 묶기 | 정규화한 제목 + 자카드 0.85 이상 |
| 언론사명 추출 | 기사 제목 끝의 ` - 매체명` 패턴에서 |
| 링크 공유 | 카드별 "링크 복사" 버튼 |
| 디자인 톤 | `ci-guarantee-30th (10).html` 의 브로슈어 스타일 차용 |

---

## 아키텍처

### 데이터 흐름

```
                 매시간 17분 cron
                       ↓
  ┌──────────────────────────────────────────────────┐
  │ crawler.py                                       │
  │  · 조합 4 + 산업 9 + 종건사 10 = 23개 키워드     │
  │  · Google News RSS 수집                          │
  │  · 각 기사에 category 필드 부여                  │
  └──────────────────────────────────────────────────┘
                       ↓ 신규 기사
  ┌──────────────────────────────────────────────────┐
  │ enrich.py (신규)                                 │
  │  ① 제목 정규화 → 중복 묶기 (cluster_id)          │
  │  ② 언론사명 추출                                 │
  │  ③ Haiku 1회: 요약 + 감정 톤(업계 시점)          │
  │  ④ 규칙 기반 중요도 스코어                       │
  └──────────────────────────────────────────────────┘
                       ↓
  ┌──────────────────────────────────────────────────┐
  │ article_store.add_articles → articles.json        │
  │ mailer.send_email                                 │
  └──────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────┐
  │ weekly_summary.py (신규, 일요일 23시 cron)        │
  │  · 지난 7일 importance >= 6 → cluster 단위 5개    │
  │  · Haiku 단락 요약 → weekly.json                 │
  └──────────────────────────────────────────────────┘
```

### 파일 변경

| 파일 | 변경 |
|---|---|
| `config.py` | `COMPANY_KEYWORDS`, `CATEGORY_KEYWORDS` 구조로 재편 |
| `crawler.py` | 카테고리 dict 순회, 기사에 `category` 부여 |
| `summarizer.py` | `enrich.py`로 통합·삭제 |
| `enrich.py` | 신규 — 정규화·클러스터링·요약·감정·중요도 |
| `weekly_summary.py` | 신규 — 주간 5건 단락 요약 |
| `weekly.json` | 신규 — 주간 카드 캐시 |
| `main.py` | `enrich_articles()` 호출, 클러스터링 호출 |
| `mailer.py` | 본문에 importance·sentiment 표시 (옵션) |
| `index.html` | 대폭 개편 (디자인 + 신규 기능) |
| `scripts/migrate_articles.py` | 신규 — 1회용 기존 데이터 마이그레이션 |
| `tests/test_enrich.py`, `test_weekly_summary.py` | 신규 |

---

## 데이터 모델

### `config.py`

```python
COMPANY_KEYWORDS = [
    "기계설비건설공제조합",
    "엔지니어링공제조합",
    "건설공제조합",
    "전문건설공제조합",
]

CATEGORY_KEYWORDS = {
    "정책·규제": ["건설산업기본법", "국토교통부 건설", "건설업 규제"],
    "시장·경기": ["건설경기", "건설 PF", "건설수주"],
    "안전·사고": ["중대재해 건설", "건설현장 안전"],
    "노동·인력": ["건설 노동"],
    "종합건설사": [
        "삼성물산 건설", "현대건설", "DL이앤씨", "대우건설", "GS건설",
        "포스코이앤씨", "롯데건설", "SK에코플랜트",
        "HDC현대산업개발", "현대엔지니어링",
    ],
}
```

`삼성물산`은 패션·바이오 등 비건설 부문 노이즈가 많아 ` 건설`을 부착해 검색 정확도 확보.

**카테고리 부여 규칙** (`crawler.py`):
- `COMPANY_KEYWORDS` 순회 시 → `category = "조합"`, `is_company = True`
- `CATEGORY_KEYWORDS` dict 순회 시 → `category = dict key`, `is_company = False`
- 따라서 유효한 `category` 값은 총 6개: `조합`, `정책·규제`, `시장·경기`, `안전·사고`, `노동·인력`, `종합건설사`
- 사이트의 "카테고리별 톱 이슈" 섹션은 `조합`을 제외한 5개만 표시 (조합 기사는 상단 별도 섹션에서 이미 강조됨)

### `articles.json` 스키마

```jsonc
{
  "keyword": "현대건설",
  "category": "종합건설사",          // 신규
  "title": "현대건설, 사우디 수주 확대 - 조선비즈",
  "title_clean": "현대건설, 사우디 수주 확대",  // 신규
  "publisher": "조선비즈",            // 신규
  "link": "...",
  "summary": "...",
  "sentiment": "positive",           // 신규: positive/neutral/negative
  "importance": 7,                   // 신규: 0~10 정수
  "cluster_id": "a3f2",              // 신규
  "is_company": false,               // 신규
  "collected_at": "..."
}
```

조합 4개 키워드는 `category="조합"` + `is_company=true`. 카테고리 dict 순회 시 카테고리는 자동 부여.

### `weekly.json` 스키마

```jsonc
{
  "period": "2026-04-13 ~ 2026-04-19",
  "generated_at": "2026-04-19T23:05:00",
  "items": [
    {"category": "시장·경기", "headline": "태영건설 워크아웃 1주년…", "brief": "지난 1년…"},
    ...
  ]
}
```

---

## 컴포넌트 설계

### 1. 정규화 + 클러스터링 (`enrich.py`)

```python
def normalize_title(title: str) -> str:
    title = re.sub(r"\s*-\s*[^-]+$", "", title)        # " - 매체명" 제거
    title = re.sub(r"[\s\W_]+", "", title.lower())     # 구두점·공백 제거
    return title

def cluster_articles(articles: list) -> list:
    """같은 정규화 제목 또는 토큰 자카드 0.85 이상이면 같은 cluster_id"""
    # cluster_id는 4자 16진수 해시 (가독용)
```

### 2. 통합 enrich 프롬프트 (`enrich.py`)

```
다음 뉴스 기사를 분석해 JSON으로 답하세요.

제목: {title_clean}
내용: {description}

판단 기준:
- 감정 톤은 "건설업계 전반과 기계설비건설공제조합" 시점에서 평가합니다.
  · positive: 업계 호재 (수주 증가, 규제 완화, 시장 확대 등)
  · negative: 업계 악재 (사고, 규제 강화, PF 위기, 부정 이슈 등)
  · neutral: 사실 보도, 양면적, 판단 어려움
- 요약은 한국어 2~3줄, 핵심만.

JSON 형식 (다른 텍스트 없이 이것만):
{"summary": "...", "sentiment": "positive|neutral|negative"}
```

파싱 실패 시 폴백: `summary = description[:200]`, `sentiment = "neutral"`. 재시도 안 함.

### 3. 중요도 스코어 (`enrich.py`)

```python
def calc_importance(article, cluster_size: int) -> int:
    score = 0
    if article["is_company"]:
        score += 5
    if article["sentiment"] == "negative":
        score += 3
    score += min(cluster_size, 5)
    if (now - article["collected_at"]) < timedelta(hours=24):
        score += 2
    return min(round(score * 10 / 15), 10)   # 0~10 정규화
```

### 4. 주간 요약 (`weekly_summary.py`)

- 일요일 23시 cron으로 호출
- 지난 7일 `importance >= 6` 기사 → cluster_id로 묶고 cluster당 최고 importance 1건 → 상위 5개 cluster
- 후보가 5개 미만이면 `importance >= 4` 까지 확장
- Haiku에게 5개를 한 번에 던지고 JSON 응답 받음
- `weekly.json` 덮어쓰기

### 5. 사이트 (`index.html`)

#### 페이지 구조 (위→아래)

1. **HERO** — 30주년 파일 스타일 차용. Pretendard Variable, 큰 타이틀, 부제 "기계설비건설공제조합 이슈 모니터", 마지막 업데이트 시각.
2. **주간 요약 카드** — 그라데이션 파스텔 라벨 "WEEKLY BRIEF", 5개 항목 리스트.
3. **검색 + 필터 바 (sticky, backdrop-blur)** — 검색창, 기간 필터(오늘/3일/7일★/1개월/전체), 카테고리 필터(전체 / 조합▾ / 산업▾ / 종건사▾).
4. **🔴 우리 조합 직접 언급 이슈** — `is_company=true` 기사 카드(좌측 navy 굵은 라인 + 적색 배지).
5. **카테고리별 톱 이슈** — 정책·규제 / 시장·경기 / 안전·사고 / 노동·인력 / 종합건설사 각 상위 3건 (importance 정렬).
6. **전체 기사** — 날짜별 그룹.

#### 기사 카드 디자인 (30주년 톤 차용)

- 배경 흰색, `border-left: 3px solid var(--navy)`, hover 시 `translateX(4px)`
- 좌측 상단: 중요도 점 3개 (●●● 7-10, ●● 4-6, ● 1-3)
- 카테고리 배지 + 감정 점(🔴/⚪/🟢) + 언론사명 + 상대 시각
- 우측 상단: 📋 링크 복사 버튼
- 제목(중간 굵게, navy 색) + cluster_size > 1이면 "+ N개 매체" 펼침 버튼
- "AI 요약" 라벨 + 요약 본문

#### 색상 체계 (30주년 팔레트 통일)

```css
--navy: #1E3A6F;          /* 메인 */
--navy-dark: #142848;
--navy-deep: #0A1829;
--blue-accent: #4A7BC8;   /* 강조, 호버 힌트 */
--blue-soft: #7BA4D9;
--cyan-soft: #9BC5D9;
--bg: #F5F7FB;
--bg-soft: #EAF0F8;
--border: #E5EAF2;
--text: #1C2333;
--sub: #4A5568;
--muted: #8A97AE;

/* 카테고리 배지 */
--cat-policy: #6b4f9a;     /* 정책·규제 */
--cat-market: #2c6f5a;     /* 시장·경기 */
--cat-safety: #d94936;     /* 안전·사고 */
--cat-labor:  #c47b3a;     /* 노동·인력 */
--cat-corp:   #4a5568;     /* 종합건설사 */

/* 감정 점 */
--sent-neg: #d94936;
--sent-neu: #8A97AE;
--sent-pos: #2c6f5a;
```

#### 인터랙션 동작

- 검색은 입력 즉시 필터링(debounce 200ms), 제목·요약 부분일치
- 모든 필터(검색·기간·카테고리)는 AND 결합
- 필터 상태는 URL 해시에 반영 → 임원 북마크/공유 가능
  - 예: `#filter=category:안전·사고&period:7d&q=중대재해`
- 카테고리 필터 펼침은 클릭 토글 (모바일은 모달)

#### 반응형

- 640px 이하: 톱 이슈 섹션 카테고리당 3→2건, 필터는 모달, 카드 패딩 축소
- 1120px max-width 컨테이너 (30주년 파일과 동일)

---

## 에러 처리

| 실패 지점 | 처리 |
|---|---|
| Google News RSS 응답 실패 | 해당 키워드 skip, 로그만 |
| Haiku API 실패/타임아웃 | `summary=description[:200]`, `sentiment="neutral"`. 재시도 없음 |
| Haiku JSON 파싱 실패 | 같은 폴백 |
| 클러스터링 실패 | `cluster_id = link 해시` 폴백 (실질 미클러스터) |
| `weekly.json` 없음/파싱 실패 | 사이트에서 주간 요약 섹션 자체 숨김 |
| `articles.json` 비어있음 | 기존 empty state |
| 신규 필드 누락 (구버전 데이터) | 클라이언트에서 옵셔널 처리 (`?? 기본값`) |

원칙: **임원 사이트가 절대 깨지지 않는다**. 어떤 실패도 콘솔/로그에 남기고 화면은 조용히 폴백.

---

## 테스트

```
tests/
  test_enrich.py
    - test_normalize_title              (매체명·구두점 제거)
    - test_cluster_articles_exact       (정규화 제목 동일)
    - test_cluster_articles_jaccard     (자카드 0.85)
    - test_calc_importance              (각 가산 조건별)
    - test_enrich_haiku_fallback        (모킹: API 실패)
    - test_enrich_json_parse_fallback   (잘못된 JSON 응답)
  test_weekly_summary.py
    - test_select_top_clusters          (importance 정렬, cluster 중복 제거)
    - test_select_fallback_threshold    (5건 미만 시 임계 확장)
    - test_weekly_prompt_format
  test_crawler.py
    - test_category_assignment          (어느 카테고리에서 왔는지)
  test_migration.py
    - 기존 articles.json 샘플 → 신규 스키마 변환
```

Haiku 호출은 모두 모킹. 실제 API는 호출 안 함.

프론트엔드는 자동 테스트 없음. 수동 체크리스트:
- 빈 데이터 / 1건 / 100건 / 카테고리별 0건
- 모바일 / 데스크탑 / 태블릿
- 검색 즉시 반영 / URL 해시 북마크 / 공유 링크

---

## 운영 / 마이그레이션

### 롤아웃 순서

1. **백엔드 변경 + 마이그레이션** (사이트 영향 없음)
   - `enrich.py`, `weekly_summary.py`, 테스트 추가
   - `scripts/migrate_articles.py` 1회 수동 실행 (백업 후)
   - 마이그레이션은 기존 데이터에 다음 기본값 채움:
     - `category` = 키워드로 역추론 ("(미분류)" 폴백 가능)
     - `sentiment = "neutral"`, `importance = 0`
     - `cluster_id = link 해시`, `is_company = keyword in COMPANY_KEYWORDS`
     - `publisher = ""`, `title_clean = title`
2. **프론트엔드 개편 1회 배포** — 신규 데이터 형태 활용
3. **주간 요약 cron 추가** — 첫 카드는 다음 일요일 이후

### cron

기존: 매시간 17분 (변경 없음)
추가: 일요일 23시 `python -m weekly_summary`

### 임원 공개 전 체크리스트

- 신규 데이터로 7일 이상 누적 운영
- 톱 이슈 / 감정 분포 / 클러스터링 결과 눈으로 검증
- 명백한 오분류(예: 호재인데 부정) 있으면 프롬프트 보정
- 그 후 임원 URL 공유

### 비용

| 호출 | 빈도 | 모델 | 추정 |
|---|---|---|---|
| enrich (요약+감정) | 신규 기사 매건 | Haiku 4.5 | ~$0.02/일 |
| weekly summary | 주 1회 | Haiku 4.5 | ~$0.005/주 |

**월 약 $0.7** 수준 — 무시 가능.
