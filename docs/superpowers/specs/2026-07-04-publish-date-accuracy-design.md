# 발행일 정확도 개선 — 포털 파서 확장 + 폴백 표시 설계

**작성일:** 2026-07-04
**상태:** 설계 확정 대기 → 구현 계획(writing-plans)로 전환 예정

## 배경 / 문제

대시보드(index.html)는 기사 시각을 `relativeTime(a.published_at || a.collected_at)`로 표시한다(index.html:834). 즉 **발행일(`published_at`)이 있으면 발행 기준, 없으면 수집시각(`collected_at`)으로 폴백**한다. 발행일이 있는 기사는 "N시간 전"과 "발행 날짜"가 모두 `published_at`에서 나와 일치한다.

문제는 **발행일이 없는 기사(articles.json 2000건 중 333건, 16%)**:
- "N시간 전"이 **수집시각 기준**으로 나와, 오래 전 발행된 기사를 우리가 방금 수집하면 "방금 전"처럼 보이는 **속보 착시**가 생긴다(홍보 관점 리스크).
- 발행일 자체가 표시되지 않는다.

발행일 없는 333건은 대부분 **포털/아그리게이터 경유** 기사다: 네이트 134, 다음(v.daum.net) 27, MSN 8 등. 실측으로 원인을 판별했다:

- **구글 URL 디코딩은 정상**(원문 포털 URL 획득, HTTP 200). 실패 원인은 디코딩이 아니라 **발행일 위치**다.
- `pub_date._extract_published_time`은 표준 메타 5종(`article:published_time`, `itemprop=datePublished`, `name=pubdate`, `<time datetime>`)만 파싱하는데, 포털은 그 바깥에 발행일을 둔다:
  - **네이트**: `<span class="firstDate">기사전송 <em>2026-07-03 13:57</em></span>` (KST, 타임존 없음)
  - **다음**: `<meta property="og:regDate" content="20260624160119">` (`YYYYMMDDHHMMSS`, KST, 타임존 없음)

## 목표

발행일을 **정확히 짚는 것**을 최우선으로, 포털 발행일을 파싱해 커버리지를 올린다(B). 그래도 못 뽑는 잔여분은 **정직하게 "수집 N시간 전"으로 표시**해 속보 착시만 제거한다(A). 네이트(134)+다음(27) 두 규칙으로 빈 것의 약 절반(161건)을 회복한다.

### 비목표

- MSN 및 소량 꼬리 매체(대한경제 13, 국토매일 12 등) 파서 — YAGNI, 나중에.
- index.html의 JS 단위 테스트 하네스 도입 — 이번 범위 아님(수동 확인).
- 발행일 없는 기사 삭제 — 백필은 **채우기만**(아래).

## 상세 설계

### 1. B — 파서 확장 (`pub_date.py`)

`_extract_published_time(html) -> Optional[datetime]`에 표준 패턴 이후 폴백 규칙 2개를 추가한다. 순서: **표준 메타(ISO, tz有) → og:regDate → 네이트 firstDate**. 첫 매치 반환.

```python
from datetime import timezone, timedelta
_KST = timezone(timedelta(hours=9))

_REGDATE_RE = re.compile(
    r'<meta[^>]+property=["\']og:regDate["\'][^>]+content=["\'](\d{14})["\']', re.I)
_NATE_FIRSTDATE_RE = re.compile(
    r'firstDate["\'][^>]*>[^<]*<em>\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', re.I)


def _parse_regdate(html):
    """다음 등: og:regDate YYYYMMDDHHMMSS (KST naive) → KST-aware datetime."""
    m = _REGDATE_RE.search(html)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=_KST)
    except ValueError:
        return None


def _parse_nate_firstdate(html):
    """네이트: firstDate <em>YYYY-MM-DD HH:MM</em> (KST naive) → KST-aware datetime."""
    m = _NATE_FIRSTDATE_RE.search(html)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=_KST)
    except ValueError:
        return None
```

`_extract_published_time`은 기존 `_META_PATTERNS` 루프가 None이면 `_parse_regdate(html) or _parse_nate_firstdate(html)`을 반환한다.

- **KST 부착 근거:** 기존 published_at은 전부 타임존 표기가 있다(실측 naive 0건). 새 값도 `+09:00`을 붙여 tz-aware ISO로 저장 → index.html의 `relativeTime`(tz 인식)·`formatPublishedDate`가 정상 처리, 표시 어긋남 없음.
- 이 값은 `resolve_published_time` → `source_google.fetch`의 `published_at`으로 흐르고, 7일 컷오프 비교(utc-aware)와도 tz-aware라 호환된다.

### 2. 백필 (`backfill_pubdate.py`, 1회성)

기존 스크립트는 발행일 없는 기사에 `resolve_published_time`을 돌려 채우되, **발행일이 7일 초과면 기사를 삭제**한다(backfill_pubdate.py:94-100). 조합 기사(is_company, 무기한 보존 대상)까지 지워질 수 있으므로, 이번 실행은 **"채우기만, 삭제 안 함"** 으로 한다.

- 변경: 7일 초과 기사를 `drops`에 넣지 않고, 해상된 발행일을 그대로 `published_at`에 기록(삭제·seen 추가 로직 비활성).
- best-effort: 디코딩/해상 실패(None)는 기존대로 보존(다음에 자연 채움 없음 — 발행일은 계속 빔).
- 스로틀·백업·중간저장(SAVE_EVERY)은 유지. **푸시 발송 없음**(articles.json/seen.json만 갱신 — 과거 백필이 알림 재발송하지 않는 원칙 유지).
- 실행 위치: **VM에서 flock 걸고 1회**(라이브 articles.json 대상, 정상 push 흐름으로 반영). 로컬 실행 후 커밋은 VM의 잦은 articles.json 갱신과 충돌하므로 지양.

### 3. A — 폴백 표시 (`index.html`)

`renderCard`의 시각 표시(index.html:834-835)를 조건 분기한다:

- `a.published_at` 있음 → 현행 유지: `relativeTime(a.published_at)` + `· 발행 YYYY-MM-DD`.
- `a.published_at` 없음 → `수집 ${relativeTime(a.collected_at)}` 로 표시(발행 아님 명시), 발행 날짜 없음.

즉 발행일 없는 카드는 예: **"수집 3시간 전"**. 속보 착시 제거.

### 4. 테스트 / 검증

- `tests/test_pub_date.py` 확장:
  - `_parse_regdate`: `og:regDate content="20260624160119"` 픽스처 → `2026-06-24 16:01:19+09:00`.
  - `_parse_nate_firstdate`: `<span class="firstDate">기사전송 <em>2026-07-03 13:57</em></span>` → `2026-07-03 13:57+09:00`.
  - `_extract_published_time` 우선순위: 표준 `article:published_time`이 있으면 그걸 먼저, 없고 og:regDate만 있으면 KST 값, 둘 다 없고 네이트만 있으면 네이트 값, 아무 것도 없으면 None.
- `index.html`: JS 테스트 하네스 없음 → **수동 확인**(발행일 없는 카드가 "수집 N시간 전"으로, 있는 카드는 현행대로 뜨는지 브라우저에서 확인).
- 백필: VM 1회 실행 후 로그의 resolved 건수 + 대시보드에서 네이트/다음 기사 발행일 표시 확인.

## 파일 영향

| 파일 | 변경 |
|------|------|
| `pub_date.py` (수정) | `_parse_regdate`, `_parse_nate_firstdate`, `_KST`, 정규식 2종; `_extract_published_time` 폴백 연결 |
| `tests/test_pub_date.py` (확장) | 두 파서 + 우선순위 단위 테스트 |
| `index.html` (수정) | `renderCard` 시각 표시 분기 — 발행일 없으면 "수집 N시간 전" |
| `backfill_pubdate.py` (수정) | "채우기만, 삭제 안 함" 모드 (7일 초과 삭제 비활성) |

## 미해결 / 배포 때 결정

- 백필 실행 타이밍: VM cron 5분/2분 마크 피해 flock으로 1회.
- 회복률: 실행해봐야 정확. 만료된 옛 구글 URL은 디코딩 실패해 못 채울 수 있음(그 잔여분은 A로 표시).
