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


def fetch(seen=frozenset()) -> list:
    """전문지 RSS에서 조합/산업 관련 최근 24h 기사. seen 의 link 는 건너뜀."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    out = []
    seen_links = set(seen)
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
