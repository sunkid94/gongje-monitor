import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD, RECIPIENTS

logger = logging.getLogger(__name__)


def build_email_subject(articles: list) -> str:
    if not articles:
        raise ValueError("articles 목록이 비어있습니다.")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    first_keyword = articles[0]["keyword"]
    count = len(articles)
    if count == 1:
        return f"[이슈 알림] {first_keyword} ({now})"
    return f"[이슈 알림] {first_keyword} 외 {count - 1}건 ({now})"


def build_email_body(articles: list) -> str:
    lines = []
    for a in articles:
        body_text = a.get("summary") or a.get("description", "")
        if not a.get("summary") and len(body_text) > 200:
            body_text = body_text[:200] + "..."

        sentiment_mark = {"negative": "🔴", "positive": "🟢", "neutral": "⚪"}.get(
            a.get("sentiment", "neutral"), "⚪"
        )
        importance = a.get("importance", 0)
        category = a.get("category", "")
        publisher = a.get("publisher", "")
        title = a.get("title_clean") or a.get("title", "")

        meta_parts = [sentiment_mark, f"중요도 {importance}/10"]
        if category:
            meta_parts.append(f"[{category}]")
        if publisher:
            meta_parts.append(publisher)

        lines += [
            "━" * 40,
            " ".join(meta_parts),
            "━" * 40,
            f"제목: {title}",
            f"링크: {a['link']}",
            f"요약: {body_text}",
            "",
        ]
    return "\n".join(lines)


def send_email(articles: list) -> None:
    subject = build_email_subject(articles)
    body = build_email_body(articles)

    msg = MIMEMultipart()
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = ", ".join(RECIPIENTS)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, RECIPIENTS, msg.as_string())
    except smtplib.SMTPException as e:
        logger.error("이메일 발송 실패: %s", e)
        raise
