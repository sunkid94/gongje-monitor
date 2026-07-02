import hashlib
import html
import json
import logging
import os
import re
import smtplib
from collections import Counter
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import anthropic

from article_store import format_collected_at, parse_collected_at
from config import COMPANY_KEYWORDS, COMPANY_ALIASES, BLOCKED_PUBLISHERS

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


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """HTML 태그·엔티티 제거 → 정제 텍스트. 구글뉴스 description 은 <a>·<font>·&nbsp; 등
    HTML 이라, 그대로 요약 입력/폴백에 쓰면 모델 품질 저하·요약에 raw HTML 노출(폴백 시)."""
    if not text:
        return ""
    t = _TAG_RE.sub(" ", text)
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


_RELEVANCE_CRITERIA = """
- about_org: 이 기사가 다음 조직 중 어느 하나에 관한 뉴스인지 판단: {orgs}
  · true: 목록 중 한 곳의 활동·발표·실적·인사·사건 등을 직접 다루거나 의미 있게 관련됨 (별칭 포함 — 예: K-FINCO=전문건설공제조합)
  · false: 목록의 어느 조직과도 무관한 게 명백한 경우만 (일반 칼럼·법률해설·사설, 무관한 부고종합/인사 목록, 단순 벤더·타기관 뉴스, 본문에 등장하지 않고 사이트 메뉴·관련기사 링크로만 걸린 경우, 조직이 행사 장소·건물명으로만 등장하고 기사의 실제 주제는 연예·시상식·포토·레드카펫 등 업계와 무관한 경우 등). 애매하면 true.
- event_label: 이 기사의 핵심 사건을 "대표조직명 + 핵심사건" 한 줄로 간결히. 대표조직은 위 목록의 정식 명칭 사용(예: K-FINCO→전문건설공제조합). 매체·표현이 달라도 같은 사건이면 같은 라벨이 나오게. 예: "대한기계설비건설협회 박종학 회장 별세", "전문건설공제조합 피치 신용등급 A+ 유지"."""

_RELEVANCE_FIELD = ', "about_org": true|false, "event_label": "..."'

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
    # 구글뉴스 description 은 HTML(<a>·<font>·&nbsp;) — 정제 후 사용해야 모델 입력 품질이
    # 좋고, 폴백 시에도 raw HTML 이 요약으로 새지 않는다.
    clean_desc = _strip_html(description)
    fallback = {
        "summary": clean_desc[:200],
        "sentiment": "neutral",
    }
    relevance_criteria = _RELEVANCE_CRITERIA.format(orgs=orgs) if orgs else ""
    relevance_field = _RELEVANCE_FIELD if orgs else ""
    prompt = _ENRICH_PROMPT.format(
        title=title, description=clean_desc,
        relevance_criteria=relevance_criteria, relevance_field=relevance_field,
    )
    last_err = None
    for attempt in (1, 2):  # 간헐적 빈 응답/파싱 실패 대응 — 1회 재시도 후 폴백
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
            if orgs and isinstance(data.get("event_label"), str) and data["event_label"].strip():
                result["event_label"] = data["event_label"].strip()
            return result
        except Exception as e:
            last_err = e
            if attempt == 1:
                logger.info("enrich 재시도 (title=%s): %s", title[:30], e)
    logger.warning("enrich_article 폴백 (title=%s): %s", title[:30], last_err)
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


# ─────────────────────────────────────────────────────────────
#  AI 요약 폴백 감지 + 관리자 알림
#  (enrich 실패 시 summary=description[:200] 로 대체됨. 폴백률이 급증하면
#   대개 Anthropic API 크레딧 소진이므로 관리자에게 메일로 통지한다.)
# ─────────────────────────────────────────────────────────────
_FALLBACK_ALERT_MIN_SAMPLE = 5       # 표본이 이보다 작으면 판단 보류
_FALLBACK_ALERT_THRESHOLD = 0.5      # 이 비율 이상 폴백이면 알림
_FALLBACK_ALERT_THROTTLE_HOURS = 6   # 같은 알림 재발송 최소 간격
_ENRICH_ALERT_STATE = str(Path(__file__).resolve().parent / ".enrich_alert_state.json")
_ENRICH_ALERT_RECIPIENT = "2wodms@seolbi.com"


def is_fallback_summary(summary: str, description: str) -> bool:
    """폴백 요약 판정 — enrich 실패 시 summary 는 정제된 description[:200] 가 된다.
    (구버전 raw HTML 폴백도 감지되도록 정제본·원본 양쪽과 비교.)"""
    if not summary:
        return False
    return summary == _strip_html(description or "")[:200] or summary == (description or "")[:200]


def should_alert(total: int, fallbacks: int, last_alert_iso: Optional[str],
                 now: datetime, *, min_sample: int = _FALLBACK_ALERT_MIN_SAMPLE,
                 threshold: float = _FALLBACK_ALERT_THRESHOLD,
                 throttle_hours: int = _FALLBACK_ALERT_THROTTLE_HOURS) -> bool:
    """폴백 알림을 보낼지 결정 (순수 함수)."""
    if total < min_sample:
        return False
    if fallbacks / total < threshold:
        return False
    if last_alert_iso:
        try:
            last = datetime.fromisoformat(last_alert_iso)
            if now - last < timedelta(hours=throttle_hours):
                return False
        except ValueError:
            pass
    return True


def _read_last_alert() -> Optional[str]:
    try:
        with open(_ENRICH_ALERT_STATE, encoding="utf-8") as f:
            return json.load(f).get("last_alert")
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_last_alert(iso: str) -> None:
    try:
        with open(_ENRICH_ALERT_STATE, "w", encoding="utf-8") as f:
            json.dump({"last_alert": iso}, f)
    except OSError as e:
        logger.warning("enrich 알림 상태 저장 실패: %s", e)


def _send_enrich_alert(total: int, fallbacks: int) -> None:
    addr = os.environ.get("GMAIL_ADDRESS")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not (addr and pw):
        logger.warning("GMAIL 미설정 — enrich 폴백 알림 메일 건너뜀")
        return
    rate = fallbacks / total * 100 if total else 0
    body = (
        "[CIG 알림 시스템] AI 요약(enrich) 폴백 급증 감지\n\n"
        f"이번 수집에서 {total}건 중 {fallbacks}건({rate:.0f}%)이 AI 요약에 실패해 "
        "원문 일부로 대체(폴백)되었습니다.\n\n"
        "가장 흔한 원인은 Anthropic API 크레딧 소진입니다. "
        "Console → Plans & Billing 에서 잔액/자동충전을 확인하세요.\n"
        "복구 후 과거 폴백 기사는 backfill_summaries.py 로 재요약할 수 있습니다.\n\n"
        "— CIG 이슈 모니터 자동 감지"
    )
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"[CIG 알림] AI 요약 폴백 {fallbacks}/{total}건 감지"
    msg["From"] = addr
    msg["To"] = _ENRICH_ALERT_RECIPIENT
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(addr, pw)
            server.sendmail(addr, [_ENRICH_ALERT_RECIPIENT], msg.as_string())
        logger.info("enrich 폴백 알림 메일 발송: %s", _ENRICH_ALERT_RECIPIENT)
    except smtplib.SMTPException as e:
        logger.error("enrich 폴백 알림 메일 발송 실패: %s", e)


def _maybe_alert_fallbacks(total: int, fallbacks: int) -> None:
    now = datetime.now().astimezone()
    if not should_alert(total, fallbacks, _read_last_alert(), now):
        return
    _send_enrich_alert(total, fallbacks)
    _write_last_alert(now.isoformat())


def enrich_articles(articles: list) -> list:
    if not articles:
        return []

    clustered = cluster_articles(articles)
    cluster_sizes = Counter(a["cluster_id"] for a in clustered)

    enriched = []
    total_enriched = 0
    fallback_count = 0
    now = datetime.now().astimezone()
    now_str = format_collected_at(now)
    for a in clustered:
        title = a["title"]
        publisher = extract_publisher(title)
        title_clean = _PUBLISHER_SUFFIX_RE.sub("", title)
        # 블로그/플랫폼 발행처(브런치 등)는 기사 아님 → AI 호출 전에 제외
        if publisher in BLOCKED_PUBLISHERS:
            logger.info("차단 발행처 제외 (%s): %s", publisher, title_clean[:40])
            continue
        orgs = _TRACKED_ORGS if a.get("is_company") else None
        ai = enrich_article(title_clean, a.get("description", ""), orgs=orgs)
        total_enriched += 1
        if is_fallback_summary(ai["summary"], a.get("description", "")):
            fallback_count += 1
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
        if "event_label" in ai:
            out["event_label"] = ai["event_label"]
        out["importance"] = calc_importance(out, cluster_sizes[a["cluster_id"]], now=now)
        enriched.append(out)

    _maybe_alert_fallbacks(total_enriched, fallback_count)
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
