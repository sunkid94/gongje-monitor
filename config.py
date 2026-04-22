import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.env"))

GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENTS = os.environ["RECIPIENTS"].split(",")

COMPANY_KEYWORDS = [
    "기계설비건설공제조합",
    "엔지니어링공제조합",
    "건설공제조합",
    "전문건설공제조합",
]

CATEGORY_KEYWORDS = {
    "정책·규제": ["건설산업기본법", "국토교통부 건설", "건설업 규제"],
    "시장·경기": ["건설경기", "건설 PF", "건설수주"],
    "안전·사고": ["중대재해 건설", "건설현장 안전"],
    "노동·인력": ["건설 노동"],
    "종합건설사": [
        "삼성물산 건설", "현대건설", "DL이앤씨", "대우건설", "GS건설",
        "포스코이앤씨", "롯데건설", "SK에코플랜트",
        "HDC현대산업개발", "현대엔지니어링",
    ],
}

# 하위 호환 (crawler 등이 이전 이름 쓸 수 있어 유지)
KEYWORDS = COMPANY_KEYWORDS
INDUSTRY_KEYWORDS = [k for ks in CATEGORY_KEYWORDS.values() for k in ks]
