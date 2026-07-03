import calendar
import logging
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from config import CATEGORY_KEYWORDS, COMPANY_KEYWORDS, TRADE_RSS_FEEDS

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ci-monitor/1.0)"}
_TIMEOUT = 10
_KST = timezone(timedelta(hours=9))
# 원본 pubDate 문자열에 타임존 표기(+0900, Z, GMT 등)가 있는지 감지
_TZ_MARKER_RE = re.compile(r"([+-]\d{2}:?\d{2}|\bZ|\b[A-Z]{2,5})\s*$")


def _fetch_body(url: str) -> str:
    """원문 페이지 HTML 반환(실패 시 ""). classify 가 부분문자열 매칭이라 원본 HTML로 충분."""
    try:
        r = requests.get(url, timeout=_TIMEOUT, headers=_HEADERS)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.warning("RSS 본문 페치 실패(%s): %s", url, e)
        return ""


def classify(text: str):
    """텍스트에 조합/산업 키워드가 있으면 (is_company, category, matched_keyword), 없으면 None."""
    for kw in COMPANY_KEYWORDS:
        if kw in text:
            return True, "조합·협회", kw
    for category, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if all(tok in text for tok in kw.split()):
                return False, category, kw
    return None


def _published_at(entry, cutoff):
    """(iso 또는 None, 최근여부). 발행시각 모르면 보수적으로 최근=True.

    한국 전문지 RSS 는 tz 없는 naive KST pubDate(예 '2026-07-02 17:23:55')를 주는데
    feedparser 가 이를 UTC 로 간주 → 그대로 저장하면 사이트(KST 렌더링)에서 +9h 밀려
    다음날로 표시된다. 원본 문자열에 tz 표기가 없으면 KST 로 재해석한다.
    """
    ps = entry.get("published_parsed")
    if not ps:
        return None, True
    try:
        dt = datetime.fromtimestamp(calendar.timegm(ps), tz=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None, True
    raw = (entry.get("published", "") or entry.get("updated", "")).strip()
    if raw and not _TZ_MARKER_RE.search(raw):
        # feedparser 가 naive 시각을 UTC 로 라벨링한 것 → 같은 벽시계 숫자를 KST 로 교정
        dt = dt.replace(tzinfo=_KST)
    return (None, False) if dt < cutoff else (dt.isoformat(), True)


def fetch(seen=frozenset()) -> list:
    """전문지 RSS에서 조합/산업 관련 최근 24h 기사. seen 의 link 는 건너뜀."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    out = []
    seen_links = set(seen)
    for feed_cfg in TRADE_RSS_FEEDS:
        name = feed_cfg["name"]
        try:
            # UA 필수: 일부 매체 WAF(cenews 등)가 feedparser 기본 UA를 403 차단 → XML 대신
            # HTML 에러페이지를 줘 entries=0 이 된다. 브라우저 UA 로 파싱해야 피드가 열린다.
            feed = feedparser.parse(feed_cfg["url"], agent=_HEADERS["User-Agent"])
        except Exception as e:
            logger.error("RSS 피드 실패(%s): %s", name, e)
            continue
        for entry in feed.entries:
            headline = entry.get("title", "")
            desc = entry.get("summary", "")
            link = entry.get("link", "")
            if not link or link in seen_links:
                continue
            published_at, recent = _published_at(entry, cutoff)
            if not recent:
                continue
            # 1차: 제목+요약 매칭. 실패 시 본문을 받아 재분류(조직명이 본문에만 있는 기사 포착).
            # 본문 페치는 미수집·최근·제목매칭실패 항목에만 발생하므로 비용이 제한적.
            cls = classify(headline + " " + desc)
            if cls is None:
                cls = classify(headline + " " + desc + " " + _fetch_body(link))
            if cls is None:
                continue
            is_company, category, matched_kw = cls
            article = {
                "keyword": matched_kw, "category": category, "is_company": is_company,
                "title": f"{headline} - {name}", "link": link, "description": desc,
            }
            if published_at:
                article["published_at"] = published_at
            out.append(article)
            seen_links.add(link)
    return out
