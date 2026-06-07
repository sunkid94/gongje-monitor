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


def fetch(seen=frozenset()) -> list:
    """구글 뉴스 RSS 최근 24h 기사. 원문 발행 7일 초과분 폐기.

    seen 에 있는 link 는 resolve_published_time(HTTP 비용) 전에 건너뛴다.
    """
    cutoff = datetime.now() - timedelta(hours=24)
    original_cutoff = datetime.now(timezone.utc) - timedelta(days=ORIGINAL_PUB_MAX_AGE_DAYS)
    articles = []
    seen_links = set(seen)
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
