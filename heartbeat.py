import logging
import os

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 5


def _ping(suffix: str = "") -> None:
    """HEALTHCHECK_URL 로 핑. 미설정 시 no-op. 모든 요청 예외는 삼키고 로그만."""
    url = (os.environ.get("HEALTHCHECK_URL") or "").strip()
    if not url:
        return
    try:
        requests.get(url + suffix, timeout=_TIMEOUT)
    except requests.RequestException as e:
        logger.warning("heartbeat 핑 실패(%s): %s", suffix or "success", e)


def ping() -> None:
    """정상 완료 신호."""
    _ping("")


def ping_fail() -> None:
    """실패 신호 — grace 대기 없이 즉시 알림 트리거."""
    _ping("/fail")
