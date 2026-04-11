# 공제조합 이슈 모니터링 시스템 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 4개 공제조합 뉴스를 네이버 API로 수집하고 Claude AI로 요약·판단하여 Gmail로 임원에게 자동 보고하는 시스템 구축

**Architecture:** macOS cron이 1~2시간마다 `main.py`를 실행한다. `crawler.py`가 네이버 뉴스 검색 API로 신규 기사를 수집하고, `summarizer.py`가 Claude API로 요약 및 중요도를 판단한 뒤, `mailer.py`가 Gmail SMTP로 이메일을 발송한다. `seen_store.py`가 `seen.json`을 통해 중복 발송을 방지한다.

**Tech Stack:** Python 3.x, requests, anthropic, python-dotenv, smtplib (stdlib), pytest, unittest.mock

---

## 파일 구조

| 파일 | 역할 |
|------|------|
| `requirements.txt` | 의존 패키지 목록 |
| `.gitignore` | config.env 등 민감 파일 제외 |
| `config.env.example` | 설정 파일 템플릿 |
| `config.py` | config.env 로드, 상수 정의 |
| `seen_store.py` | seen.json 읽기/쓰기 (중복 방지) |
| `crawler.py` | 네이버 뉴스 검색 API 호출, 기사 수집 |
| `summarizer.py` | Claude API로 요약 + 중요도 판단 |
| `mailer.py` | Gmail SMTP 이메일 빌드 및 발송 |
| `main.py` | 전체 흐름 조율, cron 진입점 |
| `tests/test_seen_store.py` | seen_store 단위 테스트 |
| `tests/test_crawler.py` | crawler 단위 테스트 |
| `tests/test_summarizer.py` | summarizer 단위 테스트 |
| `tests/test_mailer.py` | mailer 단위 테스트 |

---

## Task 1: 프로젝트 초기 설정

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `config.env.example`
- Create: `tests/__init__.py`

- [ ] **Step 1: requirements.txt 생성**

```
requests==2.32.3
anthropic==0.40.0
python-dotenv==1.0.1
pytest==8.3.4
```

- [ ] **Step 2: .gitignore 생성**

```
config.env
seen.json
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 3: config.env.example 생성**

```
NAVER_CLIENT_ID=여기에_네이버_클라이언트_ID
NAVER_CLIENT_SECRET=여기에_네이버_클라이언트_시크릿
ANTHROPIC_API_KEY=여기에_Anthropic_API_키
GMAIL_ADDRESS=내이메일@gmail.com
GMAIL_APP_PASSWORD=여기에_Gmail_앱_비밀번호
RECIPIENTS=임원1@company.com,임원2@company.com
```

- [ ] **Step 4: tests 디렉토리 생성**

```bash
mkdir tests
touch tests/__init__.py
```

- [ ] **Step 5: 패키지 설치**

```bash
pip install -r requirements.txt
```

Expected: `Successfully installed` 메시지 확인

- [ ] **Step 6: 커밋**

```bash
git init
git add requirements.txt .gitignore config.env.example tests/__init__.py
git commit -m "chore: 프로젝트 초기 설정"
```

---

## Task 2: Config 로더 (config.py)

**Files:**
- Create: `config.py`

config.py는 환경 변수 로딩만 담당하므로 별도 테스트 없이 구성한다.

- [ ] **Step 1: config.py 생성**

```python
import os
from dotenv import load_dotenv

load_dotenv("config.env")

NAVER_CLIENT_ID = os.environ["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = os.environ["NAVER_CLIENT_SECRET"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENTS = os.environ["RECIPIENTS"].split(",")

KEYWORDS = [
    "기계설비건설공제조합",
    "엔지니어링공제조합",
    "건설공제조합",
    "전문건설공제조합",
]
```

- [ ] **Step 2: config.env 생성 (실제 키 입력)**

`config.env.example`을 복사하여 실제 값을 채운다.

```bash
cp config.env.example config.env
# config.env 파일을 열어 실제 API 키와 이메일 정보 입력
```

- [ ] **Step 3: 커밋**

```bash
git add config.py config.env.example
git commit -m "feat: config 로더 추가"
```

---

## Task 3: Seen Store (seen_store.py)

**Files:**
- Create: `seen_store.py`
- Test: `tests/test_seen_store.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_seen_store.py`:

```python
import json
import pytest
from unittest.mock import patch


def test_load_seen_returns_empty_set_when_file_missing():
    with patch("seen_store.SEEN_FILE", "/tmp/nonexistent_seen_xyz.json"):
        import seen_store
        import importlib
        importlib.reload(seen_store)
        result = seen_store.load_seen()
    assert result == set()


def test_load_seen_returns_urls_from_existing_file(tmp_path):
    seen_file = tmp_path / "seen.json"
    seen_file.write_text(json.dumps(["http://a.com", "http://b.com"]))
    with patch("seen_store.SEEN_FILE", str(seen_file)):
        import seen_store
        import importlib
        importlib.reload(seen_store)
        result = seen_store.load_seen()
    assert result == {"http://a.com", "http://b.com"}


def test_save_seen_writes_urls_to_file(tmp_path):
    seen_file = tmp_path / "seen.json"
    with patch("seen_store.SEEN_FILE", str(seen_file)):
        import seen_store
        import importlib
        importlib.reload(seen_store)
        seen_store.save_seen({"http://a.com", "http://b.com"})
    data = json.loads(seen_file.read_text())
    assert set(data) == {"http://a.com", "http://b.com"}
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_seen_store.py -v
```

Expected: `ERROR` (seen_store 모듈 없음)

- [ ] **Step 3: seen_store.py 구현**

```python
import json
import os

SEEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json")


def load_seen() -> set:
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_seen(seen: set) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_seen_store.py -v
```

Expected: 3개 테스트 모두 PASSED

- [ ] **Step 5: 커밋**

```bash
git add seen_store.py tests/test_seen_store.py
git commit -m "feat: seen store 추가 (중복 방지)"
```

---

## Task 4: 뉴스 크롤러 (crawler.py)

**Files:**
- Create: `crawler.py`
- Test: `tests/test_crawler.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_crawler.py`:

```python
from unittest.mock import patch, MagicMock
import pytest


MOCK_API_RESPONSE = {
    "items": [
        {
            "title": "<b>기계설비</b>건설공제조합 신규 공시",
            "link": "http://news.example.com/1",
            "description": "기계설비건설공제조합이 <b>신규</b> 사업 계획을 발표했다.",
            "pubDate": "Fri, 11 Apr 2026 10:00:00 +0900",
        }
    ]
}


def test_search_news_strips_html_tags():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("crawler.requests.get", return_value=mock_resp), \
         patch("crawler.NAVER_CLIENT_ID", "test_id"), \
         patch("crawler.NAVER_CLIENT_SECRET", "test_secret"):
        import crawler
        import importlib
        importlib.reload(crawler)
        result = crawler.search_news("기계설비건설공제조합")

    assert len(result) == 1
    assert "<b>" not in result[0]["title"]
    assert "<b>" not in result[0]["description"]
    assert result[0]["keyword"] == "기계설비건설공제조합"
    assert result[0]["link"] == "http://news.example.com/1"


def test_fetch_new_articles_excludes_seen_urls():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    seen = {"http://news.example.com/1"}

    with patch("crawler.requests.get", return_value=mock_resp), \
         patch("crawler.NAVER_CLIENT_ID", "test_id"), \
         patch("crawler.NAVER_CLIENT_SECRET", "test_secret"), \
         patch("crawler.KEYWORDS", ["기계설비건설공제조합"]):
        import crawler
        import importlib
        importlib.reload(crawler)
        result = crawler.fetch_new_articles(seen)

    assert result == []


def test_fetch_new_articles_includes_unseen_urls():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    seen = set()

    with patch("crawler.requests.get", return_value=mock_resp), \
         patch("crawler.NAVER_CLIENT_ID", "test_id"), \
         patch("crawler.NAVER_CLIENT_SECRET", "test_secret"), \
         patch("crawler.KEYWORDS", ["기계설비건설공제조합"]):
        import crawler
        import importlib
        importlib.reload(crawler)
        result = crawler.fetch_new_articles(seen)

    assert len(result) == 1
    assert result[0]["link"] == "http://news.example.com/1"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_crawler.py -v
```

Expected: `ERROR` (crawler 모듈 없음)

- [ ] **Step 3: crawler.py 구현**

```python
import requests
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, KEYWORDS

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"


def _strip_html(text: str) -> str:
    return text.replace("<b>", "").replace("</b>", "")


def search_news(keyword: str) -> list:
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": keyword, "display": 20, "sort": "date"}
    response = requests.get(NAVER_NEWS_URL, headers=headers, params=params)
    response.raise_for_status()
    items = response.json().get("items", [])
    return [
        {
            "keyword": keyword,
            "title": _strip_html(item["title"]),
            "link": item["link"],
            "description": _strip_html(item["description"]),
            "pubDate": item["pubDate"],
        }
        for item in items
    ]


def fetch_new_articles(seen: set) -> list:
    cutoff = datetime.now() - timedelta(hours=24)
    articles = []
    for keyword in KEYWORDS:
        for item in search_news(keyword):
            if item["link"] in seen:
                continue
            try:
                pub_dt = parsedate_to_datetime(item["pubDate"]).replace(tzinfo=None)
                if pub_dt < cutoff:
                    continue
            except Exception:
                pass  # 날짜 파싱 실패 시 포함
            articles.append(item)
    return articles
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_crawler.py -v
```

Expected: 3개 테스트 모두 PASSED

- [ ] **Step 5: 커밋**

```bash
git add crawler.py tests/test_crawler.py
git commit -m "feat: 네이버 뉴스 크롤러 추가"
```

---

## Task 5: 기사 요약기 (summarizer.py)

**Files:**
- Create: `summarizer.py`
- Test: `tests/test_summarizer.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_summarizer.py`:

```python
from unittest.mock import patch, MagicMock
import pytest


SAMPLE_ARTICLE = {
    "keyword": "기계설비건설공제조합",
    "title": "기계설비건설공제조합, 신규 사업 발표",
    "link": "http://news.example.com/1",
    "description": "기계설비건설공제조합이 올해 신규 사업 계획을 발표했다.",
    "pubDate": "Fri, 11 Apr 2026 10:00:00 +0900",
}


def _make_mock_client(response_text: str):
    mock_content = MagicMock()
    mock_content.text = response_text
    mock_message = MagicMock()
    mock_message.content = [mock_content]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    return mock_client


def test_summarize_article_returns_summary_and_importance():
    mock_client = _make_mock_client("요약: 기계설비건설공제조합이 신규 사업을 발표했다.\n중요도: 긍정")

    with patch("summarizer.anthropic.Anthropic", return_value=mock_client), \
         patch("summarizer.ANTHROPIC_API_KEY", "test_key"):
        import summarizer
        import importlib
        importlib.reload(summarizer)
        result = summarizer.summarize_article(SAMPLE_ARTICLE)

    assert result["summary"] == "기계설비건설공제조합이 신규 사업을 발표했다."
    assert result["importance"] == "긍정"
    assert result["title"] == SAMPLE_ARTICLE["title"]
    assert result["link"] == SAMPLE_ARTICLE["link"]


def test_summarize_article_defaults_to_neutral_on_unknown_importance():
    mock_client = _make_mock_client("요약: 조합 관련 소식이 보도됐다.\n중요도: 알수없음")

    with patch("summarizer.anthropic.Anthropic", return_value=mock_client), \
         patch("summarizer.ANTHROPIC_API_KEY", "test_key"):
        import summarizer
        import importlib
        importlib.reload(summarizer)
        result = summarizer.summarize_article(SAMPLE_ARTICLE)

    assert result["importance"] == "중립"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_summarizer.py -v
```

Expected: `ERROR` (summarizer 모듈 없음)

- [ ] **Step 3: summarizer.py 구현**

```python
import anthropic

from config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

VALID_IMPORTANCE = {"긍정", "부정", "중립"}


def summarize_article(article: dict) -> dict:
    prompt = f"""다음 뉴스 기사를 분석해주세요.

제목: {article['title']}
내용: {article['description']}

아래 형식으로만 응답하세요. 다른 내용은 쓰지 마세요.
요약: (2~3줄로 핵심 내용 요약)
중요도: (긍정/부정/중립 중 하나만)"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    summary = ""
    importance = "중립"

    for line in text.split("\n"):
        if line.startswith("요약:"):
            summary = line.replace("요약:", "").strip()
        elif line.startswith("중요도:"):
            raw = line.replace("중요도:", "").strip()
            if raw in VALID_IMPORTANCE:
                importance = raw

    return {**article, "summary": summary, "importance": importance}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_summarizer.py -v
```

Expected: 2개 테스트 모두 PASSED

- [ ] **Step 5: 커밋**

```bash
git add summarizer.py tests/test_summarizer.py
git commit -m "feat: Claude API 기사 요약기 추가"
```

---

## Task 6: 이메일 발송 (mailer.py)

**Files:**
- Create: `mailer.py`
- Test: `tests/test_mailer.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_mailer.py`:

```python
from unittest.mock import patch, MagicMock
import pytest


SAMPLE_ARTICLES = [
    {
        "keyword": "기계설비건설공제조합",
        "title": "기계설비건설공제조합 신규 발표",
        "link": "http://news.example.com/1",
        "description": "...",
        "pubDate": "Fri, 11 Apr 2026 10:00:00 +0900",
        "summary": "신규 사업 계획을 발표했다.",
        "importance": "긍정",
    },
    {
        "keyword": "건설공제조합",
        "title": "건설공제조합 사고 급증",
        "link": "http://news.example.com/2",
        "description": "...",
        "pubDate": "Fri, 11 Apr 2026 11:00:00 +0900",
        "summary": "보증 사고 건수가 증가했다.",
        "importance": "부정",
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
    assert "http://news.example.com/1" in body
    assert "신규 사업 계획을 발표했다." in body
    assert "🟢 긍정" in body
    assert "🔴 부정" in body


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


def test_send_email_calls_smtp(mocker=None):
    mock_smtp = MagicMock()
    mock_smtp_instance = MagicMock()
    mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_smtp_instance)
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
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_mailer.py -v
```

Expected: `ERROR` (mailer 모듈 없음)

- [ ] **Step 3: mailer.py 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_mailer.py -v
```

Expected: 4개 테스트 모두 PASSED

- [ ] **Step 5: 커밋**

```bash
git add mailer.py tests/test_mailer.py
git commit -m "feat: Gmail SMTP 이메일 발송 추가"
```

---

## Task 7: 메인 오케스트레이터 (main.py)

**Files:**
- Create: `main.py`

- [ ] **Step 1: main.py 작성**

```python
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
```

- [ ] **Step 2: 전체 테스트 통과 확인**

```bash
pytest -v
```

Expected: 모든 테스트 PASSED

- [ ] **Step 3: 수동 실행 테스트**

실제 API 키가 `config.env`에 입력된 상태에서 실행:

```bash
python main.py
```

Expected: 콘솔에 `새 기사 N건 발견. 요약 중...` 또는 `새 기사 없음. 이메일 미발송.` 출력

- [ ] **Step 4: 커밋**

```bash
git add main.py
git commit -m "feat: 메인 오케스트레이터 추가"
```

---

## Task 8: cron 자동 실행 설정

**Files:**
- 시스템 crontab 수정 (파일 생성 없음)

- [ ] **Step 1: Python 실행 경로 확인**

```bash
which python3
```

Expected: `/usr/bin/python3` 또는 `/usr/local/bin/python3` 등 경로 메모

- [ ] **Step 2: 프로젝트 절대 경로 확인**

```bash
pwd
```

Expected: `/Users/2wodms/workspace/claude-introduction` 메모

- [ ] **Step 3: crontab 등록**

```bash
crontab -e
```

아래 내용 추가 (경로는 Step 1~2에서 확인한 값으로 대체):

```
0 */2 * * * cd /Users/2wodms/workspace/claude-introduction && /usr/bin/python3 main.py >> /Users/2wodms/workspace/claude-introduction/monitor.log 2>&1
```

- `0 */2 * * *` → 매 2시간 정각 실행
- `>> monitor.log 2>&1` → 실행 로그를 파일에 저장

- [ ] **Step 4: crontab 등록 확인**

```bash
crontab -l
```

Expected: 등록한 라인이 출력됨

- [ ] **Step 5: 최종 커밋**

```bash
git add .
git commit -m "docs: cron 설정 완료, 시스템 운영 준비"
```

---

## 준비 사항 체크리스트

구현 시작 전 아래 항목을 미리 준비해야 한다:

| 항목 | 발급 방법 |
|------|-----------|
| 네이버 API 키 | https://developers.naver.com → 애플리케이션 등록 → 검색 API 선택 |
| Anthropic API 키 | https://console.anthropic.com → API Keys |
| Gmail 앱 비밀번호 | Google 계정 → 보안 → 2단계 인증 활성화 → 앱 비밀번호 생성 |
