import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.env"))

GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENTS = os.environ["RECIPIENTS"].split(",")

KEYWORDS = [
    "기계설비건설공제조합",
    "엔지니어링공제조합",
    "건설공제조합",
    "전문건설공제조합",
]

INDUSTRY_KEYWORDS = [
    "건설산업기본법",
    "국토교통부 건설",
    "건설업 규제",
    "건설경기",
    "건설 PF",
    "건설수주",
    "중대재해 건설",
    "건설현장 안전",
    "건설 노동",
]
