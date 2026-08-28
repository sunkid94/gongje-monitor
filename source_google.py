import calendar
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import feedparser

from article_store import is_empty_stub
from config import CATEGORY_KEYWORDS, COMPANY_KEYWORDS, KEYWORD_CANONICAL
from pub_date import resolve_published_time_and_content

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={}&hl=ko&gl=KR&ceid=KR:ko"
ORIGINAL_PUB_MAX_AGE_DAYS = 7   # 원문 발행이 이보다 오래되면 폐기(구글 재색인 대응)
_KST = timezone(timedelta(hours=9))  # tz 없는 원문 발행시각은 한국 사이트라 KST 로 해석


def _fetch_keyword(keyword: str, category: str, is_company: bool) -> list:
    feed = feedparser.parse(GOOGLE_NEWS_RSS.format(quote(keyword)))
    articles = []
    for entry in feed.entries:
        title = entry.get("title", "")
        description = entry.get("summary", "")
        if is_empty_stub(title, description):
            continue
        articles.append({
            # 검색은 헤드라인 실제 표기로, 저장·표시는 대표 키워드로 통일
            "keyword": KEYWORD_CANONICAL.get(keyword, keyword),
            "category": category, "is_company": is_company,
            "title": title, "link": entry.get("link", ""),
            "description": description, "published_parsed": entry.get("published_parsed"),
        })
    return articles


def fetch(seen=frozenset()) -> list:
    """구글 뉴스 RSS 최근 24h 기사. 원문 발행 7일 초과분 폐기, 발행일 미확인분 보류.

    seen 에 있는 link 는 resolve_published_time(HTTP 비용) 전에 건너뛴다.
    """
    cutoff = datetime.now() - timedelta(hours=24)
    original_cutoff = datetime.now(timezone.utc) - timedelta(days=ORIGINAL_PUB_MAX_AGE_DAYS)
    articles = []
    seen_links = set(seen)
    sources = [(kw, "조합·협회", True) for kw in COMPANY_KEYWORDS]
    for category, kws in CATEGORY_KEYWORDS.items():
        sources.extend((kw, category, False) for kw in kws)
    for keyword, category, is_company in sources:
        for item in _fetch_keyword(keyword, category, is_company):
            if item["link"] in seen_links:
                continue
            pub_struct = item.pop("published_parsed")
            if pub_struct:
                try:
                    pub_dt = datetime.fromtimestamp(calendar.timegm(pub_struct))
                    if pub_dt < cutoff:
                        continue
                except (ValueError, TypeError, OverflowError):
                    pass
            original_pub, content, real_url = resolve_published_time_and_content(item["link"])
            # 구글 링크가 원문 대신 이미지 팝업으로 디코딩되면(클릭 시 사진만 뜸) 제외.
            # 같은 기사는 etnews.com 직접 경로로 정상 링크와 함께 유입되므로 뉴스 손실 없음.
            if real_url and "/tools/image_popup.html" in real_url:
                seen_links.add(item["link"])
                continue
            if original_pub is None:
                # 발행일 미확인 기사는 싣지 않는다(보류). fail-open 으로 통과시키면
                # 구글이 재색인한 옛 기사를 7일 가드로 거를 수 없다
                # (2026-08-28, 3월 기사가 최신처럼 푸시된 사건). 반환·seen 저장을
                # 안 하면 구글이 매 런 새 토큰 URL 을 발급하므로 다음 런에 자연히
                # 재시도된다 — 일시 오류면 수 분 지연 후 정상 유입.
                # 트레이드오프: 지속 실패 사이트(예: metroseoul 타임아웃, ikld SSL)의
                # 구글 경유 기사는 유입되지 않는다 — 필요 시 사이트별 원인을 해결할 것.
                logger.info("발행일 미확인 — 보류: %s", item.get("title", "")[:60])
                seen_links.add(item["link"])
                continue
            if original_pub.tzinfo is None:
                original_pub = original_pub.replace(tzinfo=_KST)
            if original_pub < original_cutoff:
                seen_links.add(item["link"])
                continue
            item["published_at"] = original_pub.isoformat()
            # 구글뉴스 description 은 본문 없는 HTML 링크뿐 — 원문 발행사 요약이 있으면
            # 그것으로 교체해 enrich 가 실제 내용으로 요약하게 한다.
            if content and len(content) > 40:
                item["description"] = content
            articles.append(item)
            seen_links.add(item["link"])
    return articles
