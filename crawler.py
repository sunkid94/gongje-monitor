import logging

import source_google

logger = logging.getLogger(__name__)

SOURCES = [source_google]


def fetch_new_articles(seen: set) -> list:
    """등록된 모든 소스를 수집해 합치고, link 가 seen 에 없는 것만(소스 간 중복도 제거) 반환."""
    out = []
    collected = set(seen)
    for source in SOURCES:
        try:
            items = source.fetch()
        except Exception as e:
            logger.error("소스 수집 실패 %s: %s", getattr(source, "__name__", source), e)
            continue
        for a in items:
            link = a.get("link", "")
            if not link or link in collected:
                continue
            out.append(a)
            collected.add(link)
    return out
