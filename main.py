import logging

from crawler import fetch_new_articles
from mailer import send_email
from seen_store import load_seen, save_seen
from summarizer import summarize_article

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

    summarized = []
    for article in new_articles:
        try:
            summarized.append(summarize_article(article))
        except Exception as e:
            logger.error("요약 실패: %s — %s", article["link"], e)

    # 요약 완료된 URL은 이메일 성공 여부와 무관하게 seen에 저장
    # (재실행 시 Claude API 비용 이중 청구 방지)
    new_urls = {a["link"] for a in new_articles}
    save_seen(seen | new_urls)

    if not summarized:
        logger.error("모든 기사 요약 실패. 이메일 미발송.")
        return

    send_email(summarized)
    logger.info("%d건 이슈 이메일 발송 완료.", len(summarized))


if __name__ == "__main__":
    main()
