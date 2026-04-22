"""주간 요약 생성. 일요일 23시 cron.

사용법:
    python weekly_summary.py
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import anthropic

from article_store import load_articles

logger = logging.getLogger(__name__)

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weekly.json")

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


_PROMPT = """다음은 지난 한 주({period}) 동안 수집된 건설업계 핵심 이슈 {count}건입니다.
기계설비건설공제조합 임원에게 보고하는 주간 브리핑이라 가정하고,
각 이슈를 한국어로 2~3줄씩 요약하세요.

{items_block}

JSON 출력 (다른 텍스트 없이):
{{
  "period": "{period}",
  "items": [
    {{"category": "...", "headline": "...", "brief": "..."}},
    ... (총 {count}개)
  ]
}}"""


def select_top_clusters(articles: list, now: datetime, limit: int = 5) -> list:
    cutoff = now - timedelta(days=7)
    window = []
    for a in articles:
        try:
            collected = datetime.strptime(a.get("collected_at", ""), "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
        if collected >= cutoff:
            window.append(a)

    def take_by_threshold(threshold: int) -> list:
        filtered = [a for a in window if a.get("importance", 0) >= threshold]
        filtered.sort(key=lambda x: (-x.get("importance", 0), x.get("collected_at", "")))
        seen_clusters = set()
        picked = []
        for a in filtered:
            cid = a.get("cluster_id")
            if cid in seen_clusters:
                continue
            seen_clusters.add(cid)
            picked.append(a)
            if len(picked) >= limit:
                break
        return picked

    picks = take_by_threshold(6)
    if len(picks) < limit:
        picks = take_by_threshold(4)
    return picks[:limit]


def _build_items_block(articles: list) -> str:
    lines = []
    for i, a in enumerate(articles, 1):
        lines.append(f"이슈 {i} ── [{a.get('category', '')}]")
        lines.append(f"제목: {a.get('title_clean') or a.get('title', '')}")
        lines.append(f"요약: {a.get('summary', '')}")
        lines.append("")
    return "\n".join(lines)


def generate_weekly_summary(output_path: str = OUTPUT_PATH, now: Optional[datetime] = None) -> None:
    if now is None:
        now = datetime.now()

    articles = load_articles()
    top = select_top_clusters(articles, now=now)
    if not top:
        logger.info("주간 요약 대상 기사 없음. skip.")
        return

    period_end = now.strftime("%Y-%m-%d")
    period_start = (now - timedelta(days=6)).strftime("%Y-%m-%d")
    period = f"{period_start} ~ {period_end}"

    prompt = _PROMPT.format(
        period=period,
        count=len(top),
        items_block=_build_items_block(top),
    )

    try:
        msg = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(msg.content[0].text.strip())
    except Exception as e:
        logger.error("주간 요약 생성 실패: %s", e)
        return

    data["generated_at"] = now.strftime("%Y-%m-%dT%H:%M:%S")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("weekly.json 저장: %d건", len(data.get("items", [])))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    generate_weekly_summary()
