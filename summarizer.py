import logging
import os
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def summarize_article(title: str, description: str) -> Optional[str]:
    prompt = (
        f"다음 뉴스 기사를 한국어로 2~3줄로 요약해주세요. 핵심 내용만 간결하게 작성하세요.\n\n"
        f"제목: {title}\n"
        f"내용: {description}\n\n"
        f"요약:"
    )
    try:
        message = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        logger.error("요약 실패 (title=%s): %s", title[:30], e)
        return None


def summarize_articles(articles: list) -> list:
    result = []
    for article in articles:
        summary = summarize_article(article["title"], article.get("description", ""))
        result.append({**article, "summary": summary})
    return result
