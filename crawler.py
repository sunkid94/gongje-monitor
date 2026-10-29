import inspect
import logging
from urllib.parse import urlparse

import source_google
import source_naver
import source_rss
from config import BLOCKED_DOMAINS, BLOCKED_CONTENT_KEYWORDS, CORP_CATEGORY, CORP_QUALIFIERS

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


def lacks_corp_qualifier(article: dict) -> bool:
    """종합건설사 카테고리인데 제목·요약에 활동 한정어가 하나도 없으면 True(제외 대상).

    조합 기사·기타 카테고리는 항상 False(필터 대상 아님)."""
    if article.get("category") != CORP_CATEGORY:
        return False
    hay = (article.get("title", "") or "") + " " + (article.get("description", "") or "")
    return not any(q in hay for q in CORP_QUALIFIERS)


def _accepts_seen_out(source) -> bool:
    """소스 fetch 가 seen_out 인자를 받는지(직접 RSS 만 해당, 구글/네이버는 fetch(seen))."""
    try:
        return "seen_out" in inspect.signature(source.fetch).parameters
    except (TypeError, ValueError):
        return False


def _mark_judged(seen_out, link: str) -> None:
    if seen_out is not None and link:
        seen_out.add(link)


def fetch_new_articles(seen: set, sources=None, seen_out=None) -> list:
    """등록된 소스를 수집해 합치고, link 가 seen 에 없는 것만(소스 간 중복도 제거) 반환.

    sources 미지정 시 SOURCES(전체). fast-path 는 [source_rss] 만 넘겨 저지연 수집.
    차단 도메인(연예/포토 매체 등 — 조합명이 장소로만 걸리는 곳)은 enrich 전에 제외.
    seen_out: set 을 넘기면 소스가 '무관 판정 완료'한 링크와, 여기서 걸러낸 링크를 담아준다 —
    호출자(main)가 seen 에 합쳐 저장해 같은 기사를 매 런 재판정하지 않게 한다.
    단, 걸러낸 링크 기록은 seen_out 을 받는 소스(URL 고정인 직접 RSS)에서 온 기사만. 구글은 매 런
    새 토큰 URL 을 발급(URL 회전)해 기록해도 재판정 방지 효과가 없고 seen.json 만 런당 100건+ 비대해진다.
    """
    sources = sources if sources is not None else SOURCES
    out = []
    collected = set(seen)
    for source in sources:
        stable_urls = seen_out is not None and _accepts_seen_out(source)
        judged_out = seen_out if stable_urls else None
        try:
            items = source.fetch(seen, seen_out=seen_out) if stable_urls else source.fetch(seen)
        except Exception as e:
            logger.error("소스 수집 실패 %s: %s", getattr(source, "__name__", source), e)
            continue
        for a in items:
            link = a.get("link", "")
            if not link or link in collected:
                continue
            if is_blocked_domain(link):
                logger.info("차단 도메인 제외: %s", link)
                _mark_judged(judged_out, link)
                continue
            if has_blocked_content(a):
                logger.info("차단 키워드 제외: %s", (a.get("title", "") or "")[:40])
                _mark_judged(judged_out, link)
                continue
            if lacks_corp_qualifier(a):
                logger.info("종건사 한정어 없음 제외: %s", (a.get("title", "") or "")[:40])
                _mark_judged(judged_out, link)
                continue
            out.append(a)
            collected.add(link)
    return out


def fetch_trade_only(seen: set, seen_out=None) -> list:
    """fast-path 전용 — 직접 전문지 RSS 만 수집(구글/네이버 제외). 발행 직후 저지연 포착용."""
    return fetch_new_articles(seen, [source_rss], seen_out=seen_out)
