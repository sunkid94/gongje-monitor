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
    "대한기계설비건설협회",
]

# 영문/특수 브랜드 별칭 — AI가 모를 수 있는 것만 (한글 약칭은 AI가 인식).
# 키는 반드시 COMPANY_KEYWORDS 에 있는 조직명이어야 함 (enrich._build_tracked_orgs 가 COMPANY_KEYWORDS 기준으로 순회).
COMPANY_ALIASES = {
    "전문건설공제조합": ["K-FINCO"],
    "기계설비건설공제조합": ["CIG"],   # 우리 조합
}

CATEGORY_KEYWORDS = {
    "정책·규제": ["건설산업기본법", "국토교통부 건설", "건설업 규제"],
    "시장·경기": ["건설경기", "건설 PF", "건설수주"],
    "안전·노동": ["중대재해 건설", "건설현장 안전", "건설 노동"],
    "신기술": ["건설 신기술", "스마트건설", "모듈러 건설"],
    "종합건설사": [
        "두산에너빌리티", "삼성중공업", "대우건설", "엘지씨엔에스", "두산퓨얼셀",
        "에이치디씨현대산업개발", "롯데건설", "포스코이앤씨", "에스지씨이앤씨", "신세계건설",
    ],
}

# 하위 호환 (crawler 등이 이전 이름 쓸 수 있어 유지)
KEYWORDS = COMPANY_KEYWORDS
INDUSTRY_KEYWORDS = [k for ks in CATEGORY_KEYWORDS.values() for k in ks]

# 직접 구독하는 전문지 RSS (네이버 색인이 얇은 우리 조합 매체 보험)
TRADE_RSS_FEEDS = [
    {"name": "기계설비신문", "url": "https://www.kmecnews.co.kr/rss/allArticle.xml"},
]
