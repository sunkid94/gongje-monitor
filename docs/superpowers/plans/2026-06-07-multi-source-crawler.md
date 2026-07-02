# 멀티소스 크롤러 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 구글 뉴스만 보던 크롤러에 네이버 검색 API와 기계설비신문 RSS를 추가해, 전문지가 발행한 직후 기사를 수집·알림하도록 한다(구글 색인 지연 제거).

**Architecture:** 소스를 `source_google.py`/`source_naver.py`/`source_rss.py` 모듈로 분리한다. 각 소스는 `fetch() -> list[dict]`로 동일 형식의 원시 기사를 반환하되 제목을 `"헤드라인 - 매체명"`으로 맞춰 기존 enrich(publisher/cluster) 로직을 그대로 쓴다. `crawler.fetch_new_articles(seen)`은 세 소스를 합치고 link 기준 중복(+seen)만 제거한다. `main.py`는 무변경.

**Tech Stack:** Python 3.10+, `requests`(네이버 API), `feedparser`(구글·RSS), pytest 8.3.4. 신규 의존성 없음.

설계 스펙: `docs/superpowers/specs/2026-06-07-multi-source-crawler-design.md`
대상: `crawler.py`(현 74줄, 구글 전용), `config.py`, `tests/test_crawler.py`(현 google 동작 테스트 다수)

---

## File Structure

| 파일 | 책임 |
|------|------|
| `source_google.py` (신규) | 구글 뉴스 RSS 수집 — 기존 crawler 로직 이전. `fetch()` |
| `source_naver.py` (신규) | 네이버 검색 API 수집. `fetch()` |
| `source_rss.py` (신규) | 전문지 RSS 수집 + 관련도 분류. `fetch()`, `classify()` |
| `crawler.py` (재작성) | 세 소스 합치기 + seen/link 중복 제거. `fetch_new_articles(seen)` |
| `config.py` (수정) | `TRADE_RSS_FEEDS` 추가 |
| `tests/test_source_google.py` (신규) | 기존 google 동작 테스트 이전 |
| `tests/test_source_naver.py` (신규) | 네이버 소스 테스트 |
| `tests/test_source_rss.py` (신규) | RSS 소스 테스트 |
| `tests/test_crawler.py` (재작성) | 합치기/중복제거(aggregator) 테스트 |

**공통 출력 dict:** `{"keyword","category","is_company","title"(="헤드라인 - 매체명"),"link","description"[, "published_at"(ISO)]}`

---

### Task 1: 구글 소스 분리 + 크롤러를 합치기 계층으로

**Files:**
- Create: `source_google.py`, `tests/test_source_google.py`
- Rewrite: `crawler.py`, `tests/test_crawler.py`

- [ ] **Step 1: `source_google.py` 생성** — 기존 `crawler.py`의 구글 로직을 옮기되 `fetch_new_articles(seen)` 대신 seen 없는 `fetch()`로:

```python
import calendar
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import feedparser

from article_store import is_empty_stub
from config import CATEGORY_KEYWORDS, COMPANY_KEYWORDS
from pub_date import resolve_published_time

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={}&hl=ko&gl=KR&ceid=KR:ko"
ORIGINAL_PUB_MAX_AGE_DAYS = 7   # 원문 발행이 이보다 오래되면 폐기(구글 재색인 대응)


def _fetch_keyword(keyword: str, category: str, is_company: bool) -> list:
    feed = feedparser.parse(GOOGLE_NEWS_RSS.format(quote(keyword)))
    articles = []
    for entry in feed.entries:
        title = entry.get("title", "")
        description = entry.get("summary", "")
        if is_empty_stub(title, description):
            continue
        articles.append({
            "keyword": keyword, "category": category, "is_company": is_company,
            "title": title, "link": entry.get("link", ""),
            "description": description, "published_parsed": entry.get("published_parsed"),
        })
    return articles


def fetch() -> list:
    """구글 뉴스 RSS 최근 24h 기사. 원문 발행 7일 초과분 폐기. seen 미적용."""
    cutoff = datetime.now() - timedelta(hours=24)
    original_cutoff = datetime.now(timezone.utc) - timedelta(days=ORIGINAL_PUB_MAX_AGE_DAYS)
    articles = []
    seen_links = set()
    sources = [(kw, "조합·협회", True) for kw in COMPANY_KEYWORDS]
    for category, kws in CATEGORY_KEYWORDS.items():
        sources.extend((kw, category, False) for kw in kws)
    for keyword, category, is_company in sources:
        for item in _fetch_keyword(keyword, category, is_company):
            if item["link"] in seen_links:
                continue
            pub_struct = item.pop("published_parsed")
            if pub_struct:
                try:
                    pub_dt = datetime.fromtimestamp(calendar.timegm(pub_struct))
                    if pub_dt < cutoff:
                        continue
                except (ValueError, TypeError, OverflowError):
                    pass
            original_pub = resolve_published_time(item["link"])
            if original_pub is not None:
                if original_pub.tzinfo is None:
                    original_pub = original_pub.replace(tzinfo=timezone.utc)
                if original_pub < original_cutoff:
                    seen_links.add(item["link"])
                    continue
                item["published_at"] = original_pub.isoformat()
            articles.append(item)
            seen_links.add(item["link"])
    return articles
```

- [ ] **Step 2: `tests/test_source_google.py` 생성** — 기존 `tests/test_crawler.py`의 google 동작 테스트를 이전(패치 대상 `crawler.*`→`source_google.*`, `fetch_new_articles(seen)`→`fetch()`):

```python
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import time
import importlib

FIXED_NOW = datetime(2026, 4, 18, 12, 0, 0)
FIXED_NOW_UTC = FIXED_NOW.replace(tzinfo=timezone.utc)

MOCK_ENTRY = MagicMock()
MOCK_ENTRY.get = lambda key, default="": {
    "title": "기계설비건설공제조합 신규 공시 - 기계설비신문",
    "link": "http://news.google.com/articles/1",
    "summary": "기계설비건설공제조합이 신규 사업 계획을 발표했다.",
    "published_parsed": time.strptime("2026-04-18 10:00:00", "%Y-%m-%d %H:%M:%S"),
}.get(key, default)


def _mock_feed(entries):
    feed = MagicMock()
    feed.entries = entries
    return feed


def _make_datetime_mock():
    mock_dt = MagicMock(spec=datetime)
    mock_dt.now.side_effect = lambda tz=None: FIXED_NOW_UTC if tz is not None else FIXED_NOW
    mock_dt.fromtimestamp.side_effect = datetime.fromtimestamp
    return mock_dt


def test_fetch_keyword_returns_articles():
    with patch("source_google.feedparser.parse", return_value=_mock_feed([MOCK_ENTRY])):
        import source_google
        importlib.reload(source_google)
        result = source_google._fetch_keyword("기계설비건설공제조합", "조합·협회", True)
    assert len(result) == 1
    assert result[0]["keyword"] == "기계설비건설공제조합"
    assert result[0]["link"] == "http://news.google.com/articles/1"
    assert result[0]["is_company"] is True


def test_fetch_excludes_old_articles():
    import source_google
    importlib.reload(source_google)
    old = MagicMock()
    old.get = lambda key, default="": {
        "title": "오래된 기사 - 매체", "link": "http://news.google.com/articles/old",
        "summary": "오래된 내용",
        "published_parsed": time.strptime("2024-01-01 10:00:00", "%Y-%m-%d %H:%M:%S"),
    }.get(key, default)
    with patch("source_google.feedparser.parse", return_value=_mock_feed([old])), \
         patch("source_google.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_google.CATEGORY_KEYWORDS", {}):
        source_google.datetime = _make_datetime_mock()
        result = source_google.fetch()
    assert result == []


def test_fetch_drops_old_original_pub():
    import source_google
    importlib.reload(source_google)
    from datetime import datetime as _dt
    old_pub = _dt(2021, 2, 26, 8, 55, tzinfo=timezone.utc)
    with patch("source_google.feedparser.parse", return_value=_mock_feed([MOCK_ENTRY])), \
         patch("source_google.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_google.CATEGORY_KEYWORDS", {}), \
         patch("source_google.resolve_published_time", return_value=old_pub):
        source_google.datetime = _make_datetime_mock()
        result = source_google.fetch()
    assert result == []


def test_fetch_keeps_recent_original_pub_and_sets_published_at():
    import source_google
    importlib.reload(source_google)
    from datetime import datetime as _dt
    recent = _dt(2026, 4, 17, 9, 0, tzinfo=timezone.utc)
    with patch("source_google.feedparser.parse", return_value=_mock_feed([MOCK_ENTRY])), \
         patch("source_google.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_google.CATEGORY_KEYWORDS", {}), \
         patch("source_google.resolve_published_time", return_value=recent):
        source_google.datetime = _make_datetime_mock()
        result = source_google.fetch()
    assert len(result) == 1
    assert result[0]["published_at"] == recent.isoformat()


def test_fetch_keeps_when_pub_unresolvable():
    import source_google
    importlib.reload(source_google)
    with patch("source_google.feedparser.parse", return_value=_mock_feed([MOCK_ENTRY])), \
         patch("source_google.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_google.CATEGORY_KEYWORDS", {}), \
         patch("source_google.resolve_published_time", return_value=None):
        source_google.datetime = _make_datetime_mock()
        result = source_google.fetch()
    assert len(result) == 1
    assert "published_at" not in result[0]
```

- [ ] **Step 3: `crawler.py` 재작성** — 합치기 계층(이번 태스크는 구글만 연결, Naver/RSS는 Task 2·3에서 추가):

```python
import logging

import source_google

logger = logging.getLogger(__name__)

SOURCES = [source_google]


def fetch_new_articles(seen: set) -> list:
    """등록된 모든 소스를 수집해 합치고, link 가 seen 에 없는 것만(소스 간 중복도 제거) 반환."""
    out = []
    collected = set(seen)
    for source in SOURCES:
        try:
            items = source.fetch()
        except Exception as e:
            logger.error("소스 수집 실패 %s: %s", getattr(source, "__name__", source), e)
            continue
        for a in items:
            link = a.get("link", "")
            if not link or link in collected:
                continue
            out.append(a)
            collected.add(link)
    return out
```

- [ ] **Step 4: `tests/test_crawler.py` 재작성** — aggregator 동작(소스 모킹):

```python
from unittest.mock import patch
import crawler


def _article(link):
    return {"keyword": "k", "category": "조합·협회", "is_company": True,
            "title": "제목 - 매체", "link": link, "description": "d"}


def test_aggregator_excludes_seen_links():
    with patch.object(crawler, "SOURCES", [type("S", (), {"fetch": staticmethod(lambda: [_article("http://a/1")]), "__name__": "s"})]):
        result = crawler.fetch_new_articles({"http://a/1"})
    assert result == []


def test_aggregator_includes_unseen_links():
    with patch.object(crawler, "SOURCES", [type("S", (), {"fetch": staticmethod(lambda: [_article("http://a/2")]), "__name__": "s"})]):
        result = crawler.fetch_new_articles(set())
    assert len(result) == 1
    assert result[0]["link"] == "http://a/2"


def test_aggregator_dedups_same_link_across_sources():
    s1 = type("S1", (), {"fetch": staticmethod(lambda: [_article("http://dup")]), "__name__": "s1"})
    s2 = type("S2", (), {"fetch": staticmethod(lambda: [_article("http://dup")]), "__name__": "s2"})
    with patch.object(crawler, "SOURCES", [s1, s2]):
        result = crawler.fetch_new_articles(set())
    assert len(result) == 1


def test_aggregator_continues_when_a_source_raises():
    bad = type("Bad", (), {"fetch": staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("x"))), "__name__": "bad"})
    good = type("Good", (), {"fetch": staticmethod(lambda: [_article("http://ok")]), "__name__": "good"})
    with patch.object(crawler, "SOURCES", [bad, good]):
        result = crawler.fetch_new_articles(set())
    assert len(result) == 1
    assert result[0]["link"] == "http://ok"
```

- [ ] **Step 5: 실행** — `python3 -m pytest tests/test_source_google.py tests/test_crawler.py -v` → 모두 통과. 그다음 전체 `python3 -m pytest -q` → 회귀 없음(기존 test_crawler.py는 새 내용으로 대체됨). `python3 -c "import main, crawler, source_google; print('OK')"` → OK.

- [ ] **Step 6: 커밋**

```bash
git add source_google.py crawler.py tests/test_source_google.py tests/test_crawler.py
git commit -m "refactor: 구글 수집을 source_google로 분리, crawler는 소스 합치기 계층으로"
```

---

### Task 2: 네이버 검색 API 소스

**Files:**
- Create: `source_naver.py`, `tests/test_source_naver.py`
- Modify: `crawler.py` (SOURCES에 추가)

- [ ] **Step 1: `tests/test_source_naver.py` 작성**

```python
from unittest.mock import patch, MagicMock
import importlib


def _resp(items, error=None):
    r = MagicMock()
    r.json.return_value = {"errorCode": error, "errorMessage": "e"} if error else {"items": items}
    return r


def _item(title, link, pub="Fri, 05 Jun 2026 08:00:00 +0900", desc=""):
    return {"title": title, "originallink": link, "link": link, "description": desc, "pubDate": pub}


def _env():
    return patch.dict("os.environ", {"NAVER_CLIENT_ID": "id", "NAVER_CLIENT_SECRET": "sec"})


def test_naver_maps_item_with_publisher_suffix():
    import source_naver
    importlib.reload(source_naver)
    items = [_item("K-FINCO 하반기 채용", "https://www.koscaj.com/news/1", desc="전문건설공제조합 채용")]
    with _env(), patch("source_naver.requests.get", return_value=_resp(items)), \
         patch("source_naver.COMPANY_KEYWORDS", ["전문건설공제조합"]), \
         patch("source_naver.CATEGORY_KEYWORDS", {}):
        source_naver.datetime = _frozen_dt()
        out = source_naver.fetch()
    assert len(out) == 1
    assert out[0]["title"] == "K-FINCO 하반기 채용 - 대한전문건설신문"   # 도메인→매체명
    assert out[0]["link"] == "https://www.koscaj.com/news/1"
    assert out[0]["is_company"] is True


def test_naver_filters_irrelevant_items():
    import source_naver
    importlib.reload(source_naver)
    items = [_item("전세사기 대처법", "https://x.com/1", desc="부동산")]   # 키워드 미포함
    with _env(), patch("source_naver.requests.get", return_value=_resp(items)), \
         patch("source_naver.COMPANY_KEYWORDS", ["전문건설공제조합"]), \
         patch("source_naver.CATEGORY_KEYWORDS", {}):
        source_naver.datetime = _frozen_dt()
        out = source_naver.fetch()
    assert out == []


def test_naver_handles_api_error():
    import source_naver
    importlib.reload(source_naver)
    with _env(), patch("source_naver.requests.get", return_value=_resp([], error="024")), \
         patch("source_naver.COMPANY_KEYWORDS", ["전문건설공제조합"]), \
         patch("source_naver.CATEGORY_KEYWORDS", {}):
        out = source_naver.fetch()
    assert out == []


def test_naver_skips_when_no_keys():
    import source_naver
    importlib.reload(source_naver)
    with patch.dict("os.environ", {}, clear=True), \
         patch("source_naver.COMPANY_KEYWORDS", ["전문건설공제조합"]), \
         patch("source_naver.CATEGORY_KEYWORDS", {}):
        out = source_naver.fetch()
    assert out == []


# 24h 컷오프를 위한 고정 시각 (2026-06-05 18:00 KST 부근)
from datetime import datetime, timezone, timedelta
def _frozen_dt():
    fixed = datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc)   # 18:00 KST
    m = MagicMock(spec=datetime)
    m.now.side_effect = lambda tz=None: fixed
    return m
```

- [ ] **Step 2: 실패 확인** — `python3 -m pytest tests/test_source_naver.py -v` → ModuleNotFoundError: source_naver

- [ ] **Step 3: `source_naver.py` 구현**

```python
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests

from config import CATEGORY_KEYWORDS, COMPANY_KEYWORDS

logger = logging.getLogger(__name__)

NAVER_NEWS_API = "https://openapi.naver.com/v1/search/news.json"
_TAG_RE = re.compile(r"<[^>]+>")

# 알려진 도메인 → 매체명 (없으면 도메인 그대로)
_DOMAIN_PUBLISHER = {
    "koscaj.com": "대한전문건설신문",
    "kmecnews.co.kr": "기계설비신문",
    "kscnews.co.kr": "전문건설신문",
    "ikld.kr": "국토일보",
    "dnews.co.kr": "대한경제",
}


def _publisher(link: str) -> str:
    dom = urlparse(link).netloc.replace("www.", "")
    return _DOMAIN_PUBLISHER.get(dom, dom or "네이버뉴스")


def _strip(text: str) -> str:
    text = _TAG_RE.sub("", text or "")
    return text.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()


def _search(keyword: str) -> list:
    cid = (os.environ.get("NAVER_CLIENT_ID") or "").strip()
    csec = (os.environ.get("NAVER_CLIENT_SECRET") or "").strip()
    if not (cid and csec):
        logger.warning("NAVER_CLIENT_ID/SECRET 미설정 — 네이버 건너뜀")
        return []
    headers = {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec}
    params = {"query": f'"{keyword}"', "display": 20, "sort": "date"}
    try:
        resp = requests.get(NAVER_NEWS_API, headers=headers, params=params, timeout=10)
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.error("네이버 검색 실패(%s): %s", keyword, e)
        return []
    if data.get("errorCode"):
        logger.error("네이버 API 오류 %s: %s", data.get("errorCode"), data.get("errorMessage"))
        return []
    return data.get("items", [])


def fetch() -> list:
    """네이버 검색 API 키워드별 최근 24h 기사. seen 미적용."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    sources = [(kw, "조합·협회", True) for kw in COMPANY_KEYWORDS]
    for category, kws in CATEGORY_KEYWORDS.items():
        sources.extend((kw, category, False) for kw in kws)

    out = []
    seen_links = set()
    for keyword, category, is_company in sources:
        for it in _search(keyword):
            headline = _strip(it.get("title", ""))
            desc = _strip(it.get("description", ""))
            text = headline + " " + desc
            if not all(tok in text for tok in keyword.split()):   # 광역매칭 노이즈 제거
                continue
            link = it.get("originallink") or it.get("link") or ""
            if not link or link in seen_links:
                continue
            published_at = None
            try:
                dt = parsedate_to_datetime(it.get("pubDate", ""))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    continue
                published_at = dt.isoformat()
            except (TypeError, ValueError):
                pass
            article = {
                "keyword": keyword, "category": category, "is_company": is_company,
                "title": f"{headline} - {_publisher(link)}", "link": link, "description": desc,
            }
            if published_at:
                article["published_at"] = published_at
            out.append(article)
            seen_links.add(link)
    return out
```

- [ ] **Step 4: 통과 확인** — `python3 -m pytest tests/test_source_naver.py -v` → 4개 통과.

- [ ] **Step 5: `crawler.py`에 네이버 연결** — import + SOURCES 수정:

```python
import source_google
import source_naver
...
SOURCES = [source_naver, source_google]
```

- [ ] **Step 6: 실행 + 커밋** — `python3 -m pytest -q` 통과:

```bash
git add source_naver.py tests/test_source_naver.py crawler.py
git commit -m "feat: 네이버 검색 API 소스 추가"
```

---

### Task 3: 전문지 RSS 소스 (기계설비신문)

**Files:**
- Create: `source_rss.py`, `tests/test_source_rss.py`
- Modify: `config.py`, `crawler.py`

- [ ] **Step 1: `config.py`에 피드 목록 추가** — 파일 끝에:

```python
# 직접 구독하는 전문지 RSS (네이버 색인이 얇은 우리 조합 매체 보험)
TRADE_RSS_FEEDS = [
    {"name": "기계설비신문", "url": "https://www.kmecnews.co.kr/rss/allArticle.xml"},
]
```

- [ ] **Step 2: `tests/test_source_rss.py` 작성**

```python
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import time, importlib


def _entry(title, link, summary="", pub="2026-06-05 08:00:00"):
    e = MagicMock()
    e.get = lambda k, d="": {
        "title": title, "link": link, "summary": summary,
        "published_parsed": time.strptime(pub, "%Y-%m-%d %H:%M:%S"),
    }.get(k, d)
    return e


def _feed(entries):
    f = MagicMock(); f.entries = entries; return f


def _frozen_dt():
    fixed = datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc)  # 18:00 KST
    m = MagicMock(spec=datetime)
    m.now.side_effect = lambda tz=None: fixed
    m.fromtimestamp.side_effect = datetime.fromtimestamp
    return m


FEEDS = [{"name": "기계설비신문", "url": "http://feed/x"}]


def test_rss_keeps_company_relevant_with_suffix():
    import source_rss
    importlib.reload(source_rss)
    e = _entry("기계설비건설공제조합 신규 사업 발표", "http://kmec/1", "조합 소식")
    with patch("source_rss.feedparser.parse", return_value=_feed([e])), \
         patch("source_rss.TRADE_RSS_FEEDS", FEEDS), \
         patch("source_rss.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_rss.CATEGORY_KEYWORDS", {}):
        source_rss.datetime = _frozen_dt()
        out = source_rss.fetch()
    assert len(out) == 1
    assert out[0]["title"] == "기계설비건설공제조합 신규 사업 발표 - 기계설비신문"
    assert out[0]["is_company"] is True
    assert out[0]["link"] == "http://kmec/1"


def test_rss_drops_irrelevant_articles():
    import source_rss
    importlib.reload(source_rss)
    e = _entry("롯데건설 봉사활동 진행", "http://kmec/2", "사회공헌")
    with patch("source_rss.feedparser.parse", return_value=_feed([e])), \
         patch("source_rss.TRADE_RSS_FEEDS", FEEDS), \
         patch("source_rss.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_rss.CATEGORY_KEYWORDS", {}):
        source_rss.datetime = _frozen_dt()
        out = source_rss.fetch()
    assert out == []


def test_rss_classifies_industry_category():
    import source_rss
    importlib.reload(source_rss)
    e = _entry("스마트건설 기술 도입 확대", "http://kmec/3", "신기술")
    with patch("source_rss.feedparser.parse", return_value=_feed([e])), \
         patch("source_rss.TRADE_RSS_FEEDS", FEEDS), \
         patch("source_rss.COMPANY_KEYWORDS", []), \
         patch("source_rss.CATEGORY_KEYWORDS", {"신기술": ["스마트건설"]}):
        source_rss.datetime = _frozen_dt()
        out = source_rss.fetch()
    assert len(out) == 1
    assert out[0]["is_company"] is False
    assert out[0]["category"] == "신기술"


def test_rss_feed_error_isolated():
    import source_rss
    importlib.reload(source_rss)
    with patch("source_rss.feedparser.parse", side_effect=RuntimeError("down")), \
         patch("source_rss.TRADE_RSS_FEEDS", FEEDS), \
         patch("source_rss.COMPANY_KEYWORDS", ["기계설비건설공제조합"]), \
         patch("source_rss.CATEGORY_KEYWORDS", {}):
        source_rss.datetime = _frozen_dt()
        out = source_rss.fetch()
    assert out == []
```

- [ ] **Step 3: 실패 확인** — `python3 -m pytest tests/test_source_rss.py -v` → ModuleNotFoundError

- [ ] **Step 4: `source_rss.py` 구현**

```python
import calendar
import logging
from datetime import datetime, timedelta, timezone

import feedparser

from config import CATEGORY_KEYWORDS, COMPANY_KEYWORDS, TRADE_RSS_FEEDS

logger = logging.getLogger(__name__)


def classify(text: str):
    """텍스트에 조합/산업 키워드가 있으면 (is_company, category), 없으면 None."""
    for kw in COMPANY_KEYWORDS:
        if kw in text:
            return True, "조합·협회"
    for category, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if all(tok in text for tok in kw.split()):
                return False, category
    return None


def _published_at(entry, cutoff):
    """(iso 또는 None, 최근여부). 발행시각 모르면 보수적으로 최근=True."""
    ps = entry.get("published_parsed")
    if not ps:
        return None, True
    try:
        dt = datetime.fromtimestamp(calendar.timegm(ps), tz=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None, True
    return (None, False) if dt < cutoff else (dt.isoformat(), True)


def fetch() -> list:
    """전문지 RSS에서 조합/산업 관련 최근 24h 기사. seen 미적용."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    out = []
    seen_links = set()
    for feed_cfg in TRADE_RSS_FEEDS:
        name = feed_cfg["name"]
        try:
            feed = feedparser.parse(feed_cfg["url"])
        except Exception as e:
            logger.error("RSS 피드 실패(%s): %s", name, e)
            continue
        for entry in feed.entries:
            headline = entry.get("title", "")
            desc = entry.get("summary", "")
            cls = classify(headline + " " + desc)
            if cls is None:
                continue
            is_company, category = cls
            link = entry.get("link", "")
            if not link or link in seen_links:
                continue
            published_at, recent = _published_at(entry, cutoff)
            if not recent:
                continue
            article = {
                "keyword": name, "category": category, "is_company": is_company,
                "title": f"{headline} - {name}", "link": link, "description": desc,
            }
            if published_at:
                article["published_at"] = published_at
            out.append(article)
            seen_links.add(link)
    return out
```

- [ ] **Step 5: 통과 확인** — `python3 -m pytest tests/test_source_rss.py -v` → 4개 통과.

- [ ] **Step 6: `crawler.py`에 RSS 연결**

```python
import source_google
import source_naver
import source_rss
...
SOURCES = [source_naver, source_google, source_rss]
```

- [ ] **Step 7: 실행 + 커밋** — `python3 -m pytest -q` 통과:

```bash
git add source_rss.py tests/test_source_rss.py config.py crawler.py
git commit -m "feat: 전문지 RSS 소스(기계설비신문) 추가"
```

---

### Task 4: 소스 간 동일 기사 cluster 일치 검증 + 스모크

**Files:**
- Test: `tests/test_crawler.py` (통합 테스트 추가)

- [ ] **Step 1: cluster 일치 테스트 추가** — 같은 헤드라인이 매체 접미사만 다르게 세 소스로 들어와도 enrich가 같은 cluster_id를 주는지(→ 저장/푸시 dedup가 1건으로 합침) 검증. `tests/test_crawler.py` 끝에 추가:

```python
def test_same_headline_across_sources_gets_same_cluster_id():
    import enrich
    arts = [
        {"title": "전문건설공제조합 피치 A+ 유지 - 대한전문건설신문", "description": "", "link": "http://a", "keyword": "k", "category": "조합·협회", "is_company": True},
        {"title": "전문건설공제조합 피치 A+ 유지 - 네이버뉴스", "description": "", "link": "http://b", "keyword": "k", "category": "조합·협회", "is_company": True},
        {"title": "전문건설공제조합 피치 A+ 유지 - 기계설비신문", "description": "", "link": "http://c", "keyword": "k", "category": "조합·협회", "is_company": True},
    ]
    clustered = enrich.cluster_articles(arts)
    ids = {c["cluster_id"] for c in clustered}
    assert len(ids) == 1   # 매체만 달라도 같은 사건 → 한 cluster
```

(`enrich.cluster_articles`는 `normalize_title`로 " - 매체명" 접미사를 떼고 정규화 제목으로 클러스터링하므로, 매체만 다른 동일 헤드라인은 같은 cluster_id를 받는다.)

- [ ] **Step 2: 실행** — `python3 -m pytest tests/test_crawler.py -v` → 통과(클러스터 함수명 확인 반영). 그다음 전체:

Run: `python3 -m pytest -q`
Expected: 전체 통과(신규 source 테스트 12개 + crawler 5개 + 기존 전부).

- [ ] **Step 3: 임포트 스모크**

Run: `python3 -c "import main, crawler, source_google, source_naver, source_rss; print('import OK')"`
Expected: `import OK`

- [ ] **Step 4: 커밋**

```bash
git add tests/test_crawler.py
git commit -m "test: 소스 간 동일 기사 cluster 일치 통합 테스트"
```

---

## 배포 (구현·검증 완료 후)

`main` 머지 → VM cron `git pull --rebase`로 코드 자동 반영. 네이버 키는 이미 `config.env`에 존재. 머지 후 `monitor.log`에서 네이버/RSS 소스 수집 로그와 발행~수집 지연 단축 확인.

---

## Self-Review 결과

- **스펙 커버리지:** source_google(Task 1)·source_naver(Task 2)·source_rss(Task 3)·crawler 합치기(Task 1~3)·config TRADE_RSS_FEEDS(Task 3)·제목"헤드라인-매체명"으로 cluster 호환(전 소스 + Task 4 검증)·에러격리(각 소스 + crawler)·관련도 필터(naver/rss)·네이버 한도(설계 수치, 코드 영향 없음) 모두 대응.
- **플레이스홀더:** 없음 — 모든 코드/테스트 단계에 실제 내용. 단 Task 4 Step 1은 enrich 클러스터 함수명 확인을 명시(코드베이스 의존)로 처리.
- **타입 일관성:** 각 소스 `fetch()->list[dict]`, 공통 dict 키(keyword/category/is_company/title/link/description/published_at) 일치. crawler `SOURCES` 리스트 + `fetch_new_articles(seen)` 시그니처 유지(main.py 무변경). `classify()->Optional[tuple[bool,str]]`.
