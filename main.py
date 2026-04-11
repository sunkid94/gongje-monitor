from crawler import fetch_new_articles
from mailer import send_email
from seen_store import load_seen, save_seen
from summarizer import summarize_article


def main() -> None:
    seen = load_seen()
    new_articles = fetch_new_articles(seen)

    if not new_articles:
        print("새 기사 없음. 이메일 미발송.")
        return

    print(f"새 기사 {len(new_articles)}건 발견. 요약 중...")
    summarized = [summarize_article(article) for article in new_articles]

    send_email(summarized)
    print(f"{len(summarized)}건 이슈 이메일 발송 완료.")

    new_urls = {a["link"] for a in new_articles}
    save_seen(seen | new_urls)


if __name__ == "__main__":
    main()
