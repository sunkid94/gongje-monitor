from unittest.mock import patch, MagicMock
import pytest


SAMPLE_ARTICLES = [
    {
        "keyword": "기계설비건설공제조합",
        "title": "기계설비건설공제조합 신규 발표",
        "link": "http://news.google.com/articles/1",
        "description": "신규 사업 계획을 발표했다.",
    },
    {
        "keyword": "건설공제조합",
        "title": "건설공제조합 사고 급증",
        "link": "http://news.google.com/articles/2",
        "description": "보증 사고 건수가 증가했다.",
    },
]


def test_build_email_body_contains_article_info():
    with patch("mailer.GMAIL_ADDRESS", "test@gmail.com"), \
         patch("mailer.GMAIL_APP_PASSWORD", "pw"), \
         patch("mailer.RECIPIENTS", ["exec@company.com"]):
        import mailer
        import importlib
        importlib.reload(mailer)
        body = mailer.build_email_body(SAMPLE_ARTICLES)

    assert "기계설비건설공제조합" in body
    assert "http://news.google.com/articles/1" in body
    assert "신규 사업 계획을 발표했다." in body
    assert "건설공제조합" in body


def test_build_email_subject_single_article():
    with patch("mailer.GMAIL_ADDRESS", "test@gmail.com"), \
         patch("mailer.GMAIL_APP_PASSWORD", "pw"), \
         patch("mailer.RECIPIENTS", ["exec@company.com"]):
        import mailer
        import importlib
        importlib.reload(mailer)
        subject = mailer.build_email_subject([SAMPLE_ARTICLES[0]])

    assert "[이슈 알림]" in subject
    assert "기계설비건설공제조합" in subject


def test_build_email_subject_multiple_articles():
    with patch("mailer.GMAIL_ADDRESS", "test@gmail.com"), \
         patch("mailer.GMAIL_APP_PASSWORD", "pw"), \
         patch("mailer.RECIPIENTS", ["exec@company.com"]):
        import mailer
        import importlib
        importlib.reload(mailer)
        subject = mailer.build_email_subject(SAMPLE_ARTICLES)

    assert "외 1건" in subject


def test_build_email_subject_empty_raises():
    with patch("mailer.GMAIL_ADDRESS", "test@gmail.com"), \
         patch("mailer.GMAIL_APP_PASSWORD", "pw"), \
         patch("mailer.RECIPIENTS", ["exec@company.com"]):
        import mailer
        import importlib
        importlib.reload(mailer)
        with pytest.raises(ValueError):
            mailer.build_email_subject([])


def test_send_email_calls_smtp():
    mock_smtp = MagicMock()
    mock_smtp.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

    with patch("mailer.smtplib.SMTP_SSL", mock_smtp), \
         patch("mailer.GMAIL_ADDRESS", "test@gmail.com"), \
         patch("mailer.GMAIL_APP_PASSWORD", "pw"), \
         patch("mailer.RECIPIENTS", ["exec@company.com"]):
        import mailer
        import importlib
        importlib.reload(mailer)
        mailer.send_email(SAMPLE_ARTICLES)

    mock_smtp.assert_called_once_with("smtp.gmail.com", 465)
