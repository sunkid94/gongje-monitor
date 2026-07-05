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

# 수집 차단 도메인 — 조합명이 '행사 장소'로만 걸리는 연예/포토 매체 등.
# 호스트가 정확히 일치하거나 서브도메인(.)으로 끝나면 차단. (예: job-post.co.kr → 황금촬영상 레드카펫 포토 기사 대량 유입)
BLOCKED_DOMAINS = [
    "job-post.co.kr",
]

# 수집 차단 내용 키워드 — 제목·본문에 있으면 도메인 무관하게 제외.
# 연예 전용 단어만(정상 건설/조합 기사엔 거의 안 나옴) — 조합 건물이 행사 장소로 걸리는 레드카펫·포토 기사 차단.
# 주의: '시상식'·'배우' 등 정상기사에도 나오는 흔한 단어는 넣지 말 것(오탐).
BLOCKED_CONTENT_KEYWORDS = [
    "황금촬영상",
    "레드카펫",
    "포토월",
    "쇼호스트",
]

# 수집 차단 발행처 — 기사가 아닌 블로그/플랫폼 글. publisher(제목 끝 '- 매체') 기준 정확히 일치 시 제외.
# 구글뉴스 경유라 링크가 news.google.com 이어도 publisher 로 잡힘.
BLOCKED_PUBLISHERS = [
    "브런치",
    "Naver Blog",      # 구글뉴스가 네이버블로그를 이렇게 표기(실측)
    "네이버 블로그",
    "네이버블로그",
    "Tistory",         # 티스토리(구글뉴스 영문 표기)
    "티스토리",
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
        "현대산업개발", "롯데건설", "포스코이앤씨", "SGC이앤씨", "SGC E&C", "신세계건설",
    ],
}

# 수집 검색어 → 저장·표시용 대표 키워드. 한 회사를 여러 표기로 검색할 때 결과를 하나로 통합.
# (구글뉴스는 음차표기로 최근 기사를 잘 못 잡음 — 헤드라인 실제 표기로 검색하되 표시는 통일.)
KEYWORD_CANONICAL = {
    "SGC E&C": "SGC이앤씨",
}

# 하위 호환 (crawler 등이 이전 이름 쓸 수 있어 유지)
KEYWORDS = COMPANY_KEYWORDS
INDUSTRY_KEYWORDS = [k for ks in CATEGORY_KEYWORDS.values() for k in ks]

# 직접 구독하는 전문지 RSS (네이버 색인이 얇은 우리 조합 매체 보험)
TRADE_RSS_FEEDS = [
    {"name": "기계설비신문", "url": "https://www.kmecnews.co.kr/rss/allArticle.xml"},
    # 구글 색인이 느린 건설 전문지 직접 구독 — 발행 즉시 포착(색인 지연 우회). 2026-07-02 추가.
    {"name": "대한전문건설신문", "url": "https://www.koscaj.com/rss/allArticle.xml"},
    {"name": "한국건설신문", "url": "https://www.kscnews.co.kr/rss/allArticle.xml"},
    # 기계설비협회 기사 다수 게재 — 배너 오염 없음 확인(무관기사 본문에 조합/협회 키워드 無). 2026-07-03 추가.
    {"name": "건설이코노미뉴스", "url": "https://www.cenews.kr/rss/allArticle.xml"},
    # (비즈워크 제외: 전 페이지 '건설공제조합' 배너로 본문폴백이 전 기사 오분류 — 순손해)
]

# 종합건설사 카테고리명 (article_store 와 동일 값 — crawler 필터가 참조)
CORP_CATEGORY = "종합건설사"

# 종합건설사 뉴스 한정어 — 이 중 하나가 제목·요약에 있어야 수집(건설 활동 뉴스만).
# 없으면 조선·방산·원전·주가·실적 등 무관 뉴스로 보고 제외. 놓치는 게 있으면 단어 추가.
CORP_QUALIFIERS = ["수주", "공사", "현장", "착공", "준공", "재건축", "시공", "재개발", "계약"]
