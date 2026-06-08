import hashlib
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

import anthropic

from article_store import format_collected_at, parse_collected_at
from config import COMPANY_KEYWORDS, COMPANY_ALIASES

logger = logging.getLogger(__name__)

_PUBLISHER_SUFFIX_RE = re.compile(r"\s+-\s+([^-]+?)\s*$")
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)
_VALID_SENTIMENTS = {"positive", "neutral", "negative"}
_client: Optional[anthropic.Anthropic] = None


def _build_tracked_orgs() -> str:
    parts = []
    for org in COMPANY_KEYWORDS:
        aliases = COMPANY_ALIASES.get(org)
        parts.append(f"{org}(={'/'.join(aliases)})" if aliases else org)
    return ", ".join(parts)


_TRACKED_ORGS = _build_tracked_orgs()


def _strip_code_fence(text: str) -> str:
    m = _CODE_FENCE_RE.match(text.strip())
    return m.group(1).strip() if m else text.strip()


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


_RELEVANCE_CRITERIA = """
- about_org: 이 기사가 다음 조직 중 어느 하나에 관한 뉴스인지 판단: {orgs}
  · true: 목록 중 한 곳의 활동·발표·실적·인사·사건 등을 직접 다루거나 의미 있게 관련됨 (별칭 포함 — 예: K-FINCO=전문건설공제조합)
  · false: 목록의 어느 조직과도 무관한 게 명백한 경우만 (일반 칼럼·법률해설·사설, 무관한 부고종합/인사 목록, 단순 벤더·타기관 뉴스, 본문에 등장하지 않고 사이트 메뉴·관련기사 링크로만 걸린 경우 등). 애매하면 true."""

_RELEVANCE_FIELD = ', "about_org": true|false'

_ENRICH_PROMPT = """다음 뉴스 기사를 분석해 JSON으로 답하세요.

제목: {title}
내용: {description}

판단 기준:
- 감정 톤은 "건설업계 전반과 기계설비건설공제조합" 시점에서 평가합니다.
  · positive: 업계 호재 (수주 증가, 규제 완화, 시장 확대 등)
  · negative: 업계 악재 (사고, 규제 강화, PF 위기, 부정 이슈 등)
  · neutral: 사실 보도, 양면적, 판단 어려움
- 요약은 한국어 2~3줄, 핵심만.{relevance_criteria}

JSON 형식 (다른 텍스트 없이 이것만):
{{"summary": "...", "sentiment": "positive|neutral|negative"{relevance_field}}}"""


def enrich_article(title: str, description: str, orgs: Optional[str] = None) -> dict:
    fallback = {
        "summary": (description or "")[:200],
        "sentiment": "neutral",
    }
    relevance_criteria = _RELEVANCE_CRITERIA.format(orgs=orgs) if orgs else ""
    relevance_field = _RELEVANCE_FIELD if orgs else ""
    prompt = _ENRICH_PROMPT.format(
        title=title, description=description,
        relevance_criteria=relevance_criteria, relevance_field=relevance_field,
    )
    try:
        msg = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _strip_code_fence(msg.content[0].text)
        data = json.loads(raw)
        sentiment = data.get("sentiment", "neutral")
        if sentiment not in _VALID_SENTIMENTS:
            sentiment = "neutral"
        result = {
            "summary": data.get("summary", "").strip() or fallback["summary"],
            "sentiment": sentiment,
        }
        if orgs and "about_org" in data:
            val = data["about_org"]
            if isinstance(val, bool):
                result["about_org"] = val
            elif isinstance(val, str):
                result["about_org"] = val.strip().lower() not in ("false", "no", "0", "")
            # 그 외 타입은 무시(키 미포함 → 호출측이 보수적으로 통과)
        return result
    except Exception as e:
        logger.warning("enrich_article 폴백 (title=%s): %s", title[:30], e)
        return fallback


def calc_importance(article: dict, cluster_size: int, now: Optional[datetime] = None) -> int:
    if now is None:
        now = datetime.now().astimezone()
    elif now.tzinfo is None:
        now = now.astimezone()

    score = 0
    if article.get("is_company"):
        score += 5
    if article.get("sentiment") == "negative":
        score += 3
    score += min(cluster_size, 5)

    collected_at_str = article.get("collected_at")
    if collected_at_str:
        try:
            collected = parse_collected_at(collected_at_str)
            if (now - collected) < timedelta(hours=24):
                score += 2
        except ValueError:
            pass

    return min(round(score * 10 / 15), 10)


def enrich_articles(articles: list) -> list:
    if not articles:
        return []

    clustered = cluster_articles(articles)
    cluster_sizes = Counter(a["cluster_id"] for a in clustered)

    enriched = []
    now = datetime.now().astimezone()
    now_str = format_collected_at(now)
    for a in clustered:
        title = a["title"]
        publisher = extract_publisher(title)
        title_clean = _PUBLISHER_SUFFIX_RE.sub("", title)
        orgs = _TRACKED_ORGS if a.get("is_company") else None
        ai = enrich_article(title_clean, a.get("description", ""), orgs=orgs)
        # 조합기사인데 추적 조직 어디와도 명백히 무관(about_org=false) → 제외 (보수적: 애매/누락은 통과)
        if a.get("is_company") and ai.get("about_org") is False:
            logger.info("관련도 게이트 제외 (keyword=%s): %s", a.get("keyword"), title_clean[:40])
            continue
        out = {
            **a,
            "publisher": publisher,
            "title_clean": title_clean,
            "summary": ai["summary"],
            "sentiment": ai["sentiment"],
            # collected_at 가짜 세팅 — calc_importance 의 24h 가산점 활성화용.
            # article_store.add_articles 가 나중에 진짜 시각으로 덮어쓰지만 importance 는 유지.
            "collected_at": a.get("collected_at") or now_str,
        }
        out["importance"] = calc_importance(out, cluster_sizes[a["cluster_id"]], now=now)
        enriched.append(out)

    return enriched


def extract_publisher(title: str) -> str:
    m = _PUBLISHER_SUFFIX_RE.search(title)
    return m.group(1).strip() if m else ""


def normalize_title(title: str) -> str:
    title = _PUBLISHER_SUFFIX_RE.sub("", title)
    return re.sub(r"[\s\W_]+", "", title.lower())


def _tokens(title: str) -> set:
    cleaned = _PUBLISHER_SUFFIX_RE.sub("", title)
    return set(re.findall(r"\w+", cleaned.lower()))


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _cluster_id(norm: str) -> str:
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:4]


def cluster_articles(articles: list) -> list:
    """각 기사에 cluster_id 부여. 정규화 제목 완전 일치 또는 토큰 자카드 0.85 이상이면 동일 cluster."""
    clusters = []  # list of (representative_norm, cluster_id, token_set)
    result = []

    for a in articles:
        norm = normalize_title(a["title"])
        tokens = _tokens(a["title"])
        matched_id = None

        for rep_norm, cid, rep_tokens in clusters:
            if norm == rep_norm or _jaccard(tokens, rep_tokens) >= 0.85:
                matched_id = cid
                break

        if matched_id is None:
            matched_id = _cluster_id(norm or a["link"])
            clusters.append((norm, matched_id, tokens))

        result.append({**a, "cluster_id": matched_id})

    return result
