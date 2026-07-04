# 대시보드 탭 발행일 기준 + 달력일 + 발행일순 정렬 설계

**작성일:** 2026-07-04
**상태:** 설계 확정 대기 → 구현 계획(writing-plans)로 전환 예정

## 배경 / 문제

대시보드 기간 탭이 **세 축으로 따로 놀아** 사용자에게 혼란을 준다:
- **탭 필터** = `collected_at`(수집시각) 기준 (index.html:904 `inPeriod(a.collected_at)`)
- **목록 순서** = 저장순(수집 최신순), 시간 정렬 없음
- **카드 표시 시간** = `published_at`(발행시각)

그래서 (1) "오늘"이 지난 24h 롤링이라 "어제"(있다면 달력)와 겹치고, (2) 늦게 수집된 옛 기사가 "오늘"에 오래된 발행일로 뜨며, (3) 목록이 발행일 순서가 아니다. 실측상 시각 자체는 KST로 정확(collected_at 전부 +09:00, published_at tz-aware)하나 **필터·정렬·표시 축이 어긋난** 게 원인이다.

## 목표

탭 필터·정렬을 **발행일 기준**으로 통일하고 오늘/어제를 **달력일로 분리(겹침 제거)**해, "오늘=오늘 발행된 기사"라는 직관과 화면을 일치시킨다.

### 비목표

- 백엔드/수집 로직 변경 없음(프론트 index.html 전용).
- collected_at 저장 방식 변경 없음.

## 상세 설계 (index.html 전용)

### 1. 기준 날짜(effective date)

기사의 대표 시각 = **`published_at` 우선, 없으면 `collected_at`**. 탭 필터·정렬 모두 이 값 사용. 헬퍼:

```js
function effectiveDate(a) { return a.published_at || a.collected_at || ''; }
```

발행일이 있는 기사는 발행 기준, 없는 기사(포털 등)는 수집 기준으로 자연 폴백.

### 2. 탭 의미

`inPeriod(iso)`를 다음으로 정리(날짜범위 from/to 분기는 기존 유지):

- **오늘**(period `1`) = 달력상 오늘: `t >= 오늘0시`.
- **어제**(period `yesterday`) = 달력상 어제: `어제0시 <= t < 오늘0시`. (오늘과 disjoint)
- **7일**(`7`) / **1개월**(`30`) = 최근 N일 롤링: `Date.now() - t <= N*86400000`.
- **전체**(`all`) = 항상 true.

오늘0시 = `new Date(now.getFullYear(), now.getMonth(), now.getDate())` (브라우저 로컬=KST 기준 자정).

### 3. 호출부 — effective date 전달

`inPeriod(a.collected_at)` 두 곳을 `inPeriod(effectiveDate(a))`로 교체:
- `filtered()` (index.html:904)
- 카운트 계산부 (index.html:933 `inPeriod(a.collected_at)`)

날짜범위(from/to) 모드도 effectiveDate 로 필터 → 발행일 기준 일관.

### 4. 발행일순 정렬

`filtered()` 반환 목록을 **effective date 내림차순** 정렬(최신 발행 먼저). 발행일 없는 기사는 collected_at 으로 정렬 참여.

```js
function filtered() {
  return allArticles
    .filter(a => inPeriod(effectiveDate(a)) && matchesGroup(a) && matchesQuery(a))
    .sort((x, y) => effectiveDate(y).localeCompare(effectiveDate(x)));
}
```

(ISO 문자열은 사전식 정렬 = 시간 정렬. tz 오프셋이 섞여도 대부분 +09:00 이라 실무상 정확; 정밀히 하려면 Date 비교로 대체 가능하나 YAGNI.)

### 5. 검증

- JS 하네스 없음 → **수동 확인**(브라우저): 오늘/어제 안 겹침, 각 탭이 발행일 기준, 목록이 발행일 최신순.
- **실데이터 파이썬 재현**: 오늘/어제 탭 집합이 disjoint 인지, effective date desc 정렬이 맞는지 로컬 articles.json 으로 검증.

## 파일 영향

| 파일 | 변경 |
|------|------|
| `index.html` (수정) | `effectiveDate()` 추가, `inPeriod` 오늘/어제 달력 분기, 호출부 2곳 effectiveDate, `filtered()` 발행일 desc 정렬 |

## 미해결 / 배포 때 결정

- 정렬을 문자열 localeCompare 로 할지 Date 비교로 할지 — 우선 문자열(단순), 문제 시 Date.
- GitHub Pages 캐시 지연 감안(배포 후 수 분).
