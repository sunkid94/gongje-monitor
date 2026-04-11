import logging

from article_store import add_articles
from crawler import fetch_new_articles
from mailer import send_email
from seen_store import load_seen, save_seen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    seen = load_seen()
    new_articles = fetch_new_articles(seen)

    if not new_articles:
        logger.info("새 기사 없음. 이메일 미발송.")
        return

    logger.info("새 기사 %d건 발견. 저장 및 이메일 발송 중...", len(new_articles))

    new_urls = {a["link"] for a in new_articles}
    save_seen(seen | new_urls)
    add_articles(new_articles)

    send_email(new_articles)
    logger.info("%d건 이슈 이메일 발송 완료.", len(new_articles))


if __name__ == "__main__":
    main()
