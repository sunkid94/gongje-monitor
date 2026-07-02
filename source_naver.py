import html
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
    dom = urlparse(link).netloc.removeprefix("www.")
    return _DOMAIN_PUBLISHER.get(dom, dom or "네이버뉴스")


def _strip(text: str) -> str:
    """HTML 태그 제거 후 엔티티(&quot; &amp; &apos; &#... 등) 모두 해제."""
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def _search(keyword: str) -> list:
    cid = (os.environ.get("NAVER_CLIENT_ID") or "").strip()
    csec = (os.environ.get("NAVER_CLIENT_SECRET") or "").strip()
    if not (cid and csec):
        logger.warning("NAVER_CLIENT_ID/SECRET 미설정 — 네이버 건너뜀")
        return []
    headers = {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec}
    params = {"query": f'"{keyword}"', "display": 50, "sort": "date"}
    try:
        resp = requests.get(NAVER_NEWS_API, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.error("네이버 검색 실패(%s): %s", keyword, e)
        return []
    if data.get("errorCode"):
        logger.error("네이버 API 오류 %s: %s", data.get("errorCode"), data.get("errorMessage"))
        return []
    return data.get("items", [])


def fetch(seen=frozenset()) -> list:
    """네이버 검색 API 키워드별 최근 24h 기사. seen 의 link 는 건너뜀."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    sources = [(kw, "조합·협회", True) for kw in COMPANY_KEYWORDS]
    for category, kws in CATEGORY_KEYWORDS.items():
        sources.extend((kw, category, False) for kw in kws)

    out = []
    seen_links = set(seen)
    for keyword, category, is_company in sources:
        for it in _search(keyword):
            headline = _strip(it.get("title", ""))
            desc = _strip(it.get("description", ""))
            text = headline + " " + desc
            if not all(tok in text for tok in keyword.split()):
                continue
            link = it.get("originallink") or it.get("link") or ""
            if not link or link in seen_links:
                continue
            published_at = None
            try:
                dt = parsedate_to_datetime(it.get("pubDate", ""))
                if dt.tzinfo is None:
                    # tz 없는 pubDate 는 한국 사이트라 KST 로 해석(UTC 오라벨 시 +9h 밀림)
                    dt = dt.replace(tzinfo=timezone(timedelta(hours=9)))
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
