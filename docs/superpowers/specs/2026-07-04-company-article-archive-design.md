# 조합 기사 아카이브 설계

**작성일:** 2026-07-04
**상태:** 설계 확정 대기 → 구현 계획(writing-plans)로 전환 예정

## 배경 / 문제

`article_store.save_articles`는 `is_company`(조합·협회) 기사를 **무기한 보존**한다(article_store.py:160). 현재 articles.json 1998건 중 **785건(39%)이 조합 기사**이고, 2026-04-19부터 2.5개월간 월 ~300건 페이스로 누적 중이다. 이대로면 1년 내 `MAX_ARTICLES=2000` 상한을 조합 기사가 잠식해 대시보드가 무한정 무거워진다.

조합 기사는 홍보 관점에서 **하나도 버릴 수 없다**. 따라서 전체를 잃지 않으면서 대시보드 볼륨만 줄이는 구조가 필요하다.

## 목표

- 조합 기사 **전 기간을 제목+링크 리스트로 영구 보존**하는 아카이브 페이지를 만든다.
- 메인 대시보드에는 **최근 30일** 조합 기사만 전체 카드로 남기고, 그 이전은 아카이브(제목+링크)에서만 본다.
- 결과: articles.json 볼륨이 유계(bounded)가 되고, 조합 기사는 아카이브에 100% 남는다.

### 비목표 (이번 스코프 아님)

- 메인 대시보드의 정렬/시간축 정리(수집순 vs 발행순) — 별개 후속 작업.
- 비-조합 기사 보존정책 변경(기존 유지).
- 아카이브 검색/필터 UI — 이번엔 월별 그룹 + 제목링크 리스트까지. (YAGNI)

## 상세 설계

### 1. 데이터: `archive.json` + `archive_store.py`

**`archive.json`** — 조합 기사의 가벼운 영구 목록. 항목 스키마:

```json
{"title": "제목", "link": "https://...", "date": "2026-07-03T13:57:00+09:00", "keyword": "기계설비건설공제조합"}
```

- `title`: `title_clean` 우선, 없으면 `title`.
- `date`: `published_at` 우선, 없으면 `collected_at`.
- **link 기준 중복 제거**, 삭제·보존기간 없음(영구). 안전 상한 `MAX_ARCHIVE = 20000`(초과 시 오래된 것부터 컷 — 실질적으로 안 닿음, anti-runaway).

**`archive_store.py`** (신규):

```python
def append_articles(articles: list) -> None:
    """articles 중 is_company 인 것을 archive.json 에 lean 형태로 추가(link 중복 제거)."""
```

- 기존 archive.json 로드 → 이미 있는 link 는 건너뜀 → 신규 is_company 만 lean 변환해 append → 저장.
- 파일 없으면 빈 리스트로 시작. JSON 파싱 실패 시 로그 후 빈 리스트(기존 파일 덮어쓰지 않도록 주의: 파싱 실패 시 append 중단하고 반환).

### 2. `article_store.save_articles` — 조합 기사 30일 보존

현재(160행): `if a.get("is_company"): company.append(a); continue` — 무기한. 이를 **30일 보존**으로 변경:

- 상수 추가: `RETENTION_DAYS_COMPANY = 30`.
- 조합 기사도 `collected_at` 이 `now - 30일` 보다 오래면 제외(비-조합 `RETENTION_DAYS=60` 로직과 동일 패턴). 시각 파싱 실패 시 보존(기존 관례).
- 캡 로직: 조합 기사는 별도 캡 없이 30일 이내 전부 유지(중요 카테고리라 캡 안 씌움). `MAX_ARTICLES` 전체 상한은 유지.

**전제:** 이 변경은 archive.json 시딩(아래 배포 5) **이후**에만 안전하다 — 아카이브에 없는 조합 기사가 pruning 으로 사라지면 안 되므로.

### 3. `main.py` — 아카이브 적재

`add_articles(deduped)` 호출 지점(main.py:49 부근)에 `archive_store.append_articles(deduped)` 추가. `deduped` 전체를 넘기고 archive_store 내부에서 is_company 만 거른다. 순서: 아카이브 적재를 add_articles(보존 pruning 발생) **전에** 수행해 유실 방지.

### 4. `archive.html` — 아카이브 페이지

신규 정적 페이지. `archive.json` 을 fetch 해 렌더:

- **월별 그룹**(예: `2026년 6월`), 그룹 내 **발행일 기준 최신순**.
- 각 항목: `날짜 · <a href=link target=_blank>제목</a>`.
- 상단에 대시보드로 돌아가는 링크. index.html 헤더에는 `📁 조합 기사 전체보기` → `archive.html` 링크 추가.
- 스타일은 index.html 톤 재사용(최소 인라인 CSS). GitHub Pages(main root)로 서빙되므로 index.html 과 같은 위치.

### 5. 테스트

- `tests/test_archive_store.py`:
  - is_company 만 적재(비-조합 무시).
  - link 중복 제거(기존 + 배치 내).
  - lean 스키마(title=title_clean 우선, date=published_at 우선).
  - archive.json 파싱 실패 시 기존 파일 안 건드리고 중단.
- `tests/test_article_store.py`(기존 확장): 조합 기사도 30일 초과면 pruning, 30일 이내면 보존.
- `archive.html`: JS 하네스 없음 → 수동 확인(월별 그룹·제목링크·정렬).

## 파일 영향

| 파일 | 변경 |
|------|------|
| `archive.json` (신규, 데이터) | 조합 기사 lean 영구 목록 |
| `archive_store.py` (신규) | `append_articles()` — is_company lean 적재, link dedup |
| `article_store.py` (수정) | `RETENTION_DAYS_COMPANY=30`, 조합 기사 30일 보존 |
| `main.py` (수정) | `archive_store.append_articles(deduped)` 호출 |
| `archive.html` (신규) | 월별 제목-링크 리스트 페이지 |
| `index.html` (수정) | 헤더에 아카이브 링크 |
| `tests/test_archive_store.py` (신규), `tests/test_article_store.py` (확장) | 단위 테스트 |

## 배포 & 검증 (구현 후)

1. `main` 머지 → push → VM 반영(flock pull).
2. **시딩 1회(VM, flock)**: 현재 articles.json 의 조합 기사 785건을 archive.json 에 적재하는 일회성 스크립트 실행(`archive_store.append_articles(load_articles())`). articles.json 30일 보존은 그 다음 정상 실행에서 적용.
3. archive.json 커밋·push(정상 flow 또는 수동).
4. 대시보드: 조합 기사가 최근 30일치만 카드로 남는지 확인.
5. `archive.html`: 전체 조합 기사가 월별 제목-링크로 뜨는지, 링크 클릭 시 원문 이동 확인.
6. GitHub Pages 캐시 지연 감안(raw.githubusercontent 로 확정 검증 가능).

## 미해결 / 배포 때 결정

- 시딩 스크립트는 일회성 — archive_store.append_articles 재사용(별도 진입점 or `python3 -c`).
- 대시보드 정렬(발행순) 개선은 별개 후속.
