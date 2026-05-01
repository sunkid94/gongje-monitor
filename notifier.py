"""표준 Web Push (VAPID) 발송 — 새 조합 기사 발견 시 등록된 구독자 모두에게 푸시."""
import json
import logging
import os
from pathlib import Path
from typing import Iterable, List

from pywebpush import webpush, WebPushException

logger = logging.getLogger(__name__)

VAPID_CLAIMS_EMAIL = "mailto:2wodms@gmail.com"
SITE_URL = "https://sunkid94.github.io/gongje-monitor/"
SUBSCRIPTIONS_FILE = Path(__file__).resolve().parent / "subscriptions.json"


def _coerce_to_list(data) -> List[dict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _load_subscriptions() -> List[dict]:
    """구독 토큰 목록을 두 소스에서 로드 후 endpoint 기준으로 중복 제거하여 합침.
    1) 저장소의 subscriptions.json 파일 (주 소스)
    2) WEBPUSH_SUBSCRIPTIONS 환경변수 (legacy/백업)
    """
    items: List[dict] = []

    if SUBSCRIPTIONS_FILE.exists():
        try:
            data = json.loads(SUBSCRIPTIONS_FILE.read_text(encoding="utf-8"))
            items.extend(_coerce_to_list(data))
        except json.JSONDecodeError as e:
            logger.error("subscriptions.json 파싱 실패: %s", e)

    raw = (os.environ.get("WEBPUSH_SUBSCRIPTIONS") or "").strip()
    if raw:
        try:
            items.extend(_coerce_to_list(json.loads(raw)))
        except json.JSONDecodeError:
            logger.error("WEBPUSH_SUBSCRIPTIONS JSON 파싱 실패")

    seen = set()
    unique: List[dict] = []
    for sub in items:
        endpoint = sub.get("endpoint")
        if endpoint and endpoint not in seen:
            seen.add(endpoint)
            unique.append(sub)
    return unique


def _build_payload(company_articles: List[dict]) -> str:
    n = len(company_articles)
    if n == 1:
        title = "[CIG] 새 조합 기사"
        body = company_articles[0].get("title", "")
    else:
        title = f"[CIG] 새 조합 기사 {n}건"
        body = " · ".join(a.get("title", "") for a in company_articles[:3])
        if n > 3:
            body += f" 외 {n - 3}건"
    return json.dumps(
        {"title": title, "body": body, "url": SITE_URL, "tag": "cig-news"},
        ensure_ascii=False,
    )


def send_company_push(articles: Iterable[dict]) -> None:
    """is_company 기사가 한 건이라도 있으면 등록된 구독자 전원에게 푸시 발송."""
    company = [a for a in articles if a.get("is_company")]
    if not company:
        logger.info("조합 기사 없음 — 푸시 알림 건너뜀")
        return

    subs = _load_subscriptions()
    if not subs:
        logger.info("WEBPUSH_SUBSCRIPTIONS 미설정 — 푸시 알림 건너뜀")
        return

    private_key = (os.environ.get("VAPID_PRIVATE_KEY") or "").strip()
    if not private_key:
        logger.warning("VAPID_PRIVATE_KEY 미설정 — 푸시 알림 건너뜀")
        return

    payload = _build_payload(company)
    sent, failed = 0, 0
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
            )
            sent += 1
        except WebPushException as e:
            failed += 1
            endpoint = (sub.get("endpoint") or "")[:50]
            status = getattr(e.response, "status_code", "?") if e.response is not None else "?"
            logger.error("Web Push 발송 실패 (status=%s, endpoint=%s…): %s", status, endpoint, e)

    logger.info("Web Push 발송 완료: 성공 %d / 실패 %d (조합 기사 %d건)", sent, failed, len(company))
