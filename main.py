import logging
import sys

from article_store import add_articles
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

    new_urls = {a["link"] for a in enriched}
    if skip_email:
        logger.info("--no-email 모드: 이메일 스킵 (%d건)", len(enriched))
    else:
        send_email(enriched)
    save_seen(seen | new_urls)
    add_articles(enriched)
    send_company_push(enriched)
    logger.info("%d건 처리 완료 (email=%s).", len(enriched), not skip_email)


if __name__ == "__main__":
    main(skip_email="--no-email" in sys.argv)
