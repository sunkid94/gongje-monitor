import logging

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

    logger.info("새 기사 %d건 발견. 이메일 발송 중...", len(new_articles))

    # seen 저장을 이메일 발송 전에 수행 (재실행 시 중복 방지)
    new_urls = {a["link"] for a in new_articles}
    save_seen(seen | new_urls)

    send_email(new_articles)
    logger.info("%d건 이슈 이메일 발송 완료.", len(new_articles))


if __name__ == "__main__":
    main()
