# AI 요약 + 건설산업 뉴스 확장 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 건설산업 관련 키워드 9개를 추가하고, Claude API로 각 기사를 요약하여 articles.json, 이메일, 웹사이트에 표시한다.

**Architecture:** `config.py`에 `INDUSTRY_KEYWORDS`를 추가하고, `crawler.py`가 공제조합+산업 키워드 모두 수집한다. `summarizer.py`가 Claude Haiku API로 기사별 요약을 생성하고, `main.py`가 수집→요약→저장→이메일 순으로 실행한다. `index.html`은 건설산업 필터 버튼과 요약 표시를 추가한다.

**Tech Stack:** Python 3.x, anthropic SDK (claude-haiku-4-5-20251001), feedparser, pytest, GitHub Actions, GitHub Pages

---

## 파일 구조

| 파일 | 변경 | 역할 |
|------|------|------|
| `config.py` | 수정 | `INDUSTRY_KEYWORDS` 9개 추가 |
| `crawler.py` | 수정 | `KEYWORDS + INDUSTRY_KEYWORDS` 모두 수집 |
| `summarizer.py` | 신규 | Claude Haiku API로 기사별 2~3줄 요약 생성 |
| `tests/test_summarizer.py` | 신규 | summarizer 단위 테스트 |
| `main.py` | 수정 | `summarize_articles` 호출 추가 |
| `mailer.py` | 수정 | `summary` 필드 우선 표시, fallback은 `description` |
| `tests/test_mailer.py` | 수정 | summary 관련 테스트 추가 |
| `index.html` | 수정 | 건설산업 필터 버튼, AI 요약 표시 |
| `requirements.txt` | 수정 | `anthropic` 추가 |
| `config.env` | 수정 | `ANTHROPIC_API_KEY` 추가 |
| `.github/workflows/monitor.yml` | 수정 | `ANTHROPIC_API_KEY` Secret 주입 추가 |

---

## Task 1: config.py + crawler.py — 건설산업 키워드 추가

**Files:**
- Modify: `config.py`
- Modify: `crawler.py`

- [ ] **Step 1: config.py에 INDUSTRY_KEYWORDS 추가**

`config.py` 전체를 아래로 교체:

```python
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
```

- [ ] **Step 2: crawler.py에서 INDUSTRY_KEYWORDS 사용**

`crawler.py` 전체를 아래로 교체:

```python
import calendar
from datetime import datetime, timedelta

import feedparser

from config import INDUSTRY_KEYWORDS, KEYWORDS

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={}&hl=ko&gl=KR&ceid=KR:ko"


def fetch_news_rss(keyword: str) -> list:
    feed = feedparser.parse(GOOGLE_NEWS_RSS.format(keyword))
    articles = []
    for entry in feed.entries:
        articles.append({
            "keyword": keyword,
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "description": entry.get("summary", ""),
            "published_parsed": entry.get("published_parsed"),
        })
    return articles


def fetch_new_articles(seen: set) -> list:
    cutoff = datetime.now() - timedelta(hours=24)
    articles = []
    collected_links = set(seen)
    for keyword in KEYWORDS + INDUSTRY_KEYWORDS:
        for item in fetch_news_rss(keyword):
            if item["link"] in collected_links:
                continue
            pub_struct = item.pop("published_parsed")
            if pub_struct:
                try:
                    pub_dt = datetime.fromtimestamp(calendar.timegm(pub_struct))
                    if pub_dt < cutoff:
                        continue
                except (ValueError, TypeError, OverflowError):
                    pass
            articles.append(item)
            collected_links.add(item["link"])
    return articles
```

- [ ] **Step 3: 기존 테스트 통과 확인**

```bash
cd /Users/2wodms/workspace/claude-introduction
python3 -m pytest tests/test_crawler.py -v
```

Expected: 4개 테스트 모두 PASSED

- [ ] **Step 4: 커밋**

```bash
git add config.py crawler.py
git commit -m "feat: 건설산업 키워드 9개 추가 및 크롤러 연동"
```

---

## Task 2: summarizer.py — Claude API 요약 모듈

**Files:**
- Create: `summarizer.py`
- Create: `tests/test_summarizer.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_summarizer.py`:

```python
from unittest.mock import MagicMock, patch


def test_summarize_article_returns_text():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="  건설공제조합이 MOU를 체결했다. 법률 지원이 강화될 전망이다.  ")]
    )
    with patch("summarizer._get_client", return_value=mock_client):
        import summarizer
        import importlib
        importlib.reload(summarizer)
        result = summarizer.summarize_article("테스트 제목", "테스트 내용")

    assert result == "건설공제조합이 MOU를 체결했다. 법률 지원이 강화될 전망이다."


def test_summarize_article_returns_none_on_api_error():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API Error")
    with patch("summarizer._get_client", return_value=mock_client):
        import summarizer
        import importlib
        importlib.reload(summarizer)
        result = summarizer.summarize_article("제목", "내용")

    assert result is None


def test_summarize_articles_adds_summary_field():
    with patch("summarizer.summarize_article", return_value="테스트 요약"):
        import summarizer
        import importlib
        importlib.reload(summarizer)
        articles = [
            {"keyword": "건설공제조합", "title": "제목", "description": "내용", "link": "http://l/1"},
        ]
        result = summarizer.summarize_articles(articles)

    assert result[0]["summary"] == "테스트 요약"
    assert result[0]["keyword"] == "건설공제조합"
    assert result[0]["link"] == "http://l/1"


def test_summarize_articles_handles_none_summary():
    with patch("summarizer.summarize_article", return_value=None):
        import summarizer
        import importlib
        importlib.reload(summarizer)
        articles = [
            {"keyword": "건설경기", "title": "제목", "description": "내용", "link": "http://l/2"},
        ]
        result = summarizer.summarize_articles(articles)

    assert result[0]["summary"] is None


def test_summarize_articles_preserves_all_fields():
    with patch("summarizer.summarize_article", return_value="요약"):
        import summarizer
        import importlib
        importlib.reload(summarizer)
        articles = [
            {
                "keyword": "건설공제조합",
                "title": "제목",
                "description": "내용",
                "link": "http://l/3",
                "extra_field": "extra",
            },
        ]
        result = summarizer.summarize_articles(articles)

    assert result[0]["extra_field"] == "extra"
    assert result[0]["summary"] == "요약"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python3 -m pytest tests/test_summarizer.py -v
```

Expected: `ERROR` (summarizer 모듈 없음)

- [ ] **Step 3: summarizer.py 구현**

```python
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def summarize_article(title: str, description: str) -> str | None:
    prompt = (
        f"다음 뉴스 기사를 한국어로 2~3줄로 요약해주세요. 핵심 내용만 간결하게 작성하세요.\n\n"
        f"제목: {title}\n"
        f"내용: {description}\n\n"
        f"요약:"
    )
    try:
        message = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        logger.error("요약 실패 (title=%s): %s", title[:30], e)
        return None


def summarize_articles(articles: list) -> list:
    result = []
    for article in articles:
        summary = summarize_article(article["title"], article.get("description", ""))
        result.append({**article, "summary": summary})
    return result
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python3 -m pytest tests/test_summarizer.py -v
```

Expected: 5개 테스트 모두 PASSED

- [ ] **Step 5: 커밋**

```bash
git add summarizer.py tests/test_summarizer.py
git commit -m "feat: Claude Haiku API 기사별 요약 모듈 추가"
```

---

## Task 3: main.py — 요약 단계 추가

**Files:**
- Modify: `main.py`

- [ ] **Step 1: main.py 수정**

`main.py` 전체를 아래로 교체:

```python
import logging

from article_store import add_articles
from crawler import fetch_new_articles
from mailer import send_email
from seen_store import load_seen, save_seen
from summarizer import summarize_articles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    seen = load_seen()
    new_articles = fetch_new_articles(seen)

    if not new_articles:
        logger.info("새 기사 없음. 이메일 미발송.")
        return

    logger.info("새 기사 %d건 발견. 요약 중...", len(new_articles))
    summarized = summarize_articles(new_articles)

    new_urls = {a["link"] for a in summarized}
    send_email(summarized)
    save_seen(seen | new_urls)
    add_articles(summarized)
    logger.info("%d건 이슈 이메일 발송 완료.", len(summarized))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 전체 테스트 통과 확인**

```bash
python3 -m pytest -v
```

Expected: 기존 테스트 포함 모두 PASSED

- [ ] **Step 3: 커밋**

```bash
git add main.py
git commit -m "feat: main.py에 AI 요약 단계 추가"
```

---

## Task 4: mailer.py — 이메일에 AI 요약 표시

**Files:**
- Modify: `mailer.py`
- Modify: `tests/test_mailer.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_mailer.py`의 기존 내용 끝에 아래 테스트를 추가:

```python
def test_build_email_body_uses_summary_when_available():
    articles_with_summary = [
        {
            "keyword": "건설공제조합",
            "title": "건설공제조합 소식",
            "link": "http://news.google.com/articles/3",
            "description": "원문 내용입니다.",
            "summary": "AI가 요약한 내용입니다.",
        }
    ]
    with patch("mailer.GMAIL_ADDRESS", "test@gmail.com"), \
         patch("mailer.GMAIL_APP_PASSWORD", "pw"), \
         patch("mailer.RECIPIENTS", ["exec@company.com"]):
        import mailer
        import importlib
        importlib.reload(mailer)
        body = mailer.build_email_body(articles_with_summary)

    assert "AI가 요약한 내용입니다." in body
    assert "원문 내용입니다." not in body


def test_build_email_body_falls_back_to_description_when_no_summary():
    articles_no_summary = [
        {
            "keyword": "건설경기",
            "title": "건설경기 동향",
            "link": "http://news.google.com/articles/4",
            "description": "원문 내용 fallback입니다.",
            "summary": None,
        }
    ]
    with patch("mailer.GMAIL_ADDRESS", "test@gmail.com"), \
         patch("mailer.GMAIL_APP_PASSWORD", "pw"), \
         patch("mailer.RECIPIENTS", ["exec@company.com"]):
        import mailer
        import importlib
        importlib.reload(mailer)
        body = mailer.build_email_body(articles_no_summary)

    assert "원문 내용 fallback입니다." in body
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python3 -m pytest tests/test_mailer.py::test_build_email_body_uses_summary_when_available -v
```

Expected: FAIL (`원문 내용입니다.` 가 포함되어 summary 대신 description이 표시됨)

- [ ] **Step 3: mailer.py의 build_email_body 수정**

`mailer.py`에서 `build_email_body` 함수만 아래로 교체:

```python
def build_email_body(articles: list) -> str:
    lines = []
    for a in articles:
        body_text = a.get("summary") or a.get("description", "")
        if not a.get("summary") and len(body_text) > 200:
            body_text = body_text[:200] + "..."
        lines += [
            "━" * 40,
            f"[{a['keyword']}]",
            "━" * 40,
            f"제목: {a['title']}",
            f"링크: {a['link']}",
            f"요약: {body_text}",
            "",
        ]
    return "\n".join(lines)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python3 -m pytest tests/test_mailer.py -v
```

Expected: 7개 테스트 모두 PASSED (기존 5개 + 신규 2개)

- [ ] **Step 5: 커밋**

```bash
git add mailer.py tests/test_mailer.py
git commit -m "feat: 이메일 본문에 AI 요약 표시, summary 없으면 description fallback"
```

---

## Task 5: index.html — 건설산업 필터 + AI 요약 표시

**Files:**
- Modify: `index.html`

- [ ] **Step 1: index.html 전체 교체**

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>공제조합 이슈 모니터</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f5; color: #333; }
    header { background: #1a1a2e; color: white; padding: 24px 32px; }
    header h1 { font-size: 1.5rem; font-weight: 700; }
    header p { font-size: 0.85rem; opacity: 0.7; margin-top: 4px; }
    .filters { padding: 16px 32px; background: white; border-bottom: 1px solid #e0e0e0; display: flex; gap: 8px; flex-wrap: wrap; }
    .filter-btn { padding: 6px 14px; border: 1px solid #ccc; border-radius: 20px; background: white; cursor: pointer; font-size: 0.85rem; }
    .filter-btn.active { background: #1a1a2e; color: white; border-color: #1a1a2e; }
    .filter-btn.industry { border-color: #2e7d32; color: #2e7d32; }
    .filter-btn.industry.active { background: #2e7d32; color: white; border-color: #2e7d32; }
    .container { max-width: 860px; margin: 24px auto; padding: 0 16px; }
    .article { background: white; border-radius: 8px; padding: 16px 20px; margin-bottom: 12px; border-left: 4px solid #1a1a2e; }
    .article.industry { border-left-color: #2e7d32; }
    .article-meta { font-size: 0.78rem; color: #888; margin-bottom: 6px; }
    .keyword-badge { background: #e8eaf6; color: #3949ab; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; margin-right: 8px; }
    .keyword-badge.industry { background: #e8f5e9; color: #2e7d32; }
    .article-title { font-size: 1rem; font-weight: 600; margin-bottom: 6px; }
    .article-title a { color: #1a1a2e; text-decoration: none; }
    .article-title a:hover { text-decoration: underline; }
    .article-summary { font-size: 0.875rem; color: #555; line-height: 1.5; }
    .summary-label { font-size: 0.75rem; color: #888; font-weight: 600; margin-bottom: 2px; }
    .empty { text-align: center; padding: 60px; color: #999; }
    .count { font-size: 0.85rem; color: #666; margin-bottom: 16px; }
  </style>
</head>
<body>
  <header>
    <h1>🔔 공제조합 이슈 모니터</h1>
    <p id="last-updated">로딩 중...</p>
  </header>
  <div class="filters" id="filters">
    <button class="filter-btn active" data-filter="전체" onclick="setFilter('전체')">전체</button>
    <button class="filter-btn" data-filter="기계설비건설공제조합" onclick="setFilter('기계설비건설공제조합')">기계설비</button>
    <button class="filter-btn" data-filter="엔지니어링공제조합" onclick="setFilter('엔지니어링공제조합')">엔지니어링</button>
    <button class="filter-btn" data-filter="건설공제조합" onclick="setFilter('건설공제조합')">건설</button>
    <button class="filter-btn" data-filter="전문건설공제조합" onclick="setFilter('전문건설공제조합')">전문건설</button>
    <button class="filter-btn industry" data-filter="건설산업" onclick="setFilter('건설산업')">건설산업</button>
  </div>
  <div class="container">
    <div id="article-count" class="count"></div>
    <div id="articles"></div>
  </div>
  <script>
    const INDUSTRY_KEYWORDS = [
      "건설산업기본법", "국토교통부 건설", "건설업 규제",
      "건설경기", "건설 PF", "건설수주",
      "중대재해 건설", "건설현장 안전", "건설 노동"
    ];

    let allArticles = [];
    let currentFilter = '전체';

    function escapeHtml(str) {
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    function safeHref(url) {
      try {
        const u = new URL(url);
        return (u.protocol === 'http:' || u.protocol === 'https:') ? url : '#';
      } catch { return '#'; }
    }

    function formatDate(iso) {
      if (!iso) return '';
      const d = new Date(iso);
      if (isNaN(d.getTime())) return '';
      return d.toLocaleDateString('ko-KR') + ' ' + d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    }

    function isIndustry(keyword) {
      return INDUSTRY_KEYWORDS.includes(keyword);
    }

    function setFilter(keyword) {
      currentFilter = keyword;
      document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === keyword);
      });
      render();
    }

    function render() {
      const filtered = currentFilter === '전체'
        ? allArticles
        : currentFilter === '건설산업'
        ? allArticles.filter(a => INDUSTRY_KEYWORDS.includes(a.keyword))
        : allArticles.filter(a => a.keyword === currentFilter);

      const container = document.getElementById('articles');
      const countEl = document.getElementById('article-count');

      countEl.textContent = `총 ${filtered.length}건`;

      if (filtered.length === 0) {
        container.innerHTML = '<div class="empty">수집된 기사가 없습니다.</div>';
        return;
      }

      container.innerHTML = filtered.map(a => {
        const industry = isIndustry(a.keyword);
        const badgeClass = industry ? 'keyword-badge industry' : 'keyword-badge';
        const cardClass = industry ? 'article industry' : 'article';
        const displayText = escapeHtml(a.summary || a.description || '');
        const summaryLabel = a.summary ? 'AI 요약' : '내용';
        return `
          <div class="${cardClass}">
            <div class="article-meta">
              <span class="${badgeClass}">${escapeHtml(a.keyword)}</span>
              ${escapeHtml(formatDate(a.collected_at))}
            </div>
            <div class="article-title">
              <a href="${safeHref(a.link)}" target="_blank" rel="noopener">${escapeHtml(a.title)}</a>
            </div>
            <div class="summary-label">${summaryLabel}</div>
            <div class="article-summary">${displayText}</div>
          </div>
        `;
      }).join('');
    }

    fetch('articles.json?t=' + Date.now())
      .then(r => r.json())
      .then(data => {
        allArticles = data;
        const lastUpdated = data.length > 0 ? data[0].collected_at : null;
        document.getElementById('last-updated').textContent =
          lastUpdated ? '마지막 업데이트: ' + formatDate(lastUpdated) : '아직 수집된 기사 없음';
        render();
      })
      .catch(() => {
        document.getElementById('articles').innerHTML = '<div class="empty">articles.json을 불러올 수 없습니다.</div>';
        document.getElementById('last-updated').textContent = '로딩 실패';
      });
  </script>
</body>
</html>
```

- [ ] **Step 2: 로컬에서 동작 확인**

```bash
python3 -m http.server 8080
```

브라우저에서 `http://localhost:8080` 접속 후 확인:
- "건설산업" 필터 버튼이 초록색으로 표시되는지
- 기사 카드에 "AI 요약" 또는 "내용" 레이블이 표시되는지
- 건설산업 필터 클릭 시 해당 기사만 표시되는지

- [ ] **Step 3: 커밋**

```bash
git add index.html
git commit -m "feat: 웹사이트에 건설산업 필터 버튼 및 AI 요약 표시 추가"
```

---

## Task 6: requirements.txt + config.env + GitHub Actions

**Files:**
- Modify: `requirements.txt`
- Modify: `config.env`
- Modify: `.github/workflows/monitor.yml`

- [ ] **Step 1: requirements.txt에 anthropic 추가**

`requirements.txt` 전체를 아래로 교체:

```
requests==2.32.3
feedparser==6.0.11
python-dotenv==1.0.1
pytest==8.3.4
anthropic>=0.40.0
```

- [ ] **Step 2: 의존성 설치 확인**

```bash
pip install -r requirements.txt
```

Expected: `anthropic` 패키지 설치 완료

- [ ] **Step 3: config.env에 ANTHROPIC_API_KEY 추가**

`config.env` 파일을 열어 아래 줄을 추가 (실제 API 키로 교체):

```
ANTHROPIC_API_KEY=sk-ant-여기에실제키입력
```

- [ ] **Step 4: monitor.yml에 ANTHROPIC_API_KEY Secret 추가**

`.github/workflows/monitor.yml`의 `뉴스 모니터 실행` step을 아래로 교체:

```yaml
      - name: 뉴스 모니터 실행
        env:
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          RECIPIENTS: ${{ secrets.RECIPIENTS }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python main.py
```

- [ ] **Step 5: 전체 테스트 통과 확인**

```bash
python3 -m pytest -v
```

Expected: 전체 테스트 모두 PASSED

- [ ] **Step 6: GitHub Secrets에 ANTHROPIC_API_KEY 등록**

GitHub 저장소 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Name | Value |
|------|-------|
| `ANTHROPIC_API_KEY` | `sk-ant-실제키값` |

- [ ] **Step 7: 커밋 및 푸시**

```bash
git add requirements.txt .github/workflows/monitor.yml
git commit -m "feat: anthropic 의존성 및 GitHub Actions Secret 추가"
git push
```

- [ ] **Step 8: GitHub Actions 수동 실행으로 동작 확인**

GitHub 저장소 → **Actions** → **공제조합 이슈 모니터** → **Run workflow**

실행 완료 후 확인:
1. Actions 로그에서 "요약 중..." 로그 확인
2. 저장소의 `articles.json`에 `summary` 필드가 포함된 기사 확인
3. GitHub Pages 웹사이트에서 AI 요약 표시 및 건설산업 필터 버튼 확인
