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
        desc = a.get("description", "")
        if len(desc) > 200:
            desc = desc[:200] + "..."
        lines += [
            "━" * 40,
            f"[{a['keyword']}]",
            "━" * 40,
            f"제목: {a['title']}",
            f"링크: {a['link']}",
            f"내용: {desc}",
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
