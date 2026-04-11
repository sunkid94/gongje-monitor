import html
import requests
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, KEYWORDS

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"


def _strip_html(text: str) -> str:
    text = text.replace("<b>", "").replace("</b>", "")
    return html.unescape(text)


def search_news(keyword: str) -> list:
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": keyword, "display": 20, "sort": "date"}
    response = requests.get(NAVER_NEWS_URL, headers=headers, params=params)
    response.raise_for_status()
    items = response.json().get("items", [])
    return [
        {
            "keyword": keyword,
            "title": _strip_html(item["title"]),
            "link": item["link"],
            "description": _strip_html(item["description"]),
            "pubDate": item["pubDate"],
        }
        for item in items
    ]


def fetch_new_articles(seen: set) -> list:
    cutoff = datetime.now() - timedelta(hours=24)
    articles = []
    collected_links = set(seen)
    for keyword in KEYWORDS:
        for item in search_news(keyword):
            if item["link"] in collected_links:
                continue
            try:
                pub_dt = parsedate_to_datetime(item["pubDate"]).replace(tzinfo=None)
                if pub_dt < cutoff:
                    continue
            except (ValueError, TypeError):
                pass  # 날짜 파싱 실패 시 포함
            articles.append(item)
            collected_links.add(item["link"])
    return articles
