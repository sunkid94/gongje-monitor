import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD, RECIPIENTS

_ICON = {"긍정": "✅", "부정": "⚠️", "중립": "➖"}
_BADGE = {"긍정": "🟢 긍정", "부정": "🔴 부정", "중립": "⚪ 중립"}


def build_email_subject(articles: list) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    first_keyword = articles[0]["keyword"]
    count = len(articles)
    if count == 1:
        return f"[이슈 알림] {first_keyword} ({now})"
    return f"[이슈 알림] {first_keyword} 외 {count - 1}건 ({now})"


def build_email_body(articles: list) -> str:
    lines = []
    for a in articles:
        icon = _ICON.get(a["importance"], "➖")
        badge = _BADGE.get(a["importance"], "⚪ 중립")
        lines += [
            "━" * 40,
            f"[{a['keyword']}] {icon} {a['importance']}",
            "━" * 40,
            f"제목: {a['title']}",
            f"링크: {a['link']}",
            f"요약: {a['summary']}",
            f"중요도: {badge}",
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

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, RECIPIENTS, msg.as_string())
