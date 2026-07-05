import logging
import sys

from article_store import add_articles, filter_duplicates
from crawler import fetch_new_articles, fetch_trade_only
from enrich import enrich_articles
from mailer import send_email
from notifier import send_company_push
from seen_store import load_seen, save_seen

import archive_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main(skip_email: bool = False, fast: bool = False) -> None:
    seen = load_seen()
    # fast-path: 직접 전문지 RSS 만(구글/네이버 제외) — 2분 주기 저지연 실행용.
    new_articles = fetch_trade_only(seen) if fast else fetch_new_articles(seen)

    if not new_articles:
        if not fast:
            logger.info("새 기사 없음. 처리 종료.")
        return

    logger.info("새 기사 %d건 발견. enrich 중...", len(new_articles))
    enriched = enrich_articles(new_articles)

    # 수집한 모든 기사 link 를 seen 에 기록 — 게이트 제외분도 포함.
    # (과거엔 enriched=게이트통과분만 seen 에 넣어 제외 기사를 매 런 재-enrich 했다.
    #  full run(5분)에선 비용이 작았지만 fast-path(2분)+직접RSS는 URL 고정이라 같은
    #  무관 기사를 무한 재판정 → API 비용 폭증. 그래서 fetched 전체를 seen 처리한다.
    #  Google 은 URL 이 회전하므로 재수집 시 새 URL 로 어차피 재평가됨.)
    save_seen(seen | {a["link"] for a in new_articles})

    deduped = filter_duplicates(enriched)
    if len(deduped) < len(enriched):
        logger.info("중복 제거: %d → %d 건 (publisher+cluster_id 일치)", len(enriched), len(deduped))
    if not deduped:
        logger.info("새 기사 모두 기존 클러스터와 중복 — 이메일/푸시/저장 건너뜀.")
        return

    if skip_email:
        logger.info("--no-email 모드: 이메일 스킵 (%d건)", len(deduped))
    else:
        send_email(deduped)
    archive_store.append_articles(deduped)
    add_articles(deduped)
    send_company_push(deduped)
    logger.info("%d건 처리 완료 (email=%s).", len(deduped), not skip_email)


if __name__ == "__main__":
    _fast = "--fast" in sys.argv
    main(skip_email=_fast or "--no-email" in sys.argv, fast=_fast)
