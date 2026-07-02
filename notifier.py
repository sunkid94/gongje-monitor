"""표준 Web Push (VAPID) 발송 — 새 조합 기사 발견 시 등록된 구독자 모두에게 푸시.

구독자 목록은 두 형식 모두 허용:
  1) 플레인:  {"endpoint": "...", "keys": {...}}
  2) 래핑:    {"name": "홍길동 본부장", "subscription": {"endpoint": "...", "keys": {...}}}

만료(410 Gone)·인증 실패(401/403/404)가 발생하면 관리자에게 메일로 통지.
"""
import hashlib
import json
import logging
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path
from typing import Iterable, List

import push_dedup

from pywebpush import webpush, WebPushException

logger = logging.getLogger(__name__)

VAPID_CLAIMS_EMAIL = "mailto:2wodms@seolbi.com"
SITE_URL = "https://sunkid94.github.io/gongje-monitor/"
SUBSCRIPTIONS_FILE = Path(__file__).resolve().parent / "subscriptions.json"
ADMIN_NOTICE_RECIPIENT = "2wodms@seolbi.com"
EXPIRED_STATUS = {404, 410}
AUTH_FAILED_STATUS = {401, 403}


def _coerce_to_list(data) -> List:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _normalize(item: dict) -> dict:
    """플레인/래핑 양쪽을 통일된 형태로 변환: {sub, name}"""
    if "subscription" in item and isinstance(item["subscription"], dict):
        return {"sub": item["subscription"], "name": item.get("name") or "(이름 미상)"}
    return {"sub": item, "name": item.get("_name") or "(이름 미상)"}


def _load_subscriptions() -> List[dict]:
    """subscriptions.json + WEBPUSH_SUBSCRIPTIONS env에서 로드, endpoint 기준 중복 제거."""
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

    seen, unique = set(), []
    for it in items:
        norm = _normalize(it)
        endpoint = norm["sub"].get("endpoint")
        if endpoint and endpoint not in seen:
            seen.add(endpoint)
            unique.append(norm)
    return unique


def _build_payload(company_articles: List[dict]) -> str:
    n = len(company_articles)
    if n == 1:
        title = "[CIG] 새 조합 기사"
        body = company_articles[0].get("title", "")
        # 단일 기사는 그 기사 링크로 보내 알림 클릭 시 본문으로 이동(링크 없으면 대시보드)
        url = company_articles[0].get("link") or SITE_URL
    else:
        title = f"[CIG] 새 조합 기사 {n}건"
        body = " · ".join(a.get("title", "") for a in company_articles[:3])
        if n > 3:
            body += f" 외 {n - 3}건"
        # 여러 기사는 특정 기사로 못 보내므로 대시보드로
        url = SITE_URL
    # 기사 내용 기반 고유 꼬리표 — 같은 꼬리표면 새 알림이 앞 알림을 덮어써 "떴다 사라짐".
    # 기사마다 달라야 알림이 안 덮어쓰고 쌓인다. (같은 기사는 같은 꼬리표로 안정)
    basis = "|".join((a.get("link") or a.get("title", "")) for a in company_articles)
    tag = "cig-" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
    return json.dumps(
        {"title": title, "body": body, "url": url, "tag": tag},
        ensure_ascii=False,
    )


def _send_admin_alert(expired: List[dict], auth_failed: List[dict]) -> None:
    if not (expired or auth_failed):
        return
    addr = os.environ.get("GMAIL_ADDRESS")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not (addr and pw):
        logger.warning("GMAIL_ADDRESS/PASSWORD 미설정 — 만료 알림 메일 건너뜀")
        return

    lines = ["[CIG 알림 시스템 알림]\n", "새 조합 기사 푸시 발송 중 다음 문제가 감지되었습니다.\n"]
    if expired:
        lines.append(f"\n■ 만료된 구독 {len(expired)}건 (해당 분께 PWA 재실행 → 🔔 → '다시 등록' 안내 부탁드립니다):")
        for it in expired:
            ep = (it["sub"].get("endpoint") or "")[:80]
            lines.append(f"  - {it['name']}  |  endpoint: {ep}…")
    if auth_failed:
        lines.append(f"\n■ 인증 실패 구독 {len(auth_failed)}건 (VAPID 키 점검 필요):")
        for it in auth_failed:
            ep = (it["sub"].get("endpoint") or "")[:80]
            lines.append(f"  - {it['name']}  |  endpoint: {ep}…")
    lines.append("\n— CIG 이슈 모니터 자동 감지\n  " + SITE_URL)

    body = "\n".join(lines)
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"[CIG 알림 시스템] 만료 구독 {len(expired)}건 감지"
    msg["From"] = addr
    msg["To"] = ADMIN_NOTICE_RECIPIENT
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(addr, pw)
            server.sendmail(addr, [ADMIN_NOTICE_RECIPIENT], msg.as_string())
        logger.info("관리자 만료 알림 메일 발송: %s", ADMIN_NOTICE_RECIPIENT)
    except smtplib.SMTPException as e:
        logger.error("관리자 알림 메일 발송 실패: %s", e)


def send_company_push(articles: Iterable[dict]) -> None:
    """is_company 기사 중 최근 24h 내 미발송 스토리만 구독자 전원에게 푸시.

    주의: 스토리 '발송됨' 기록(pushed.json)은 발송 *시도* 시점에 남는다 — 전 구독자
    발송이 실패해도 해당 스토리는 24h 동안 재발송되지 않는다. (개별 webpush 호출 간
    롤백이 불가능하므로 필터를 발송 전에 커밋하는 의도된 트레이드오프.)
    """
    company = [a for a in articles if a.get("is_company")]
    if not company:
        logger.info("조합 기사 없음 — 푸시 알림 건너뜀")
        return

    subs = _load_subscriptions()
    if not subs:
        logger.info("구독자 없음 — 푸시 알림 건너뜀")
        return

    private_key = (os.environ.get("VAPID_PRIVATE_KEY") or "").strip()
    if not private_key:
        logger.warning("VAPID_PRIVATE_KEY 미설정 — 푸시 알림 건너뜀")
        return

    # 발송 가능 확인 후에 스토리 중복 필터 (미발송 스토리를 기록하지 않도록 순서 중요)
    to_push, suppressed = push_dedup.filter_unpushed(company, datetime.now().astimezone())
    if suppressed:
        logger.info("스토리 중복 %d건 푸시 억제", len(suppressed))
    if not to_push:
        logger.info("모두 기존 스토리 중복 — 푸시 알림 건너뜀")
        return

    payload = _build_payload(to_push)
    sent, expired, auth_failed, other_failed = 0, [], [], 0
    for item in subs:
        try:
            webpush(
                subscription_info=item["sub"],
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
            )
            sent += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None) if e.response is not None else None
            if status in EXPIRED_STATUS:
                expired.append(item)
            elif status in AUTH_FAILED_STATUS:
                auth_failed.append(item)
            else:
                other_failed += 1
            logger.error("Web Push 실패 [%s] (status=%s, name=%s)", (item["sub"].get("endpoint") or "")[:50], status, item["name"])

    logger.info(
        "Web Push 발송 결과: 성공 %d / 만료 %d / 인증실패 %d / 기타실패 %d (신규 스토리 %d건)",
        sent, len(expired), len(auth_failed), other_failed, len(to_push),
    )
    _send_admin_alert(expired, auth_failed)
