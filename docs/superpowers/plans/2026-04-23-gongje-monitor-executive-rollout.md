# Gongje Monitor Executive Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이슈 모니터를 임원 공개 수준으로 개편한다 — 카테고리 2단 구조 + AI 중요도·감정·주간 요약 + 30주년 브로슈어 디자인 언어 적용.

**Architecture:** 기존 `crawler → summarizer → articles.json → static site` 파이프라인을 `crawler → enrich → articles.json` 으로 재편하고, 주간 `weekly_summary.py` cron을 추가한다. 프론트엔드는 `index.html` 을 신규 필드(`category`, `importance`, `sentiment`, `cluster_id`, `publisher`, `is_company`)에 맞춰 전면 재작성한다.

**Tech Stack:** Python 3, feedparser, anthropic SDK (Haiku 4.5), pytest, vanilla HTML/CSS/JS (Pretendard Variable).

**Spec:** `docs/superpowers/specs/2026-04-23-gongje-monitor-executive-rollout-design.md`

---

## File Structure

| 파일 | 동작 | 책임 |
|---|---|---|
| `config.py` | Modify | 조합 4개 + 카테고리 dict (5개) 보유 |
| `crawler.py` | Modify | RSS 수집 + category/is_company 부여 |
| `summarizer.py` | Delete | enrich.py로 흡수 |
| `enrich.py` | Create | 정규화·클러스터·Haiku enrich·중요도 |
| `weekly_summary.py` | Create | 주간 5건 cron 요약 |
| `main.py` | Modify | enrich 파이프라인 호출 |
| `weekly.json` | Created at runtime | 주간 카드 캐시 |
| `scripts/migrate_articles.py` | Create | 1회성 기존 데이터 마이그레이션 |
| `index.html` | Rewrite | 30주년 디자인 톤 + 신규 필드 활용 |
| `tests/test_enrich.py` | Create | enrich 유닛 테스트 |
| `tests/test_weekly_summary.py` | Create | 주간 요약 유닛 테스트 |
| `tests/test_crawler.py` | Modify | category 부여 검증 추가 |
| `tests/test_summarizer.py` | Delete | summarizer 제거로 무효 |
| `tests/test_migration.py` | Create | 마이그레이션 스크립트 검증 |

---

## Task 1: config.py 재편

**Files:**
- Modify: `config.py`

- [ ] **Step 1: 현재 config.py 확인**

```bash
cat config.py
```

KEYWORDS (4개) + INDUSTRY_KEYWORDS (9개) 가 flat list로 존재함을 확인.

- [ ] **Step 2: config.py 재작성**

`config.py` 전체 교체:

```python
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.env"))

GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENTS = os.environ["RECIPIENTS"].split(",")

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

# 하위 호환 (crawler 등이 이전 이름 쓸 수 있어 유지)
KEYWORDS = COMPANY_KEYWORDS
INDUSTRY_KEYWORDS = [k for ks in CATEGORY_KEYWORDS.values() for k in ks]
```

- [ ] **Step 3: import 체크**

```bash
python -c "from config import COMPANY_KEYWORDS, CATEGORY_KEYWORDS; print(len(COMPANY_KEYWORDS), sum(len(v) for v in CATEGORY_KEYWORDS.values()))"
```

Expected: `4 23`

- [ ] **Step 4: 기존 테스트 통과 확인**

```bash
pytest tests/ -v
```

Expected: 모두 PASS (아직 crawler는 수정 안 했고 하위 호환 alias 있음)

- [ ] **Step 5: 커밋**

```bash
git add config.py
git commit -m "refactor(config): 조합·카테고리 키워드 구조화 + 종합건설사 10곳 추가"
```

---

## Task 2: crawler.py — category/is_company 부여

**Files:**
- Modify: `crawler.py`
- Modify: `tests/test_crawler.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_crawler.py` 맨 아래에 추가:

```python
def test_fetch_news_rss_attaches_category_for_company_keyword():
    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])):
        import crawler
        import importlib
        importlib.reload(crawler)
        result = crawler.fetch_news_rss("기계설비건설공제조합", category="조합", is_company=True)

    assert result[0]["category"] == "조합"
    assert result[0]["is_company"] is True


def test_fetch_news_rss_attaches_category_for_industry_keyword():
    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])):
        import crawler
        import importlib
        importlib.reload(crawler)
        result = crawler.fetch_news_rss("건설 PF", category="시장·경기", is_company=False)

    assert result[0]["category"] == "시장·경기"
    assert result[0]["is_company"] is False


def test_fetch_new_articles_uses_category_keywords_dict():
    import crawler
    import importlib

    mock_dt = _make_datetime_mock()
    test_category_keywords = {"시장·경기": ["건설 PF"]}

    importlib.reload(crawler)

    with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])), \
         patch("crawler.COMPANY_KEYWORDS", []), \
         patch("crawler.CATEGORY_KEYWORDS", test_category_keywords):
        crawler.datetime = mock_dt
        result = crawler.fetch_new_articles(set())

    assert len(result) == 1
    assert result[0]["category"] == "시장·경기"
    assert result[0]["is_company"] is False
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/test_crawler.py -v
```

Expected: 3개 신규 테스트 FAIL (`category` 파라미터 없음 / KeyError).

- [ ] **Step 3: crawler.py 전체 교체**

```python
import calendar
from datetime import datetime, timedelta
from urllib.parse import quote

import feedparser

from config import CATEGORY_KEYWORDS, COMPANY_KEYWORDS

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={}&hl=ko&gl=KR&ceid=KR:ko"


def fetch_news_rss(keyword: str, category: str, is_company: bool) -> list:
    feed = feedparser.parse(GOOGLE_NEWS_RSS.format(quote(keyword)))
    articles = []
    for entry in feed.entries:
        articles.append({
            "keyword": keyword,
            "category": category,
            "is_company": is_company,
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "description": entry.get("summary", ""),
            "published_parsed": entry.get("published_parsed"),
        })
    return articles


def fetch_new_articles(seen: set) -> list:
    cutoff = datetime.now() - timedelta(hours=24)
    articles = []
    collected_links = set(seen)

    sources = [(kw, "조합", True) for kw in COMPANY_KEYWORDS]
    for category, kws in CATEGORY_KEYWORDS.items():
        sources.extend((kw, category, False) for kw in kws)

    for keyword, category, is_company in sources:
        for item in fetch_news_rss(keyword, category, is_company):
            if item["link"] in collected_links:
                continue
            pub_struct = item.pop("published_parsed")
            if pub_struct:
                try:
                    pub_dt = datetime.fromtimestamp(calendar.timegm(pub_struct))
                    if pub_dt < cutoff:
                        continue
                except (ValueError, TypeError, OverflowError):
                    pass
            articles.append(item)
            collected_links.add(item["link"])
    return articles
```

- [ ] **Step 4: 기존 테스트 호출부 업데이트**

`tests/test_crawler.py` 상단 쪽 `test_fetch_news_rss_returns_articles` 및 `test_fetch_new_articles_excludes_seen_urls`, `test_fetch_new_articles_includes_unseen_urls`, `test_fetch_new_articles_excludes_old_articles` 에서 `crawler.KEYWORDS`, `crawler.INDUSTRY_KEYWORDS` 참조를 전부 `crawler.COMPANY_KEYWORDS`, `crawler.CATEGORY_KEYWORDS` 로 교체. 예:

```python
# BEFORE
with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])), \
     patch("crawler.KEYWORDS", ["기계설비건설공제조합"]), \
     patch("crawler.INDUSTRY_KEYWORDS", []):

# AFTER
with patch("crawler.feedparser.parse", return_value=_mock_feed([MOCK_FEED_ENTRY])), \
     patch("crawler.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
     patch("crawler.CATEGORY_KEYWORDS", {}):
```

`test_fetch_news_rss_returns_articles`는 `crawler.fetch_news_rss("기계설비건설공제조합")` 호출부에 파라미터 추가:

```python
result = crawler.fetch_news_rss("기계설비건설공제조합", category="조합", is_company=True)
```

- [ ] **Step 5: 테스트 재실행**

```bash
pytest tests/test_crawler.py -v
```

Expected: 전부 PASS.

- [ ] **Step 6: 커밋**

```bash
git add crawler.py tests/test_crawler.py
git commit -m "feat(crawler): 카테고리·is_company 필드 부여"
```

---

## Task 3: enrich.py — 파싱 헬퍼 (normalize_title, extract_publisher)

**Files:**
- Create: `enrich.py`
- Create: `tests/test_enrich.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_enrich.py` 신규 파일:

```python
from enrich import normalize_title, extract_publisher


def test_normalize_title_strips_publisher_suffix():
    assert normalize_title("현대건설 사우디 수주 확대 - 조선비즈") == "현대건설사우디수주확대"


def test_normalize_title_removes_whitespace_and_punctuation():
    assert normalize_title('"태영건설" 워크아웃, 1주년…') == "태영건설워크아웃1주년"


def test_normalize_title_handles_no_suffix():
    assert normalize_title("그냥 제목") == "그냥제목"


def test_normalize_title_handles_multiple_dashes():
    # 마지막 " - " 만 제거
    assert normalize_title("A-B 논란 - 매경") == "ab논란"


def test_extract_publisher_returns_suffix():
    assert extract_publisher("현대건설 사우디 수주 확대 - 조선비즈") == "조선비즈"


def test_extract_publisher_returns_empty_when_no_suffix():
    assert extract_publisher("그냥 제목") == ""


def test_extract_publisher_trims_whitespace():
    assert extract_publisher("제목 -  머니투데이  ") == "머니투데이"
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/test_enrich.py -v
```

Expected: FAIL with `ImportError: cannot import name 'normalize_title' from 'enrich'`.

- [ ] **Step 3: enrich.py 신규 생성 (최소 구현)**

```python
import re


_PUBLISHER_SUFFIX_RE = re.compile(r"\s+-\s+([^-]+?)\s*$")


def extract_publisher(title: str) -> str:
    m = _PUBLISHER_SUFFIX_RE.search(title)
    return m.group(1).strip() if m else ""


def normalize_title(title: str) -> str:
    title = _PUBLISHER_SUFFIX_RE.sub("", title)
    return re.sub(r"[\s\W_]+", "", title.lower())
```

- [ ] **Step 4: 테스트 재실행 — PASS 확인**

```bash
pytest tests/test_enrich.py -v
```

Expected: 7개 PASS.

- [ ] **Step 5: 커밋**

```bash
git add enrich.py tests/test_enrich.py
git commit -m "feat(enrich): normalize_title, extract_publisher 헬퍼"
```

---

## Task 4: enrich.py — cluster_articles

**Files:**
- Modify: `enrich.py`
- Modify: `tests/test_enrich.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_enrich.py` 끝에 추가:

```python
from enrich import cluster_articles


def _art(title, link):
    return {"title": title, "link": link, "description": ""}


def test_cluster_articles_assigns_cluster_id():
    articles = [_art("제목A", "l1"), _art("제목B", "l2")]
    result = cluster_articles(articles)
    assert "cluster_id" in result[0]
    assert result[0]["cluster_id"] != result[1]["cluster_id"]


def test_cluster_articles_groups_exact_normalized_match():
    articles = [
        _art("태영건설 워크아웃 1주년 - 조선비즈", "l1"),
        _art("태영건설 워크아웃 1주년 - 매경", "l2"),
    ]
    result = cluster_articles(articles)
    assert result[0]["cluster_id"] == result[1]["cluster_id"]


def test_cluster_articles_groups_jaccard_similar():
    # 토큰 자카드 >= 0.85 → 같은 cluster
    articles = [
        _art("태영건설 워크아웃 1주년 재무 개선 미흡", "l1"),
        _art("태영건설 워크아웃 1주년 재무개선 미흡", "l2"),  # 공백 1개 차이
    ]
    result = cluster_articles(articles)
    assert result[0]["cluster_id"] == result[1]["cluster_id"]


def test_cluster_articles_keeps_different_apart():
    articles = [
        _art("태영건설 워크아웃 1주년", "l1"),
        _art("현대건설 사우디 수주", "l2"),
    ]
    result = cluster_articles(articles)
    assert result[0]["cluster_id"] != result[1]["cluster_id"]


def test_cluster_articles_cluster_id_is_4char_hex():
    articles = [_art("제목", "l1")]
    result = cluster_articles(articles)
    assert len(result[0]["cluster_id"]) == 4
    assert all(c in "0123456789abcdef" for c in result[0]["cluster_id"])
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/test_enrich.py::test_cluster_articles_assigns_cluster_id -v
```

Expected: FAIL.

- [ ] **Step 3: cluster_articles 구현 추가**

`enrich.py` 에 추가:

```python
import hashlib


def _tokens(title: str) -> set:
    cleaned = _PUBLISHER_SUFFIX_RE.sub("", title)
    return set(re.findall(r"\w+", cleaned.lower()))


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _cluster_id(norm: str) -> str:
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:4]


def cluster_articles(articles: list) -> list:
    """각 기사에 cluster_id 부여. 정규화 제목 완전 일치 또는 토큰 자카드 0.85 이상이면 동일 cluster."""
    clusters = []  # list of (representative_norm, cluster_id, token_set)
    result = []

    for a in articles:
        norm = normalize_title(a["title"])
        tokens = _tokens(a["title"])
        matched_id = None

        for rep_norm, cid, rep_tokens in clusters:
            if norm == rep_norm or _jaccard(tokens, rep_tokens) >= 0.85:
                matched_id = cid
                break

        if matched_id is None:
            matched_id = _cluster_id(norm or a["link"])
            clusters.append((norm, matched_id, tokens))

        result.append({**a, "cluster_id": matched_id})

    return result
```

- [ ] **Step 4: 테스트 재실행**

```bash
pytest tests/test_enrich.py -v
```

Expected: 12개 PASS.

- [ ] **Step 5: 커밋**

```bash
git add enrich.py tests/test_enrich.py
git commit -m "feat(enrich): 정규화 제목 + 자카드 0.85 기반 cluster_articles"
```

---

## Task 5: enrich.py — Haiku enrich (summary + sentiment)

**Files:**
- Modify: `enrich.py`
- Modify: `tests/test_enrich.py`

- [ ] **Step 1: 테스트 추가**

```python
import json
from unittest.mock import MagicMock, patch


def test_enrich_article_returns_summary_and_sentiment():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "요약입니다.", "sentiment": "negative"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용")

    assert result == {"summary": "요약입니다.", "sentiment": "negative"}


def test_enrich_article_falls_back_on_api_error():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API down")
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용이 200자 이상이어야 하는가 아닌가 테스트")

    assert result["sentiment"] == "neutral"
    assert "내용" in result["summary"]


def test_enrich_article_falls_back_on_invalid_json():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="This is not JSON at all.")]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "원문 내용")

    assert result["sentiment"] == "neutral"
    assert result["summary"] == "원문 내용"[:200]


def test_enrich_article_caps_description_fallback_at_200():
    long_desc = "가" * 500
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("down")
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", long_desc)

    assert len(result["summary"]) == 200


def test_enrich_article_normalizes_invalid_sentiment():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"summary": "S", "sentiment": "mixed"}')]
    )
    with patch("enrich._get_client", return_value=mock_client):
        from enrich import enrich_article
        result = enrich_article("제목", "내용")

    assert result["sentiment"] == "neutral"
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/test_enrich.py -k enrich_article -v
```

Expected: FAIL (enrich_article 없음).

- [ ] **Step 3: enrich.py 에 구현 추가**

```python
import json
import logging
import os
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

_VALID_SENTIMENTS = {"positive", "neutral", "negative"}
_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


_ENRICH_PROMPT = """다음 뉴스 기사를 분석해 JSON으로 답하세요.

제목: {title}
내용: {description}

판단 기준:
- 감정 톤은 "건설업계 전반과 기계설비건설공제조합" 시점에서 평가합니다.
  · positive: 업계 호재 (수주 증가, 규제 완화, 시장 확대 등)
  · negative: 업계 악재 (사고, 규제 강화, PF 위기, 부정 이슈 등)
  · neutral: 사실 보도, 양면적, 판단 어려움
- 요약은 한국어 2~3줄, 핵심만.

JSON 형식 (다른 텍스트 없이 이것만):
{{"summary": "...", "sentiment": "positive|neutral|negative"}}"""


def enrich_article(title: str, description: str) -> dict:
    fallback = {
        "summary": (description or "")[:200],
        "sentiment": "neutral",
    }
    try:
        msg = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": _ENRICH_PROMPT.format(title=title, description=description)}],
        )
        raw = msg.content[0].text.strip()
        data = json.loads(raw)
        sentiment = data.get("sentiment", "neutral")
        if sentiment not in _VALID_SENTIMENTS:
            sentiment = "neutral"
        return {
            "summary": data.get("summary", "").strip() or fallback["summary"],
            "sentiment": sentiment,
        }
    except Exception as e:
        logger.warning("enrich_article 폴백 (title=%s): %s", title[:30], e)
        return fallback
```

- [ ] **Step 4: 테스트 PASS 확인**

```bash
pytest tests/test_enrich.py -v
```

Expected: 전체 PASS.

- [ ] **Step 5: 커밋**

```bash
git add enrich.py tests/test_enrich.py
git commit -m "feat(enrich): Haiku 요약+감정 통합 호출 (폴백 포함)"
```

---

## Task 6: enrich.py — calc_importance

**Files:**
- Modify: `enrich.py`
- Modify: `tests/test_enrich.py`

- [ ] **Step 1: 테스트 추가**

```python
from datetime import datetime, timedelta


def test_calc_importance_minimum_is_zero():
    from enrich import calc_importance
    art = {"is_company": False, "sentiment": "neutral", "collected_at": "2020-01-01T00:00:00"}
    assert calc_importance(art, cluster_size=1, now=datetime(2026, 4, 23)) == 1  # cluster_size 1 → +1


def test_calc_importance_company_plus_negative_plus_recent():
    from enrich import calc_importance
    now = datetime(2026, 4, 23, 12, 0, 0)
    recent = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    art = {"is_company": True, "sentiment": "negative", "collected_at": recent}
    # 5 (company) + 3 (neg) + 1 (cluster_size 1) + 2 (recent) = 11 → round(11*10/15)=7
    assert calc_importance(art, cluster_size=1, now=now) == 7


def test_calc_importance_caps_cluster_size_at_5():
    from enrich import calc_importance
    now = datetime(2026, 4, 23)
    art = {"is_company": False, "sentiment": "neutral", "collected_at": "2020-01-01T00:00:00"}
    # cluster_size 10 → 5 (capped) / 15 * 10 = 3.33 → round = 3
    assert calc_importance(art, cluster_size=10, now=now) == 3


def test_calc_importance_max_is_10():
    from enrich import calc_importance
    now = datetime(2026, 4, 23, 12, 0, 0)
    recent = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    art = {"is_company": True, "sentiment": "negative", "collected_at": recent}
    # 5 + 3 + 5 (cluster cap) + 2 = 15 → 10
    assert calc_importance(art, cluster_size=20, now=now) == 10


def test_calc_importance_handles_missing_collected_at():
    from enrich import calc_importance
    now = datetime(2026, 4, 23)
    art = {"is_company": False, "sentiment": "positive"}  # no collected_at
    # 0 + 0 + 1 + 0 = 1 → round(1*10/15) = 1
    assert calc_importance(art, cluster_size=1, now=now) == 1
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/test_enrich.py -k calc_importance -v
```

Expected: FAIL.

- [ ] **Step 3: 구현 추가**

`enrich.py` 에 추가:

```python
from datetime import datetime, timedelta


def calc_importance(article: dict, cluster_size: int, now: Optional[datetime] = None) -> int:
    if now is None:
        now = datetime.now()

    score = 0
    if article.get("is_company"):
        score += 5
    if article.get("sentiment") == "negative":
        score += 3
    score += min(cluster_size, 5)

    collected_at_str = article.get("collected_at")
    if collected_at_str:
        try:
            collected = datetime.strptime(collected_at_str, "%Y-%m-%dT%H:%M:%S")
            if (now - collected) < timedelta(hours=24):
                score += 2
        except ValueError:
            pass

    return min(round(score * 10 / 15), 10)
```

- [ ] **Step 4: 테스트 PASS 확인**

```bash
pytest tests/test_enrich.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add enrich.py tests/test_enrich.py
git commit -m "feat(enrich): 규칙 기반 중요도 스코어 0~10"
```

---

## Task 7: enrich.py — enrich_articles 파이프라인

**Files:**
- Modify: `enrich.py`
- Modify: `tests/test_enrich.py`

- [ ] **Step 1: 테스트 추가**

```python
def test_enrich_articles_full_pipeline():
    articles = [
        {
            "keyword": "기계설비건설공제조합",
            "category": "조합",
            "is_company": True,
            "title": "기계설비건설공제조합 신규 사업 - 조선비즈",
            "link": "http://x/1",
            "description": "신규 사업 발표",
        },
        {
            "keyword": "기계설비건설공제조합",
            "category": "조합",
            "is_company": True,
            "title": "기계설비건설공제조합 신규 사업 - 매경",
            "link": "http://x/2",
            "description": "신규 사업 발표",
        },
    ]

    with patch("enrich.enrich_article", return_value={"summary": "AI 요약", "sentiment": "positive"}):
        from enrich import enrich_articles
        result = enrich_articles(articles)

    # 같은 기사 묶임 (cluster_size=2)
    assert result[0]["cluster_id"] == result[1]["cluster_id"]
    # publisher 추출됨
    assert result[0]["publisher"] == "조선비즈"
    assert result[1]["publisher"] == "매경"
    # title_clean 은 매체명 제거됨
    assert result[0]["title_clean"] == "기계설비건설공제조합 신규 사업"
    # summary, sentiment 들어감
    assert result[0]["summary"] == "AI 요약"
    assert result[0]["sentiment"] == "positive"
    # importance 계산됨
    assert isinstance(result[0]["importance"], int)
    assert 0 <= result[0]["importance"] <= 10


def test_enrich_articles_preserves_original_fields():
    articles = [{
        "keyword": "kw", "category": "조합", "is_company": False,
        "title": "제목", "link": "l1", "description": "d",
        "extra": "keep me",
    }]
    with patch("enrich.enrich_article", return_value={"summary": "s", "sentiment": "neutral"}):
        from enrich import enrich_articles
        result = enrich_articles(articles)

    assert result[0]["extra"] == "keep me"
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/test_enrich.py -k enrich_articles -v
```

Expected: FAIL (`enrich_articles` 없음).

- [ ] **Step 3: 구현 추가**

`enrich.py` 에 추가:

```python
from collections import Counter


def enrich_articles(articles: list) -> list:
    if not articles:
        return []

    # 1) 클러스터링
    clustered = cluster_articles(articles)
    cluster_sizes = Counter(a["cluster_id"] for a in clustered)

    # 2) publisher, title_clean 부여 + Haiku enrich
    enriched = []
    now = datetime.now()
    for a in clustered:
        title = a["title"]
        publisher = extract_publisher(title)
        title_clean = _PUBLISHER_SUFFIX_RE.sub("", title)
        ai = enrich_article(title_clean, a.get("description", ""))
        out = {
            **a,
            "publisher": publisher,
            "title_clean": title_clean,
            "summary": ai["summary"],
            "sentiment": ai["sentiment"],
        }
        out["importance"] = calc_importance(out, cluster_sizes[a["cluster_id"]], now=now)
        enriched.append(out)

    return enriched
```

- [ ] **Step 4: 테스트 PASS 확인**

```bash
pytest tests/test_enrich.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add enrich.py tests/test_enrich.py
git commit -m "feat(enrich): enrich_articles 파이프라인 (cluster+publisher+haiku+importance)"
```

---

## Task 8: main.py 통합, summarizer.py 삭제

**Files:**
- Modify: `main.py`
- Modify: `mailer.py` (body에 importance 표시)
- Delete: `summarizer.py`
- Delete: `tests/test_summarizer.py`
- Modify: `tests/test_mailer.py`

- [ ] **Step 1: main.py 교체**

```python
import logging

from article_store import add_articles
from crawler import fetch_new_articles
from enrich import enrich_articles
from mailer import send_email
from seen_store import load_seen, save_seen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    seen = load_seen()
    new_articles = fetch_new_articles(seen)

    if not new_articles:
        logger.info("새 기사 없음. 이메일 미발송.")
        return

    logger.info("새 기사 %d건 발견. enrich 중...", len(new_articles))
    enriched = enrich_articles(new_articles)

    new_urls = {a["link"] for a in enriched}
    send_email(enriched)
    save_seen(seen | new_urls)
    add_articles(enriched)
    logger.info("%d건 이슈 이메일 발송 완료.", len(enriched))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: mailer.py 소폭 수정** (제목/본문에 sentiment·importance 단서 추가)

`build_email_body` 내부 루프를 다음으로 교체:

```python
def build_email_body(articles: list) -> str:
    lines = []
    for a in articles:
        body_text = a.get("summary") or a.get("description", "")
        if not a.get("summary") and len(body_text) > 200:
            body_text = body_text[:200] + "..."

        sentiment_mark = {"negative": "🔴", "positive": "🟢", "neutral": "⚪"}.get(
            a.get("sentiment", "neutral"), "⚪"
        )
        importance = a.get("importance", 0)
        category = a.get("category", "")
        publisher = a.get("publisher", "")
        title = a.get("title_clean") or a.get("title", "")

        meta_parts = [sentiment_mark, f"중요도 {importance}/10"]
        if category:
            meta_parts.append(f"[{category}]")
        if publisher:
            meta_parts.append(publisher)

        lines += [
            "━" * 40,
            " ".join(meta_parts),
            "━" * 40,
            f"제목: {title}",
            f"링크: {a['link']}",
            f"요약: {body_text}",
            "",
        ]
    return "\n".join(lines)
```

- [ ] **Step 3: tests/test_mailer.py — 신규 필드 커버 테스트 1개 추가**

`test_mailer.py` 끝에 추가:

```python
def test_build_email_body_shows_importance_and_sentiment():
    articles = [{
        "keyword": "kw", "title": "t", "title_clean": "t", "link": "l",
        "description": "d", "summary": "s",
        "category": "안전·사고", "sentiment": "negative", "importance": 8,
        "publisher": "조선비즈",
    }]
    with patch("mailer.GMAIL_ADDRESS", "x"), patch("mailer.GMAIL_APP_PASSWORD", "x"), \
         patch("mailer.RECIPIENTS", ["x"]):
        import mailer
        import importlib
        importlib.reload(mailer)
        body = mailer.build_email_body(articles)

    assert "🔴" in body
    assert "8/10" in body
    assert "안전·사고" in body
    assert "조선비즈" in body
```

- [ ] **Step 4: summarizer 관련 파일 삭제**

```bash
git rm summarizer.py tests/test_summarizer.py
```

- [ ] **Step 5: 전체 테스트 실행**

```bash
pytest tests/ -v
```

Expected: 전부 PASS.

- [ ] **Step 6: 실제 실행 검증 (dry-run)**

Haiku API는 실제로 호출됨. 한 번만 돌려 `articles.json` 에 신규 필드 (category, sentiment, importance, cluster_id, publisher, title_clean, is_company) 포함되는지 확인:

```bash
python main.py
python -c "import json; a=json.load(open('articles.json')); print(a[0].keys())"
```

Expected: dict_keys 에 신규 필드 6개 모두 포함.

- [ ] **Step 7: 커밋**

```bash
git add main.py mailer.py tests/test_mailer.py
git commit -m "refactor: summarizer 제거, enrich 파이프라인으로 교체 + 메일에 중요도·감정 표시"
```

---

## Task 9: scripts/migrate_articles.py — 기존 데이터 마이그레이션

**Files:**
- Create: `scripts/migrate_articles.py`
- Create: `tests/test_migration.py`

기존 articles.json에는 신규 필드가 없음. 1회 실행으로 모든 기존 기사에 기본값을 채운다.

- [ ] **Step 1: 테스트 작성**

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def test_migrate_fills_defaults(tmp_path, monkeypatch):
    src = tmp_path / "articles.json"
    old_data = [
        {
            "keyword": "기계설비건설공제조합",
            "title": "조합 신규 사업 - 조선비즈",
            "link": "l1",
            "description": "d",
            "summary": "요약",
            "collected_at": "2026-04-01T12:00:00",
        },
        {
            "keyword": "건설 PF",
            "title": "PF 위기 심화",
            "link": "l2",
            "description": "d",
            "summary": None,
            "collected_at": "2026-04-02T12:00:00",
        },
    ]
    src.write_text(json.dumps(old_data, ensure_ascii=False))

    from migrate_articles import migrate
    migrate(str(src))

    result = json.loads(src.read_text())

    assert result[0]["category"] == "조합"
    assert result[0]["is_company"] is True
    assert result[0]["title_clean"] == "조합 신규 사업"
    assert result[0]["publisher"] == "조선비즈"
    assert result[0]["sentiment"] == "neutral"
    assert result[0]["importance"] == 0
    assert "cluster_id" in result[0]

    assert result[1]["category"] == "시장·경기"
    assert result[1]["is_company"] is False
    assert result[1]["publisher"] == ""


def test_migrate_is_idempotent(tmp_path):
    src = tmp_path / "articles.json"
    old_data = [{
        "keyword": "기계설비건설공제조합",
        "title": "제목",
        "link": "l1",
        "description": "d",
        "summary": "s",
        "collected_at": "2026-04-01T12:00:00",
    }]
    src.write_text(json.dumps(old_data, ensure_ascii=False))

    from migrate_articles import migrate
    migrate(str(src))
    first = json.loads(src.read_text())
    migrate(str(src))
    second = json.loads(src.read_text())

    assert first == second


def test_migrate_unknown_keyword_maps_to_uncategorized(tmp_path):
    src = tmp_path / "articles.json"
    src.write_text(json.dumps([{
        "keyword": "알수없는키워드",
        "title": "t",
        "link": "l",
        "description": "d",
        "summary": None,
        "collected_at": "2026-04-01T12:00:00",
    }]))

    from migrate_articles import migrate
    migrate(str(src))

    result = json.loads(src.read_text())
    assert result[0]["category"] == "(미분류)"
    assert result[0]["is_company"] is False
```

- [ ] **Step 2: scripts 디렉토리 확인 + 테스트 실행**

```bash
mkdir -p scripts
pytest tests/test_migration.py -v
```

Expected: FAIL (`migrate_articles` 모듈 없음).

- [ ] **Step 3: scripts/migrate_articles.py 작성**

```python
"""1회성 마이그레이션: 구 articles.json 에 신규 필드를 채운다.

사용법:
    python scripts/migrate_articles.py                 # articles.json 자동 백업 후 변환
    python scripts/migrate_articles.py path/to/file.json
"""
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import COMPANY_KEYWORDS, CATEGORY_KEYWORDS

_PUBLISHER_SUFFIX_RE = re.compile(r"\s+-\s+([^-]+?)\s*$")


def _lookup_category(keyword: str) -> str:
    if keyword in COMPANY_KEYWORDS:
        return "조합"
    for category, kws in CATEGORY_KEYWORDS.items():
        if keyword in kws:
            return category
    return "(미분류)"


def _migrate_one(article: dict) -> dict:
    if "category" in article and "sentiment" in article:
        return article  # 이미 마이그레이션됨

    keyword = article.get("keyword", "")
    title = article.get("title", "")
    m = _PUBLISHER_SUFFIX_RE.search(title)
    publisher = m.group(1).strip() if m else ""
    title_clean = _PUBLISHER_SUFFIX_RE.sub("", title)

    link = article.get("link", "")
    cluster_id = hashlib.sha1(link.encode("utf-8")).hexdigest()[:4]

    return {
        **article,
        "category": _lookup_category(keyword),
        "is_company": keyword in COMPANY_KEYWORDS,
        "title_clean": title_clean,
        "publisher": publisher,
        "sentiment": "neutral",
        "importance": 0,
        "cluster_id": cluster_id,
    }


def migrate(path: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    migrated = [_migrate_one(a) for a in articles]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(migrated, f, ensure_ascii=False, indent=2)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "articles.json")
    backup = target + ".pre-migration-backup"
    if not os.path.exists(backup):
        shutil.copy2(target, backup)
        print(f"백업 저장: {backup}")
    migrate(target)
    print(f"마이그레이션 완료: {target}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 PASS 확인**

```bash
pytest tests/test_migration.py -v
```

- [ ] **Step 5: 실제 마이그레이션 실행 (신중히)**

```bash
python scripts/migrate_articles.py
python -c "import json; a=json.load(open('articles.json')); print('필드:', list(a[0].keys()))"
```

Expected: 신규 필드 6개 (`category`, `is_company`, `title_clean`, `publisher`, `sentiment`, `importance`, `cluster_id`) 포함 확인.

- [ ] **Step 6: 커밋**

```bash
git add scripts/migrate_articles.py tests/test_migration.py articles.json
git commit -m "feat: 기존 articles.json 신규 스키마로 마이그레이션"
```

---

## Task 10: weekly_summary.py — 주간 요약

**Files:**
- Create: `weekly_summary.py`
- Create: `tests/test_weekly_summary.py`

- [ ] **Step 1: 테스트 작성**

```python
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


def _article(title, importance, cluster_id, category="시장·경기", days_ago=2):
    collected = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "title": title, "title_clean": title,
        "link": f"l-{title}",
        "summary": f"요약-{title}",
        "category": category,
        "cluster_id": cluster_id,
        "importance": importance,
        "collected_at": collected,
        "sentiment": "negative",
    }


def test_select_top_clusters_deduplicates_by_cluster():
    from weekly_summary import select_top_clusters
    arts = [
        _article("A", 9, "c1"),
        _article("A2", 8, "c1"),  # 같은 cluster — 최상위만 채택
        _article("B", 7, "c2"),
    ]
    now = datetime.now()
    result = select_top_clusters(arts, now=now)
    cluster_ids = [a["cluster_id"] for a in result]
    assert cluster_ids.count("c1") == 1


def test_select_top_clusters_respects_7_day_window():
    from weekly_summary import select_top_clusters
    arts = [
        _article("recent", 8, "c1", days_ago=2),
        _article("old", 10, "c2", days_ago=30),
    ]
    now = datetime.now()
    result = select_top_clusters(arts, now=now)
    links = [a["link"] for a in result]
    assert "l-recent" in links
    assert "l-old" not in links


def test_select_top_clusters_fallback_threshold_when_below_5():
    from weekly_summary import select_top_clusters
    # 6 이상 기사가 2개만 있으면 4 이상까지 확장
    arts = [
        _article("high1", 9, "c1"),
        _article("high2", 7, "c2"),
        _article("mid1", 5, "c3"),
        _article("mid2", 4, "c4"),
        _article("mid3", 4, "c5"),
        _article("low", 2, "c6"),
    ]
    now = datetime.now()
    result = select_top_clusters(arts, now=now)
    assert len(result) == 5


def test_generate_weekly_summary_writes_json(tmp_path):
    from weekly_summary import generate_weekly_summary

    arts = [_article("t", 8, f"c{i}") for i in range(5)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(content=[MagicMock(text=json.dumps({
        "period": "2026-04-14 ~ 2026-04-20",
        "items": [
            {"category": "시장·경기", "headline": "태영건설", "brief": "1주년..."},
            {"category": "안전·사고", "headline": "중대재해", "brief": "통과..."},
            {"category": "시장·경기", "headline": "PF", "brief": "확대..."},
            {"category": "정책·규제", "headline": "법개정", "brief": "개정..."},
            {"category": "종합건설사", "headline": "수주", "brief": "확대..."},
        ],
    }))])

    out = tmp_path / "weekly.json"
    with patch("weekly_summary._get_client", return_value=mock_client), \
         patch("weekly_summary.load_articles", return_value=arts):
        generate_weekly_summary(output_path=str(out), now=datetime.now())

    data = json.loads(out.read_text())
    assert len(data["items"]) == 5
    assert data["items"][0]["headline"] == "태영건설"


def test_generate_weekly_summary_handles_api_failure(tmp_path):
    from weekly_summary import generate_weekly_summary

    arts = [_article("t", 8, f"c{i}") for i in range(5)]
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API down")

    out = tmp_path / "weekly.json"
    with patch("weekly_summary._get_client", return_value=mock_client), \
         patch("weekly_summary.load_articles", return_value=arts):
        generate_weekly_summary(output_path=str(out), now=datetime.now())

    # 실패 시 파일 만들지 않음 (기존 주간 카드 유지)
    assert not out.exists()
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/test_weekly_summary.py -v
```

Expected: FAIL (모듈 없음).

- [ ] **Step 3: weekly_summary.py 작성**

```python
"""주간 요약 생성. 일요일 23시 cron.

사용법:
    python weekly_summary.py
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import anthropic

from article_store import load_articles

logger = logging.getLogger(__name__)

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weekly.json")

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


_PROMPT = """다음은 지난 한 주({period}) 동안 수집된 건설업계 핵심 이슈 {count}건입니다.
기계설비건설공제조합 임원에게 보고하는 주간 브리핑이라 가정하고,
각 이슈를 한국어로 2~3줄씩 요약하세요.

{items_block}

JSON 출력 (다른 텍스트 없이):
{{
  "period": "{period}",
  "items": [
    {{"category": "...", "headline": "...", "brief": "..."}},
    ... (총 {count}개)
  ]
}}"""


def select_top_clusters(articles: list, now: datetime, limit: int = 5) -> list:
    cutoff = now - timedelta(days=7)
    window = []
    for a in articles:
        try:
            collected = datetime.strptime(a.get("collected_at", ""), "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
        if collected >= cutoff:
            window.append(a)

    def take_by_threshold(threshold: int) -> list:
        filtered = [a for a in window if a.get("importance", 0) >= threshold]
        filtered.sort(key=lambda x: (-x.get("importance", 0), x.get("collected_at", "")))
        seen_clusters = set()
        picked = []
        for a in filtered:
            cid = a.get("cluster_id")
            if cid in seen_clusters:
                continue
            seen_clusters.add(cid)
            picked.append(a)
            if len(picked) >= limit:
                break
        return picked

    picks = take_by_threshold(6)
    if len(picks) < limit:
        picks = take_by_threshold(4)
    return picks[:limit]


def _build_items_block(articles: list) -> str:
    lines = []
    for i, a in enumerate(articles, 1):
        lines.append(f"이슈 {i} ── [{a.get('category', '')}]")
        lines.append(f"제목: {a.get('title_clean') or a.get('title', '')}")
        lines.append(f"요약: {a.get('summary', '')}")
        lines.append("")
    return "\n".join(lines)


def generate_weekly_summary(output_path: str = OUTPUT_PATH, now: Optional[datetime] = None) -> None:
    if now is None:
        now = datetime.now()

    articles = load_articles()
    top = select_top_clusters(articles, now=now)
    if not top:
        logger.info("주간 요약 대상 기사 없음. skip.")
        return

    period_end = now.strftime("%Y-%m-%d")
    period_start = (now - timedelta(days=6)).strftime("%Y-%m-%d")
    period = f"{period_start} ~ {period_end}"

    prompt = _PROMPT.format(
        period=period,
        count=len(top),
        items_block=_build_items_block(top),
    )

    try:
        msg = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(msg.content[0].text.strip())
    except Exception as e:
        logger.error("주간 요약 생성 실패: %s", e)
        return

    data["generated_at"] = now.strftime("%Y-%m-%dT%H:%M:%S")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("weekly.json 저장: %d건", len(data.get("items", [])))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    generate_weekly_summary()
```

- [ ] **Step 4: 테스트 PASS 확인**

```bash
pytest tests/test_weekly_summary.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add weekly_summary.py tests/test_weekly_summary.py
git commit -m "feat(weekly): 주간 요약 Haiku 생성기"
```

---

## Task 11: index.html — HTML 골격 + 30주년 디자인 시스템

**Files:**
- Modify: `index.html` (전체 재작성)

이후 12~15번 태스크에서 같은 파일을 점진적으로 덮어쓴다. 본 태스크는 **렌더러·스타일 토큰·hero·empty state** 까지만.

- [ ] **Step 1: 기존 index.html 백업 (작업 중 참조용, commit 하지 않음)**

```bash
cp index.html index.html.old-backup
```

- [ ] **Step 2: index.html 전면 교체 (뼈대)**

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>기계설비건설공제조합 이슈 모니터</title>
  <link href="https://cdnjs.cloudflare.com/ajax/libs/pretendard/1.3.9/variable/pretendardvariable.min.css" rel="stylesheet">
  <style>
    :root {
      --navy: #1E3A6F;
      --navy-dark: #142848;
      --navy-deep: #0A1829;
      --blue-accent: #4A7BC8;
      --blue-soft: #7BA4D9;
      --cyan-soft: #9BC5D9;
      --bg: #F5F7FB;
      --bg-soft: #EAF0F8;
      --border: #E5EAF2;
      --text: #1C2333;
      --sub: #4A5568;
      --muted: #8A97AE;
      --white: #FFFFFF;

      --cat-policy: #6b4f9a;
      --cat-market: #2c6f5a;
      --cat-safety: #d94936;
      --cat-labor:  #c47b3a;
      --cat-corp:   #4a5568;
      --cat-co-op:  #1E3A6F;

      --sent-neg: #d94936;
      --sent-neu: #8A97AE;
      --sent-pos: #2c6f5a;
    }

    * { margin: 0; padding: 0; box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      font-family: "Pretendard Variable", "Pretendard", -apple-system, sans-serif;
      color: var(--text);
      background: var(--bg);
      word-break: keep-all;
      -webkit-font-smoothing: antialiased;
    }

    nav {
      position: fixed; top: 0; left: 0; right: 0; z-index: 100;
      padding: 0 40px; height: 64px;
      display: flex; align-items: center; justify-content: space-between;
      background: rgba(255,255,255,0.95);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
    }
    nav .brand { font-size: 13px; font-weight: 800; color: var(--navy); letter-spacing: 1px; }
    nav .last-updated { font-size: 11px; color: var(--muted); letter-spacing: 1px; }

    .hero {
      padding: 140px 24px 60px;
      text-align: center;
      background: var(--white);
      border-bottom: 1px solid var(--border);
    }
    .hero-eyebrow {
      font-size: 11px; font-weight: 800;
      color: var(--navy); letter-spacing: 4px;
      margin-bottom: 18px;
    }
    .hero-title {
      font-size: clamp(32px, 5vw, 52px);
      font-weight: 900; color: var(--navy);
      letter-spacing: -1.5px; line-height: 1.1;
      margin-bottom: 12px;
    }
    .hero-sub {
      font-size: 15px; color: var(--sub); line-height: 1.7;
      max-width: 560px; margin: 0 auto;
    }

    .container { max-width: 1120px; margin: 0 auto; padding: 0 24px; }
    section { padding: 60px 0; }
    .sec-num {
      display: inline-flex; align-items: center; gap: 12px;
      margin-bottom: 20px;
    }
    .sec-num .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--navy); }
    .sec-num .line { width: 40px; height: 1px; background: var(--navy); }
    .sec-num span {
      font-size: 11px; font-weight: 800;
      color: var(--navy); letter-spacing: 4px;
    }
    .sec-head h2 {
      font-size: clamp(24px, 3vw, 32px);
      font-weight: 900; color: var(--navy);
      letter-spacing: -1px; margin-bottom: 40px;
    }

    .empty {
      text-align: center; padding: 80px 20px;
      color: var(--muted); background: var(--white);
      border-radius: 12px; border: 1px solid var(--border);
    }

    footer {
      text-align: center; padding: 40px 20px;
      color: var(--muted); font-size: 12px;
      border-top: 1px solid var(--border);
      background: var(--white);
    }

    @media (max-width: 640px) {
      nav { padding: 0 20px; }
      .hero { padding: 110px 20px 40px; }
      .container { padding: 0 20px; }
      section { padding: 40px 0; }
    }
  </style>
</head>
<body>

  <nav>
    <span class="brand">CI GUARANTEE · 이슈 모니터</span>
    <span class="last-updated" id="last-updated">로딩 중...</span>
  </nav>

  <header class="hero">
    <div class="hero-eyebrow">CONSTRUCTION INDUSTRY MONITOR</div>
    <h1 class="hero-title">이슈 모니터</h1>
    <p class="hero-sub">조합·건설업계 핵심 이슈를 매시간 수집하고 중요도·감정 톤과 함께 제공합니다.</p>
  </header>

  <!-- 주간 브리핑: Task 15 -->
  <!-- 필터 바: Task 13 -->
  <!-- 조합 언급 섹션: Task 14 -->
  <!-- 카테고리 톱 섹션: Task 14 -->

  <main class="container">
    <section>
      <div class="sec-num"><span class="dot"></span><span class="line"></span><span>ALL ARTICLES</span></div>
      <div class="sec-head"><h2>전체 기사</h2></div>
      <div id="articles"></div>
    </section>
  </main>

  <footer>© 기계설비건설공제조합 이슈 모니터 · Google News 기반 자동 수집</footer>

  <script>
    function escapeHtml(s) {
      return String(s || '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function safeHref(u) {
      try { const x = new URL(u); return (x.protocol === 'http:' || x.protocol === 'https:') ? u : '#'; }
      catch { return '#'; }
    }
    function formatDate(iso) {
      if (!iso) return '';
      const d = new Date(iso);
      if (isNaN(d)) return '';
      return d.toLocaleDateString('ko-KR') + ' ' + d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    }

    let allArticles = [];

    function render() {
      const el = document.getElementById('articles');
      if (!allArticles.length) {
        el.innerHTML = '<div class="empty">수집된 기사가 없습니다.</div>';
        return;
      }
      // Task 12에서 카드 구현
      el.innerHTML = allArticles.map(a => `<div>${escapeHtml(a.title_clean || a.title)}</div>`).join('');
    }

    fetch('articles.json?t=' + Date.now())
      .then(r => r.json())
      .then(data => {
        allArticles = data;
        const last = data.length ? data[0].collected_at : null;
        document.getElementById('last-updated').textContent = last ? '업데이트 ' + formatDate(last) : '데이터 없음';
        render();
      })
      .catch(() => {
        document.getElementById('articles').innerHTML = '<div class="empty">articles.json을 불러올 수 없습니다.</div>';
        document.getElementById('last-updated').textContent = '로딩 실패';
      });
  </script>

</body>
</html>
```

- [ ] **Step 3: 브라우저 수동 확인**

```bash
python -m http.server 8000
# 브라우저에서 http://localhost:8000 열기
```

Expected: hero 영역에 "이슈 모니터" 타이틀, 상단 sticky nav, 기사 제목만 플레인하게 나열됨.

- [ ] **Step 4: 커밋**

```bash
git add index.html
git commit -m "feat(site): 30주년 브로슈어 디자인 시스템 기반 뼈대"
```

---

## Task 12: index.html — 기사 카드 렌더링

**Files:**
- Modify: `index.html` (CSS + render 함수 확장)

- [ ] **Step 1: `<style>` 블록 끝(`</style>` 직전)에 카드 CSS 추가**

```css
    .article {
      background: var(--white);
      border-radius: 8px;
      padding: 22px 24px;
      margin-bottom: 10px;
      border: 1px solid var(--border);
      border-left: 3px solid var(--navy);
      transition: all .25s ease;
      position: relative;
    }
    .article:hover {
      box-shadow: 0 8px 24px rgba(30, 58, 111, 0.06);
      transform: translateX(4px);
    }
    .article.is-company { border-left-color: var(--cat-safety); }

    .article-meta {
      display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
      font-size: 11px; color: var(--muted);
      margin-bottom: 10px;
    }
    .imp-dots {
      letter-spacing: 1px; font-size: 10px;
      color: var(--blue-accent); font-weight: 700;
    }
    .cat-badge {
      padding: 3px 10px; border-radius: 100px;
      font-size: 10px; font-weight: 700; letter-spacing: 1px;
      color: #fff;
    }
    .cat-badge.c-co-op   { background: var(--cat-co-op); }
    .cat-badge.c-policy  { background: var(--cat-policy); }
    .cat-badge.c-market  { background: var(--cat-market); }
    .cat-badge.c-safety  { background: var(--cat-safety); }
    .cat-badge.c-labor   { background: var(--cat-labor); }
    .cat-badge.c-corp    { background: var(--cat-corp); }
    .sent-dot { font-size: 9px; line-height: 1; }
    .sent-dot.neg { color: var(--sent-neg); }
    .sent-dot.neu { color: var(--sent-neu); }
    .sent-dot.pos { color: var(--sent-pos); }
    .meta-sep { color: var(--border); }

    .article-title {
      font-size: 16px; font-weight: 700; line-height: 1.5;
      margin-bottom: 10px;
      letter-spacing: -0.3px;
    }
    .article-title a {
      color: var(--text); text-decoration: none;
    }
    .article-title a:hover { color: var(--navy); }

    .cluster-more {
      display: inline-block; margin-left: 8px;
      font-size: 11px; color: var(--blue-accent); font-weight: 700;
    }

    .summary-label {
      display: inline-block;
      font-size: 9px; color: var(--navy);
      font-weight: 800; letter-spacing: 2px;
      background: var(--bg-soft);
      padding: 3px 8px; border-radius: 3px;
      margin-bottom: 6px;
    }
    .article-summary {
      font-size: 13px; color: var(--sub); line-height: 1.7;
    }

    .copy-btn {
      position: absolute; top: 20px; right: 20px;
      border: 1px solid var(--border); background: var(--white);
      border-radius: 6px; padding: 4px 8px;
      font-size: 11px; color: var(--muted); cursor: pointer;
      font-family: inherit;
      transition: all .15s ease;
    }
    .copy-btn:hover { border-color: var(--navy); color: var(--navy); }
    .copy-btn.copied { background: var(--navy); color: #fff; border-color: var(--navy); }
```

- [ ] **Step 2: `<script>` 안에 카테고리→클래스 매핑 + renderCard 추가**

`<script>` 내 `let allArticles = [];` 아래 삽입:

```javascript
    const CATEGORY_CLASS = {
      '조합': 'c-co-op',
      '정책·규제': 'c-policy',
      '시장·경기': 'c-market',
      '안전·사고': 'c-safety',
      '노동·인력': 'c-labor',
      '종합건설사': 'c-corp',
    };

    function impDots(imp) {
      imp = imp || 0;
      if (imp >= 7) return '●●●';
      if (imp >= 4) return '●●';
      if (imp >= 1) return '●';
      return '○';
    }

    function sentDot(s) {
      const cls = s === 'negative' ? 'neg' : s === 'positive' ? 'pos' : 'neu';
      return `<span class="sent-dot ${cls}">●</span>`;
    }

    function relativeTime(iso) {
      if (!iso) return '';
      const then = new Date(iso), now = new Date();
      const mins = Math.floor((now - then) / 60000);
      if (mins < 60) return `${Math.max(1, mins)}분 전`;
      const hrs = Math.floor(mins / 60);
      if (hrs < 24) return `${hrs}시간 전`;
      const days = Math.floor(hrs / 24);
      return `${days}일 전`;
    }

    function renderCard(a) {
      const cat = a.category || '(미분류)';
      const catClass = CATEGORY_CLASS[cat] || 'c-corp';
      const isCompany = a.is_company ? 'is-company' : '';
      const title = a.title_clean || a.title || '';
      const publisher = a.publisher || '';
      const summary = a.summary || a.description || '';
      return `
        <article class="article ${isCompany}">
          <button class="copy-btn" data-link="${escapeHtml(safeHref(a.link))}" onclick="copyLink(this)">📋 복사</button>
          <div class="article-meta">
            <span class="imp-dots">${impDots(a.importance)}</span>
            <span class="cat-badge ${catClass}">${escapeHtml(cat)}</span>
            ${sentDot(a.sentiment)}
            ${publisher ? `<span>${escapeHtml(publisher)}</span><span class="meta-sep">·</span>` : ''}
            <span>${escapeHtml(relativeTime(a.collected_at))}</span>
          </div>
          <div class="article-title">
            <a href="${safeHref(a.link)}" target="_blank" rel="noopener">${escapeHtml(title)}</a>
          </div>
          <div class="summary-label">AI 요약</div>
          <div class="article-summary">${escapeHtml(summary)}</div>
        </article>
      `;
    }

    function copyLink(btn) {
      navigator.clipboard.writeText(btn.dataset.link).then(() => {
        const original = btn.innerHTML;
        btn.innerHTML = '✓ 복사됨';
        btn.classList.add('copied');
        setTimeout(() => { btn.innerHTML = original; btn.classList.remove('copied'); }, 1500);
      });
    }
```

- [ ] **Step 3: render() 함수 교체**

```javascript
    function render() {
      const el = document.getElementById('articles');
      if (!allArticles.length) {
        el.innerHTML = '<div class="empty">수집된 기사가 없습니다.</div>';
        return;
      }
      el.innerHTML = allArticles.map(renderCard).join('');
    }
```

- [ ] **Step 4: 브라우저 확인**

```bash
python -m http.server 8000
```

Expected: 카드 리스트, 중요도 점, 카테고리 배지, 감정 점, 언론사, 상대 시각, 복사 버튼 모두 정상 노출. 조합 직접 언급 기사는 좌측 보더가 빨강(`--cat-safety`).

- [ ] **Step 5: 커밋**

```bash
git add index.html
git commit -m "feat(site): 기사 카드 UI (중요도·카테고리·감정·복사)"
```

---

## Task 13: index.html — 필터 바 (검색 + 기간 + 카테고리 2단)

**Files:**
- Modify: `index.html`

- [ ] **Step 1: `<style>` 에 필터 바 CSS 추가**

```css
    .filter-bar {
      position: sticky; top: 64px; z-index: 50;
      background: rgba(255,255,255,0.97);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
      padding: 16px 24px;
    }
    .filter-bar-inner {
      max-width: 1120px; margin: 0 auto;
      display: flex; flex-direction: column; gap: 12px;
    }
    .filter-row {
      display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
    }
    .filter-label {
      font-size: 10px; font-weight: 800;
      color: var(--muted); letter-spacing: 2px;
      margin-right: 4px;
    }
    .search-input {
      flex: 1; min-width: 220px; max-width: 440px;
      padding: 10px 14px;
      border: 1px solid var(--border); border-radius: 8px;
      font-size: 14px; font-family: inherit;
      background: var(--white);
    }
    .search-input:focus { outline: none; border-color: var(--navy); }
    .chip {
      padding: 7px 14px; border: 1px solid var(--border);
      border-radius: 100px; background: var(--white);
      font-size: 12px; font-weight: 600; color: var(--sub);
      cursor: pointer; font-family: inherit;
      transition: all .15s ease;
    }
    .chip:hover { border-color: var(--navy); color: var(--navy); }
    .chip.active { background: var(--navy); color: #fff; border-color: var(--navy); }
    .chip .count { opacity: 0.7; margin-left: 4px; font-size: 11px; }

    .cat-group {
      display: flex; gap: 6px; flex-wrap: wrap;
      padding-left: 12px; border-left: 1px solid var(--border);
    }
    .cat-group.hidden { display: none; }
```

- [ ] **Step 2: HTML 에 필터 바 삽입**

`<nav>` 블록 직후, `<header class="hero">` 직전에 삽입:

```html
  <div class="filter-bar">
    <div class="filter-bar-inner">
      <div class="filter-row">
        <input type="text" id="search" class="search-input" placeholder="🔍 제목·요약 검색">
        <span class="filter-label">기간</span>
        <button class="chip" data-period="1">오늘</button>
        <button class="chip" data-period="3">3일</button>
        <button class="chip active" data-period="7">7일</button>
        <button class="chip" data-period="30">1개월</button>
        <button class="chip" data-period="all">전체</button>
      </div>
      <div class="filter-row">
        <span class="filter-label">카테고리</span>
        <button class="chip active" data-group="all">전체</button>
        <button class="chip" data-group="조합">조합</button>
        <button class="chip" data-group="산업">산업</button>
        <button class="chip" data-group="종합건설사">종합건설사</button>
        <div class="cat-group hidden" id="cat-sub-industry">
          <button class="chip" data-cat="정책·규제">정책·규제 <span class="count"></span></button>
          <button class="chip" data-cat="시장·경기">시장·경기 <span class="count"></span></button>
          <button class="chip" data-cat="안전·사고">안전·사고 <span class="count"></span></button>
          <button class="chip" data-cat="노동·인력">노동·인력 <span class="count"></span></button>
        </div>
      </div>
    </div>
  </div>
```

- [ ] **Step 3: 필터 state + 로직 구현**

`<script>` 안 `let allArticles = [];` 아래에 추가:

```javascript
    let state = {
      q: '',
      period: 7,          // 1 / 3 / 7 / 30 / 'all'
      group: 'all',       // 'all' / '조합' / '산업' / '종합건설사'
      cat: null,          // 하위 카테고리 (산업 그룹 펼침 시)
    };

    const INDUSTRY_CATS = ['정책·규제', '시장·경기', '안전·사고', '노동·인력'];

    function inPeriod(iso) {
      if (state.period === 'all') return true;
      if (!iso) return false;
      const t = new Date(iso).getTime();
      if (isNaN(t)) return false;
      return (Date.now() - t) <= state.period * 86400000;
    }

    function matchesGroup(a) {
      if (state.group === 'all') return true;
      if (state.group === '조합') return a.category === '조합';
      if (state.group === '종합건설사') return a.category === '종합건설사';
      if (state.group === '산업') {
        if (state.cat) return a.category === state.cat;
        return INDUSTRY_CATS.includes(a.category);
      }
      return true;
    }

    function matchesQuery(a) {
      if (!state.q) return true;
      const hay = (a.title_clean || a.title || '') + ' ' + (a.summary || '');
      return hay.toLowerCase().includes(state.q.toLowerCase());
    }

    function filtered() {
      return allArticles.filter(a =>
        inPeriod(a.collected_at) && matchesGroup(a) && matchesQuery(a)
      );
    }

    function updateChipActive() {
      document.querySelectorAll('.chip[data-period]').forEach(c => {
        c.classList.toggle('active', String(c.dataset.period) === String(state.period));
      });
      document.querySelectorAll('.chip[data-group]').forEach(c => {
        c.classList.toggle('active', c.dataset.group === state.group && !state.cat);
      });
      document.querySelectorAll('.chip[data-cat]').forEach(c => {
        c.classList.toggle('active', c.dataset.cat === state.cat);
      });
      document.getElementById('cat-sub-industry').classList.toggle('hidden', state.group !== '산업');
    }

    function updateCatCounts() {
      INDUSTRY_CATS.forEach(cat => {
        const n = allArticles.filter(a => a.category === cat).length;
        document.querySelectorAll(`.chip[data-cat="${cat}"] .count`).forEach(el => {
          el.textContent = `(${n})`;
        });
      });
    }

    function writeHash() {
      const parts = [];
      if (state.q) parts.push('q=' + encodeURIComponent(state.q));
      if (state.period !== 7) parts.push('period=' + state.period);
      if (state.group !== 'all') parts.push('group=' + encodeURIComponent(state.group));
      if (state.cat) parts.push('cat=' + encodeURIComponent(state.cat));
      location.hash = parts.join('&');
    }

    function readHash() {
      const h = location.hash.replace(/^#/, '');
      if (!h) return;
      h.split('&').forEach(kv => {
        const [k, v] = kv.split('=');
        if (!k) return;
        const val = decodeURIComponent(v || '');
        if (k === 'q') state.q = val;
        else if (k === 'period') state.period = val === 'all' ? 'all' : parseInt(val, 10);
        else if (k === 'group') state.group = val;
        else if (k === 'cat') state.cat = val;
      });
    }

    // 이벤트 바인딩
    document.getElementById('search').addEventListener('input', (e) => {
      clearTimeout(window._t);
      window._t = setTimeout(() => { state.q = e.target.value; writeHash(); render(); }, 200);
    });
    document.querySelectorAll('.chip[data-period]').forEach(c => c.addEventListener('click', () => {
      state.period = c.dataset.period === 'all' ? 'all' : parseInt(c.dataset.period, 10);
      writeHash(); updateChipActive(); render();
    }));
    document.querySelectorAll('.chip[data-group]').forEach(c => c.addEventListener('click', () => {
      state.group = c.dataset.group; state.cat = null;
      writeHash(); updateChipActive(); render();
    }));
    document.querySelectorAll('.chip[data-cat]').forEach(c => c.addEventListener('click', () => {
      state.cat = (state.cat === c.dataset.cat) ? null : c.dataset.cat;
      writeHash(); updateChipActive(); render();
    }));
    window.addEventListener('hashchange', () => { readHash(); document.getElementById('search').value = state.q; updateChipActive(); render(); });
```

- [ ] **Step 4: render() 함수 수정** — `allArticles` 대신 `filtered()` 사용

```javascript
    function render() {
      const list = filtered();
      const el = document.getElementById('articles');
      if (!list.length) {
        el.innerHTML = '<div class="empty">조건에 맞는 기사가 없습니다.</div>';
        return;
      }
      el.innerHTML = list.map(renderCard).join('');
    }
```

- [ ] **Step 5: fetch 완료 후 readHash + updateCatCounts 호출**

기존 `.then(data => { ... render(); })` 블록을:

```javascript
      .then(data => {
        allArticles = data;
        const last = data.length ? data[0].collected_at : null;
        document.getElementById('last-updated').textContent = last ? '업데이트 ' + formatDate(last) : '데이터 없음';
        readHash();
        document.getElementById('search').value = state.q;
        updateChipActive();
        updateCatCounts();
        render();
      })
```

- [ ] **Step 6: 브라우저 확인**

- 검색 즉시 반영
- 기간 7일 기본 선택됨
- "산업" 클릭 시 하위 카테고리 드롭다운
- URL 해시 변경 확인 (`#period=3&cat=안전·사고`)
- 북마크·공유 해시 재진입 테스트

- [ ] **Step 7: 커밋**

```bash
git add index.html
git commit -m "feat(site): 검색·기간·카테고리 2단 필터 + URL 해시"
```

---

## Task 14: index.html — 특수 섹션 (조합 언급 + 카테고리별 톱 3)

**Files:**
- Modify: `index.html`

- [ ] **Step 1: `<style>` 에 섹션 CSS 추가**

```css
    .top-section { background: var(--white); border-radius: 12px; padding: 28px 24px; margin-bottom: 40px; border: 1px solid var(--border); }
    .top-section.company { border-left: 4px solid var(--cat-safety); }
    .top-section.company .sec-head h2 { color: var(--cat-safety); }

    .cat-top-head {
      display: flex; align-items: center; gap: 10px;
      margin: 32px 0 12px;
    }
    .cat-top-head h3 {
      font-size: 16px; font-weight: 800; color: var(--navy);
      letter-spacing: -0.3px;
    }
    .cat-top-head .rule { flex: 1; height: 1px; background: var(--border); }
```

- [ ] **Step 2: HTML 에 섹션 컨테이너 추가**

`<main class="container">` 내부, 기존 `<section>` (전체 기사) 앞에 삽입:

```html
    <section id="company-top" style="display:none">
      <div class="sec-num"><span class="dot" style="background:var(--cat-safety)"></span><span class="line" style="background:var(--cat-safety)"></span><span style="color:var(--cat-safety)">CO-OP FOCUS</span></div>
      <div class="sec-head"><h2>🔴 우리 조합 직접 언급 이슈</h2></div>
      <div id="company-list" class="top-section company"></div>
    </section>

    <section id="category-top">
      <div class="sec-num"><span class="dot"></span><span class="line"></span><span>TOP BY CATEGORY</span></div>
      <div class="sec-head"><h2>카테고리별 톱 이슈</h2></div>
      <div id="category-list"></div>
    </section>
```

- [ ] **Step 3: `<script>` 에 섹션 렌더러 추가**

```javascript
    const CATEGORY_TOP_ORDER = ['정책·규제', '시장·경기', '안전·사고', '노동·인력', '종합건설사'];

    function renderCompanyTop(list) {
      const companyArts = list.filter(a => a.is_company).slice(0, 5);
      const sec = document.getElementById('company-top');
      if (!companyArts.length) { sec.style.display = 'none'; return; }
      sec.style.display = '';
      document.getElementById('company-list').innerHTML =
        companyArts.map(renderCard).join('');
    }

    function renderCategoryTop(list) {
      const el = document.getElementById('category-list');
      const html = CATEGORY_TOP_ORDER.map(cat => {
        const top = list
          .filter(a => a.category === cat)
          .sort((x, y) => (y.importance || 0) - (x.importance || 0))
          .slice(0, 3);
        if (!top.length) return '';
        return `
          <div class="cat-top-head"><h3>${escapeHtml(cat)}</h3><div class="rule"></div></div>
          ${top.map(renderCard).join('')}
        `;
      }).join('');
      el.innerHTML = html || '<div class="empty">카테고리별 이슈가 없습니다.</div>';
    }
```

- [ ] **Step 4: render() 를 3-섹션 렌더링으로 확장**

```javascript
    function render() {
      const list = filtered();
      renderCompanyTop(list);
      renderCategoryTop(list);
      const el = document.getElementById('articles');
      if (!list.length) {
        el.innerHTML = '<div class="empty">조건에 맞는 기사가 없습니다.</div>';
        return;
      }
      el.innerHTML = list.map(renderCard).join('');
    }
```

- [ ] **Step 5: 브라우저 확인**

- 상단에 "🔴 우리 조합 직접 언급" 섹션 (is_company=true 있을 때만)
- 그 아래 "카테고리별 톱 이슈" — 5개 카테고리 각각 중요도 상위 3건
- "전체 기사" 섹션에는 필터 후 모든 기사
- 필터 변경 시 모든 섹션이 동시에 업데이트

- [ ] **Step 6: 커밋**

```bash
git add index.html
git commit -m "feat(site): 조합 포커스 + 카테고리별 톱 3건 섹션"
```

---

## Task 15: index.html — 주간 브리핑 카드 (weekly.json)

**Files:**
- Modify: `index.html`

- [ ] **Step 1: `<style>` 에 주간 카드 CSS 추가**

```css
    .weekly-wrap {
      background: linear-gradient(135deg, var(--navy-deep) 0%, var(--navy) 100%);
      color: #fff;
      border-radius: 16px;
      padding: 40px;
      margin: 40px auto;
      max-width: 1120px;
      box-shadow: 0 20px 60px rgba(10, 24, 41, 0.15);
    }
    .weekly-label {
      display: inline-block;
      font-size: 10px; font-weight: 800; letter-spacing: 4px;
      padding: 5px 14px;
      background: linear-gradient(120deg, #E8A5C5, #C5A5E8, #A5B5E8, #A5E8C5);
      background-size: 200% 100%;
      animation: weeklyShift 8s ease infinite;
      color: #fff;
      border-radius: 100px;
      margin-bottom: 12px;
    }
    @keyframes weeklyShift {
      0%, 100% { background-position: 0% 50%; }
      50% { background-position: 100% 50%; }
    }
    .weekly-title {
      font-size: 24px; font-weight: 900; letter-spacing: -0.8px;
      margin-bottom: 4px;
    }
    .weekly-period { font-size: 12px; color: rgba(255,255,255,0.6); margin-bottom: 24px; letter-spacing: 2px; }
    .weekly-item { padding: 16px 0; border-top: 1px solid rgba(255,255,255,0.12); }
    .weekly-item:first-child { border-top: none; padding-top: 0; }
    .weekly-item .cat { font-size: 10px; font-weight: 800; letter-spacing: 2px; color: var(--cyan-soft); margin-bottom: 4px; }
    .weekly-item .headline { font-size: 16px; font-weight: 700; margin-bottom: 6px; letter-spacing: -0.3px; }
    .weekly-item .brief { font-size: 13px; color: rgba(255,255,255,0.8); line-height: 1.7; }
    @media (max-width: 640px) {
      .weekly-wrap { padding: 28px 20px; border-radius: 12px; }
      .weekly-title { font-size: 20px; }
    }
```

- [ ] **Step 2: HTML 에 주간 카드 섹션 삽입**

`<div class="filter-bar">` 직후(= hero 위) 에 추가:

```html
  <section id="weekly-brief" style="display:none">
    <div class="weekly-wrap">
      <div class="weekly-label">WEEKLY BRIEF</div>
      <div class="weekly-title">지난주 핵심 이슈 5선</div>
      <div class="weekly-period" id="weekly-period"></div>
      <div id="weekly-items"></div>
    </div>
  </section>
```

- [ ] **Step 3: `<script>` 에 weekly fetch + 렌더러 추가**

```javascript
    function renderWeekly(data) {
      const sec = document.getElementById('weekly-brief');
      if (!data || !data.items || !data.items.length) { sec.style.display = 'none'; return; }
      sec.style.display = '';
      document.getElementById('weekly-period').textContent = data.period || '';
      document.getElementById('weekly-items').innerHTML = data.items.map(i => `
        <div class="weekly-item">
          <div class="cat">${escapeHtml(i.category || '')}</div>
          <div class="headline">${escapeHtml(i.headline || '')}</div>
          <div class="brief">${escapeHtml(i.brief || '')}</div>
        </div>
      `).join('');
    }

    fetch('weekly.json?t=' + Date.now())
      .then(r => r.ok ? r.json() : null)
      .then(renderWeekly)
      .catch(() => {});
```

- [ ] **Step 4: 브라우저 확인**

`weekly.json` 이 없을 때는 섹션이 숨겨짐. 수동으로 샘플 파일 생성해 확인:

```bash
cat > weekly.json <<'EOF'
{
  "period": "2026-04-13 ~ 2026-04-19",
  "generated_at": "2026-04-19T23:05:00",
  "items": [
    {"category": "시장·경기", "headline": "태영건설 워크아웃 1주년…", "brief": "지난 1년간 재무구조 개선 진척이 미흡하다는 평가가 나온다."},
    {"category": "안전·사고", "headline": "중대재해법 개정안 국회 본회의 통과", "brief": "처벌 요건과 적용 범위가 일부 완화되는 방향으로 개정됐다."}
  ]
}
EOF
python -m http.server 8000
```

Expected: 필터 바 아래에 그라데이션 WEEKLY BRIEF 라벨 + 5건 리스트. 확인 후 샘플 파일 삭제:

```bash
rm weekly.json
```

- [ ] **Step 5: 커밋**

```bash
git add index.html
git commit -m "feat(site): 주간 브리핑 카드 (weekly.json 연동)"
```

---

## Task 16: 통합 실행 검증 + README 업데이트

**Files:**
- Modify: `README.md` (있다면)
- (새 파일 없음)

- [ ] **Step 1: 백엔드 전 테스트 재실행**

```bash
pytest tests/ -v
```

Expected: 전부 PASS.

- [ ] **Step 2: 실 파이프라인 1회 실행 (API 비용 ~$0.02)**

```bash
python main.py
```

Expected 로그: "새 기사 N건 발견. enrich 중..." → "N건 이슈 이메일 발송 완료." 이메일 수신 시 중요도·감정·카테고리·언론사 표시 확인.

- [ ] **Step 3: 주간 요약 수동 실행 (최초 1회, 데이터 충분할 때)**

```bash
python weekly_summary.py
cat weekly.json
```

Expected: `weekly.json` 생성. 사이트에서 주간 카드 표시 확인.

- [ ] **Step 4: 사이트 수동 체크리스트**

브라우저에서 다음 시나리오 확인:

- [ ] 데스크탑: hero → 주간 카드 → 필터 바 → 조합 포커스 → 카테고리 톱 → 전체 기사 순서
- [ ] 모바일 (~390px): 필터 한 줄에 다 안 들어가면 줄바꿈, 카드 가독성
- [ ] 검색 즉시 필터링
- [ ] 기간 변경 시 전 섹션 즉시 업데이트
- [ ] "산업" 클릭 시 하위 카테고리 펼침
- [ ] URL 해시 변경·북마크·공유 링크 동작
- [ ] 카드 복사 버튼 → 클립보드 확인 + "✓ 복사됨" 피드백
- [ ] 조합 직접 언급 기사의 빨강 좌측 보더
- [ ] 중요도 점 (●●●/●●/●), 감정 점 (🔴/⚪/🟢)

- [ ] **Step 5: cron 업데이트 안내**

기존 cron에 주간 요약 1줄 추가 (사용자 환경에 따라 crontab 편집):

```
# 기존: 매시간 17분
17 * * * * cd /path/to/claude-introduction && python main.py >> monitor.log 2>&1

# 추가: 일요일 23시
0 23 * * 0 cd /path/to/claude-introduction && python weekly_summary.py >> monitor.log 2>&1
```

- [ ] **Step 6: (선택) README.md 갱신**

파일이 있다면 신규 파이프라인·cron·마이그레이션 절차 간단 설명 추가.

- [ ] **Step 7: 최종 커밋**

```bash
# 실 파이프라인 실행 후 articles.json·seen.json 변경 커밋
git add articles.json seen.json README.md 2>/dev/null
git commit -m "chore: enrich 파이프라인 실 데이터 검증 완료"
```

- [ ] **Step 8: 임원 공개 전 체크리스트 확인**

스펙(`docs/superpowers/specs/2026-04-23-gongje-monitor-executive-rollout-design.md`) "임원 공개 전 체크리스트" 세션의 조건(7일 누적 운영·오분류 확인)은 이 플랜 종료 후 운영 단계에서 충족. 본 플랜 범위 아님.

---

## 셀프 리뷰

**스펙 커버리지**
- ✅ 카테고리 dict (`정책·규제/시장·경기/안전·사고/노동·인력/종합건설사`) — Task 1
- ✅ 종합건설사 10개 (`삼성물산 건설` 주석 포함) — Task 1
- ✅ crawler 카테고리 부여 — Task 2
- ✅ normalize_title / extract_publisher — Task 3
- ✅ cluster_articles 정규화+자카드 — Task 4
- ✅ Haiku 요약+감정 통합 호출 + 폴백 — Task 5
- ✅ 규칙 기반 중요도 — Task 6
- ✅ enrich_articles 파이프라인 — Task 7
- ✅ main 통합, summarizer 제거 — Task 8
- ✅ 마이그레이션 — Task 9
- ✅ 주간 요약 (임계 폴백 포함) — Task 10
- ✅ 30주년 디자인 언어 — Task 11 (컬러 토큰, Pretendard Variable, sec-num, hero)
- ✅ 카드 (중요도 점, 카테고리 배지, 감정 점, 언론사, 복사 버튼) — Task 12
- ✅ 필터 2단 + 검색 + 기간 + URL 해시 — Task 13
- ✅ 조합 포커스 + 카테고리 톱 3 — Task 14
- ✅ 주간 브리핑 카드 — Task 15
- ✅ cron 업데이트 안내 — Task 16

**플레이스홀더 스캔**: 모든 task 에 실제 코드·명령어·예상 출력 포함. "TODO/TBD" 없음.

**타입/이름 일관성**:
- `enrich_article` (단수, Haiku 1건 처리) vs `enrich_articles` (파이프라인) — 의도적 구분
- `cluster_id` 4자 hex — Task 4·9 일치
- `is_company` bool — Task 2·6·9·12 일치
- `title_clean` — Task 7·9·11·12 일치

**범위 체크**: 3개 단계(백엔드 enrich / 마이그레이션 / 프론트엔드)가 순차 의존. 각 커밋은 독립적으로 테스트 가능. 단일 플랜으로 유지 — 분해는 불필요.
