import logging
from urllib.parse import urlparse

import source_google
import source_naver
import source_rss
from config import BLOCKED_DOMAINS, BLOCKED_CONTENT_KEYWORDS

logger = logging.getLogger(__name__)

SOURCES = [source_naver, source_google, source_rss]


def is_blocked_domain(link: str) -> bool:
    """link 의 호스트가 BLOCKED_DOMAINS 와 정확히 같거나 서브도메인이면 True."""
    try:
        host = (urlparse(link).hostname or "").lower()
    except ValueError:
        return False
    return any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)


def has_blocked_content(article: dict) -> bool:
    """제목·본문에 BLOCKED_CONTENT_KEYWORDS(연예 전용 단어 등)가 있으면 True."""
    hay = (article.get("title", "") or "") + " " + (article.get("description", "") or "")
    return any(k in hay for k in BLOCKED_CONTENT_KEYWORDS)


def fetch_new_articles(seen: set, sources=None) -> list:
    """등록된 소스를 수집해 합치고, link 가 seen 에 없는 것만(소스 간 중복도 제거) 반환.

    sources 미지정 시 SOURCES(전체). fast-path 는 [source_rss] 만 넘겨 저지연 수집.
    차단 도메인(연예/포토 매체 등 — 조합명이 장소로만 걸리는 곳)은 enrich 전에 제외.
    """
    sources = sources if sources is not None else SOURCES
    out = []
    collected = set(seen)
    for source in sources:
        try:
            items = source.fetch(seen)
        except Exception as e:
            logger.error("소스 수집 실패 %s: %s", getattr(source, "__name__", source), e)
            continue
        for a in items:
            link = a.get("link", "")
            if not link or link in collected:
                continue
            if is_blocked_domain(link):
                logger.info("차단 도메인 제외: %s", link)
                continue
            if has_blocked_content(a):
                logger.info("차단 키워드 제외: %s", (a.get("title", "") or "")[:40])
                continue
            out.append(a)
            collected.add(link)
    return out


def fetch_trade_only(seen: set) -> list:
    """fast-path 전용 — 직접 전문지 RSS 만 수집(구글/네이버 제외). 발행 직후 저지연 포착용."""
    return fetch_new_articles(seen, [source_rss])
