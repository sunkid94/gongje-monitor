import logging

from article_store import add_articles
from crawler import fetch_new_articles
from mailer import send_email
from seen_store import load_seen, save_seen
from summarizer import summarize_articles

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

    logger.info("새 기사 %d건 발견. 요약 중...", len(new_articles))
    summarized = summarize_articles(new_articles)

    new_urls = {a["link"] for a in summarized}
    send_email(summarized)
    save_seen(seen | new_urls)
    add_articles(summarized)
    logger.info("%d건 이슈 이메일 발송 완료.", len(summarized))


if __name__ == "__main__":
    main()
