import calendar
from datetime import datetime, timedelta

import feedparser

from config import KEYWORDS

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={}&hl=ko&gl=KR&ceid=KR:ko"


def fetch_news_rss(keyword: str) -> list:
    feed = feedparser.parse(GOOGLE_NEWS_RSS.format(keyword))
    articles = []
    for entry in feed.entries:
        articles.append({
            "keyword": keyword,
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
    for keyword in KEYWORDS:
        for item in fetch_news_rss(keyword):
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
