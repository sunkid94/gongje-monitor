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
