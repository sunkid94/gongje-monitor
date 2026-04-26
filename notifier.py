"""OneSignal Web Push 알림 발송 — 조합 관련 새 기사가 있을 때만 실행."""
import logging
import os
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

ONESIGNAL_APP_ID = "0b046ff0-ddd8-46be-beb0-55eb415dc8ba"
ONESIGNAL_API_URL = "https://onesignal.com/api/v1/notifications"
SITE_URL = "https://sunkid94.github.io/gongje-monitor/"
ICON_URL = SITE_URL + "icons/icon-192.png"


def _build_payload(company_articles: list) -> dict:
    n = len(company_articles)
    if n == 1:
        title = "[CIG] 새 조합 기사"
        body = company_articles[0].get("title", "")
    else:
        title = f"[CIG] 새 조합 기사 {n}건"
        body = " · ".join(a.get("title", "") for a in company_articles[:3])
        if n > 3:
            body += f" 외 {n - 3}건"

    return {
        "app_id": ONESIGNAL_APP_ID,
        "included_segments": ["Subscribed Users"],
        "headings": {"en": title, "ko": title},
        "contents": {"en": body, "ko": body},
        "url": SITE_URL,
        "chrome_web_icon": ICON_URL,
        "chrome_web_badge": ICON_URL,
    }


def send_company_push(articles: Iterable[dict]) -> None:
    """is_company 기사 한 건이라도 있으면 전체 구독자에게 푸시 발송.

    실패해도 메인 흐름을 막지 않도록 예외는 로그만 남기고 swallow.
    """
    company_articles = [a for a in articles if a.get("is_company")]
    if not company_articles:
        logger.info("조합 기사 없음 — 푸시 알림 건너뜀")
        return

    api_key = os.environ.get("ONESIGNAL_REST_API_KEY")
    if not api_key:
        logger.warning("ONESIGNAL_REST_API_KEY 미설정 — 푸시 알림 건너뜀")
        return

    payload = _build_payload(company_articles)
    headers = {
        "Authorization": f"Basic {api_key}",
        "Content-Type": "application/json; charset=utf-8",
    }

    try:
        r = requests.post(ONESIGNAL_API_URL, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        logger.info(
            "OneSignal 푸시 발송: 조합 기사 %d건, OneSignal 응답 recipients=%s id=%s",
            len(company_articles),
            data.get("recipients"),
            data.get("id"),
        )
    except requests.HTTPError as e:
        logger.error(
            "OneSignal 푸시 실패 (HTTP %s): %s",
            getattr(e.response, "status_code", "?"),
            getattr(e.response, "text", str(e)),
        )
    except Exception as e:
        logger.error("OneSignal 푸시 실패: %s", e)
