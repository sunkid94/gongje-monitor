import calendar
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import feedparser

from article_store import is_empty_stub
from config import CATEGORY_KEYWORDS, COMPANY_KEYWORDS
from pub_date import resolve_published_time

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={}&hl=ko&gl=KR&ceid=KR:ko"

# Google News는 옛 기사를 새 사건과 함께 재인덱싱하여 RSS pubDate를 최근으로 노출
# 시키기도 한다. 원문 발행일이 이 일수보다 오래된 항목은 폐기.
ORIGINAL_PUB_MAX_AGE_DAYS = 7


def fetch_news_rss(keyword: str, category: str, is_company: bool) -> list:
    feed = feedparser.parse(GOOGLE_NEWS_RSS.format(quote(keyword)))
    articles = []
    for entry in feed.entries:
        title = entry.get("title", "")
        description = entry.get("summary", "")
        # Google News 가 가끔 발급하는 "제목만 있는" 빈 entry (예: "장관 - 국토교통부")
        # 는 enrich 단계에서 Claude API 비용만 쓰고 사용자에겐 노이즈가 되므로 여기서 차단.
        if is_empty_stub(title, description):
            continue
        articles.append({
            "keyword": keyword,
            "category": category,
            "is_company": is_company,
            "title": title,
            "link": entry.get("link", ""),
            "description": description,
            "published_parsed": entry.get("published_parsed"),
        })
    return articles


def fetch_new_articles(seen: set) -> list:
    cutoff = datetime.now() - timedelta(hours=24)
    original_cutoff = datetime.now(timezone.utc) - timedelta(days=ORIGINAL_PUB_MAX_AGE_DAYS)
    articles = []
    collected_links = set(seen)

    sources = [(kw, "조합·협회", True) for kw in COMPANY_KEYWORDS]
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

            original_pub = resolve_published_time(item["link"])
            if original_pub is not None:
                if original_pub.tzinfo is None:
                    original_pub = original_pub.replace(tzinfo=timezone.utc)
                if original_pub < original_cutoff:
                    collected_links.add(item["link"])
                    continue
                item["published_at"] = original_pub.isoformat()

            articles.append(item)
            collected_links.add(item["link"])
    return articles
