import logging
import sys

from article_store import add_articles, filter_duplicates
from crawler import fetch_new_articles
from enrich import enrich_articles
from mailer import send_email
from notifier import send_company_push
from seen_store import load_seen, save_seen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main(skip_email: bool = False) -> None:
    seen = load_seen()
    new_articles = fetch_new_articles(seen)

    if not new_articles:
        logger.info("새 기사 없음. 처리 종료.")
        return

    logger.info("새 기사 %d건 발견. enrich 중...", len(new_articles))
    enriched = enrich_articles(new_articles)

    # Google News 리다이렉트 URL 회전으로 인한 동일 매체+동일 클러스터 재수집 차단.
    # seen 갱신은 dedup 전에 — 중복 기사 URL 도 다음 페치에서 다시 안 잡히도록.
    new_urls = {a["link"] for a in enriched}
    save_seen(seen | new_urls)

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
    add_articles(deduped)
    send_company_push(deduped)
    logger.info("%d건 처리 완료 (email=%s).", len(deduped), not skip_email)


if __name__ == "__main__":
    main(skip_email="--no-email" in sys.argv)
