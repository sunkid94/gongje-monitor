# 종합건설사 뉴스 한정어 필터 설계

**작성일:** 2026-07-04
**상태:** 설계 확정 대기 → 구현 계획(writing-plans)로 전환 예정

## 배경 / 문제

최근 7일 수집 1301건 중 **종합건설사 카테고리가 1000건(77%)**, 조합·협회는 88건(7%)뿐이다. 종합건설사 1000건의 대부분은 딱 3개사:

- 삼성중공업 362 · 대우건설 358 · 두산에너빌리티 156 = 876건

원인: 이들은 **회사명만으로 검색**되어 건설·조합과 무관한 뉴스가 대량 유입된다. 제목 실측:

- **삼성중공업**: 조선 56, 수주 50(대부분 조선 수주), 공사 0 · 현장 1 — 사실상 조선/우주항공/데이터센터.
- **두산에너빌리티**: 분양 28, 주가 11, 원전 위주 — 건설·조합 무관.
- **대우건설**: 재건축 12 · 분양 11 · 현장 10 · 공사 8 · 수주 16 — 진짜 건설 뉴스지만 양이 많음.

조합원사라 목록에서 제거할 수는 없다. **활동 뉴스(수주·공사 등)만 남기고 조선·방산·원전·주가·실적 노이즈를 끊어** 대시보드 볼륨을 줄인다.

## 목표

종합건설사 카테고리 기사 중 **건설 활동 한정어가 제목·요약에 없는 기사를 수집 게이트에서 제외**한다. 조합 기사와 여타 카테고리는 영향 없음. 종건사 볼륨 ~876 → ~90건대.

### 설계 선택: "검색-후-필터"(포스트필터) — 멀티검색 아님

대안이던 "회사×한정어 각각 검색"은 (1) 검색어 11→66으로 **구글 요청 6배 → throttling 위험**, (2) `KEYWORD_CANONICAL`이 google에만 적용되고 naver는 exact-phrase 검색이라 **소스 3개를 모두 손봐야 함**. 반면 포스트필터는:

- 회사명 검색·표시 로직 **무변경**(소스 3개 안 건드림), 요청 증가 0.
- crawler 게이트 한 곳에 필터만 추가 → 모든 소스 일괄 적용.
- 결과(활동 뉴스만 남김)는 동일.

트레이드오프: 한정어가 제목·요약에 없는 관련 기사(예 "시공사 선정")는 빠질 수 있음 — 한정어 목록은 config 값이라 쉽게 조정.

## 상세 설계

### 1. `config.py` — 한정어 목록

```python
# 종합건설사 뉴스 한정어 — 이 중 하나가 제목·요약에 있어야 수집(건설 활동 뉴스만).
# 없으면 조선·방산·원전·주가·실적 등 무관 뉴스로 보고 제외.
CORP_QUALIFIERS = ["수주", "공사", "현장", "착공", "준공", "재건축"]
```

### 2. `crawler.py` — 종합건설사 한정어 게이트

`has_blocked_content` 옆에 함수 추가:

```python
from config import ..., CORP_QUALIFIERS, CORP_CATEGORY   # CORP_CATEGORY = "종합건설사"

def lacks_corp_qualifier(article: dict) -> bool:
    """종합건설사 카테고리인데 제목·요약에 활동 한정어가 하나도 없으면 True(제외 대상)."""
    if article.get("category") != CORP_CATEGORY:
        return False
    hay = (article.get("title", "") or "") + " " + (article.get("description", "") or "")
    return not any(q in hay for q in CORP_QUALIFIERS)
```

`fetch_new_articles` 루프의 게이트(is_blocked_domain / has_blocked_content 옆)에 추가:

```python
        if lacks_corp_qualifier(a):
            logger.info("종건사 한정어 없음 제외: %s", (a.get("title", "") or "")[:40])
            continue
```

- `CORP_CATEGORY = "종합건설사"` 는 이미 article_store 에 있으나 crawler 에선 config 로부터 참조(또는 리터럴). 스펙 일관성 위해 `config.py` 에 `CORP_CATEGORY = "종합건설사"` 추가하고 article_store·crawler 가 공유.
- **조합 기사(is_company)·기타 카테고리는 절대 필터 안 됨** — category 조건으로 종건사만.

### 3. 테스트 (`tests/test_crawler.py` 확장)

- 종합건설사 + 한정어 있음(제목 "대우건설 성수 재건축 수주") → 유지.
- 종합건설사 + 한정어 없음(제목 "삼성중공업 조선 수출 호조") → 제외.
- 조합·협회 카테고리(is_company) → 한정어 없어도 유지(필터 대상 아님).
- 정책·규제 등 다른 카테고리 → 한정어 없어도 유지.

### 4. 검증 / 배포

1. `main` 머지 → push → VM 반영(flock pull).
2. **기존 종건사 정리(1회, VM flock)**: 현재 articles.json 의 종합건설사 기사 중 한정어 없는 것 제거(즉시 디클러터). `lacks_corp_qualifier` 재사용하는 일회성 스크립트.
3. 이후 정상 수집에서 종건사 유입이 활동 뉴스로 제한되는지 monitor.log·articles.json 확인.
4. 대시보드에서 종건사 카테고리가 수백→수십으로 줄고 조합 신호가 드러나는지 확인.

## 파일 영향

| 파일 | 변경 |
|------|------|
| `config.py` (수정) | `CORP_QUALIFIERS`, `CORP_CATEGORY = "종합건설사"` 추가 |
| `crawler.py` (수정) | `lacks_corp_qualifier()` + fetch_new_articles 게이트 |
| `tests/test_crawler.py` (확장) | 한정어 게이트 4케이스 |

## 미해결 / 배포 때 결정

- 한정어 목록 튜닝: 배포 후 놓치는 관련 기사 있으면 config 에서 단어 추가(예 시공·분양·수주 등).
- 삼성중공업 "수주"에 조선 수주 일부 잔존 — 심하면 그 회사만 별도 처리(후속).
- 기존 종건사 대량 정리는 배포 2단계 일회성.
