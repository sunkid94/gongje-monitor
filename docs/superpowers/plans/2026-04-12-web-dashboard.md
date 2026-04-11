# 공제조합 이슈 로그 웹사이트 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 수집된 뉴스 기사를 articles.json에 누적 저장하고, GitHub Actions로 1시간마다 자동 실행하며, GitHub Pages로 이슈 로그 웹사이트를 공개 배포한다.

**Architecture:** `article_store.py`가 articles.json 읽기/쓰기를 담당하고, `main.py`가 수집 후 article_store에 기사를 추가한다. `index.html`이 articles.json을 fetch해 브라우저에서 렌더링한다. `.github/workflows/monitor.yml`이 GitHub Actions에서 1시간마다 main.py를 실행하고 변경된 파일을 자동 커밋한다.

**Tech Stack:** Python 3.x, feedparser, python-dotenv, pytest, GitHub Actions, GitHub Pages (순수 HTML/CSS/JS)

---

## 파일 구조

| 파일 | 변경 | 역할 |
|------|------|------|
| `article_store.py` | 신규 | articles.json 로드/저장/추가 (최대 500건) |
| `tests/test_article_store.py` | 신규 | article_store 단위 테스트 |
| `main.py` | 수정 | article_store.add_articles() 호출 추가 |
| `index.html` | 신규 | 이슈 로그 웹페이지 (조합별 필터, 날짜 역순) |
| `.github/workflows/monitor.yml` | 신규 | GitHub Actions 1시간 스케줄 |
| `.gitignore` | 수정 | seen.json 제외 항목 삭제 (Actions에서 커밋해야 함) |

---

## Task 1: article_store.py

**Files:**
- Create: `article_store.py`
- Test: `tests/test_article_store.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_article_store.py`:

```python
import json
from unittest.mock import patch


SAMPLE_ARTICLES = [
    {
        "keyword": "기계설비건설공제조합",
        "title": "기계설비건설공제조합 신규 발표",
        "link": "http://news.google.com/1",
        "description": "신규 사업 발표",
    },
    {
        "keyword": "건설공제조합",
        "title": "건설공제조합 소식",
        "link": "http://news.google.com/2",
        "description": "건설 소식",
    },
]


def test_load_articles_returns_empty_list_when_file_missing(tmp_path):
    articles_file = str(tmp_path / "articles.json")
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        import importlib
        importlib.reload(article_store)
        result = article_store.load_articles()
    assert result == []


def test_save_and_load_articles_roundtrip(tmp_path):
    articles_file = str(tmp_path / "articles.json")
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        import importlib
        importlib.reload(article_store)
        article_store.save_articles(SAMPLE_ARTICLES)
        result = article_store.load_articles()
    assert len(result) == 2
    assert result[0]["link"] == "http://news.google.com/1"


def test_save_articles_truncates_to_max(tmp_path):
    articles_file = str(tmp_path / "articles.json")
    many = [{"keyword": "k", "title": f"t{i}", "link": f"http://l/{i}", "description": ""} for i in range(600)]
    with patch("article_store.ARTICLES_FILE", articles_file), \
         patch("article_store.MAX_ARTICLES", 10):
        import article_store
        import importlib
        importlib.reload(article_store)
        article_store.save_articles(many)
        result = article_store.load_articles()
    assert len(result) == 10


def test_add_articles_prepends_with_collected_at(tmp_path):
    articles_file = str(tmp_path / "articles.json")
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        import importlib
        importlib.reload(article_store)
        article_store.add_articles(SAMPLE_ARTICLES)
        result = article_store.load_articles()
    assert len(result) == 2
    assert "collected_at" in result[0]
    assert result[0]["link"] == "http://news.google.com/1"


def test_add_articles_prepends_to_existing(tmp_path):
    articles_file = str(tmp_path / "articles.json")
    existing = [{"keyword": "k", "title": "old", "link": "http://old/1", "description": "", "collected_at": "2026-01-01T00:00:00"}]
    with patch("article_store.ARTICLES_FILE", articles_file):
        import article_store
        import importlib
        importlib.reload(article_store)
        article_store.save_articles(existing)
        article_store.add_articles([SAMPLE_ARTICLES[0]])
        result = article_store.load_articles()
    assert result[0]["link"] == "http://news.google.com/1"
    assert result[1]["link"] == "http://old/1"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python3 -m pytest tests/test_article_store.py -v
```

Expected: `ERROR` (article_store 모듈 없음)

- [ ] **Step 3: article_store.py 구현**

```python
import json
import os
from datetime import datetime

ARTICLES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "articles.json")
MAX_ARTICLES = 500


def load_articles() -> list:
    try:
        with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_articles(articles: list) -> None:
    with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
        json.dump(articles[:MAX_ARTICLES], f, ensure_ascii=False, indent=2)


def add_articles(new_articles: list) -> None:
    existing = load_articles()
    timestamped = [
        {**a, "collected_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
        for a in new_articles
    ]
    save_articles(timestamped + existing)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python3 -m pytest tests/test_article_store.py -v
```

Expected: 5개 테스트 모두 PASSED

- [ ] **Step 5: 커밋**

```bash
git add article_store.py tests/test_article_store.py
git commit -m "feat: article_store 추가 (articles.json 관리)"
```

---

## Task 2: main.py 수정 + .gitignore 수정

**Files:**
- Modify: `main.py`
- Modify: `.gitignore`

- [ ] **Step 1: .gitignore에서 seen.json 제거**

`.gitignore` 파일에서 `seen.json` 줄을 삭제한다. GitHub Actions가 seen.json을 커밋해야 중복 수집이 방지된다.

`.gitignore` 최종 내용:
```
config.env
__pycache__/
*.pyc
.pytest_cache/
.obsidian/
```

- [ ] **Step 2: main.py에 add_articles 호출 추가**

`main.py`를 아래 내용으로 교체한다:

```python
import logging

from article_store import add_articles
from crawler import fetch_new_articles
from mailer import send_email
from seen_store import load_seen, save_seen

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

    logger.info("새 기사 %d건 발견. 저장 및 이메일 발송 중...", len(new_articles))

    new_urls = {a["link"] for a in new_articles}
    save_seen(seen | new_urls)
    add_articles(new_articles)

    send_email(new_articles)
    logger.info("%d건 이슈 이메일 발송 완료.", len(new_articles))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 전체 테스트 통과 확인**

```bash
python3 -m pytest -v
```

Expected: 17개 테스트 모두 PASSED

- [ ] **Step 4: 커밋**

```bash
git add main.py .gitignore
git commit -m "feat: main.py에 article_store 연동, seen.json 커밋 허용"
```

---

## Task 3: index.html (이슈 로그 웹페이지)

**Files:**
- Create: `index.html`

이 파일은 순수 HTML/CSS/JS로 구성된다. 서버 없이 GitHub Pages에서 직접 서빙된다. `articles.json`을 fetch해 목록을 렌더링한다.

- [ ] **Step 1: index.html 생성**

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
    .container { max-width: 860px; margin: 24px auto; padding: 0 16px; }
    .article { background: white; border-radius: 8px; padding: 16px 20px; margin-bottom: 12px; border-left: 4px solid #1a1a2e; }
    .article-meta { font-size: 0.78rem; color: #888; margin-bottom: 6px; }
    .keyword-badge { background: #e8eaf6; color: #3949ab; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; margin-right: 8px; }
    .article-title { font-size: 1rem; font-weight: 600; margin-bottom: 6px; }
    .article-title a { color: #1a1a2e; text-decoration: none; }
    .article-title a:hover { text-decoration: underline; }
    .article-desc { font-size: 0.875rem; color: #555; line-height: 1.5; }
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
    <button class="filter-btn active" data-keyword="전체" onclick="setFilter('전체')">전체</button>
    <button class="filter-btn" data-keyword="기계설비건설공제조합" onclick="setFilter('기계설비건설공제조합')">기계설비</button>
    <button class="filter-btn" data-keyword="엔지니어링공제조합" onclick="setFilter('엔지니어링공제조합')">엔지니어링</button>
    <button class="filter-btn" data-keyword="건설공제조합" onclick="setFilter('건설공제조합')">건설</button>
    <button class="filter-btn" data-keyword="전문건설공제조합" onclick="setFilter('전문건설공제조합')">전문건설</button>
  </div>
  <div class="container">
    <div id="article-count" class="count"></div>
    <div id="articles"></div>
  </div>
  <script>
    let allArticles = [];
    let currentFilter = '전체';

    function formatDate(iso) {
      if (!iso) return '';
      const d = new Date(iso);
      return d.toLocaleDateString('ko-KR') + ' ' + d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    }

    function setFilter(keyword) {
      currentFilter = keyword;
      document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.keyword === keyword);
      });
      render();
    }

    function render() {
      const filtered = currentFilter === '전체'
        ? allArticles
        : allArticles.filter(a => a.keyword === currentFilter);

      const container = document.getElementById('articles');
      const countEl = document.getElementById('article-count');

      countEl.textContent = `총 ${filtered.length}건`;

      if (filtered.length === 0) {
        container.innerHTML = '<div class="empty">수집된 기사가 없습니다.</div>';
        return;
      }

      container.innerHTML = filtered.map(a => `
        <div class="article">
          <div class="article-meta">
            <span class="keyword-badge">${a.keyword}</span>
            ${formatDate(a.collected_at)}
          </div>
          <div class="article-title">
            <a href="${a.link}" target="_blank" rel="noopener">${a.title}</a>
          </div>
          <div class="article-desc">${a.description || ''}</div>
        </div>
      `).join('');
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

브라우저에서 `http://localhost:8080` 접속 → 이슈 로그 페이지 확인

(articles.json이 비어있으면 "수집된 기사가 없습니다." 메시지 표시됨 — 정상)

- [ ] **Step 3: 커밋**

```bash
git add index.html
git commit -m "feat: 이슈 로그 웹페이지 추가"
```

---

## Task 4: GitHub Actions 워크플로우

**Files:**
- Create: `.github/workflows/monitor.yml`

- [ ] **Step 1: 디렉토리 생성**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: monitor.yml 생성**

`.github/workflows/monitor.yml`:

```yaml
name: 공제조합 이슈 모니터

on:
  schedule:
    - cron: '0 * * * *'   # 매 1시간 정각 (UTC 기준)
  workflow_dispatch:        # 수동 실행 버튼

jobs:
  monitor:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - name: 저장소 체크아웃
        uses: actions/checkout@v4

      - name: Python 설치
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 의존성 설치
        run: pip install -r requirements.txt

      - name: 뉴스 모니터 실행
        env:
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          RECIPIENTS: ${{ secrets.RECIPIENTS }}
        run: python main.py

      - name: 변경 파일 커밋 및 푸시
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add articles.json seen.json
          git diff --staged --quiet || git commit -m "chore: 기사 업데이트 $(date +'%Y-%m-%d %H:%M UTC')"
          git push
```

- [ ] **Step 3: 커밋**

```bash
git add .github/workflows/monitor.yml
git commit -m "feat: GitHub Actions 1시간 스케줄 추가"
```

---

## Task 5: GitHub 저장소 설정 및 배포

이 태스크는 코드가 아닌 GitHub 설정 작업이다. 순서대로 진행한다.

- [ ] **Step 1: 맥북 cron 제거**

```bash
crontab -l   # 현재 등록된 cron 확인
crontab -r   # 전체 cron 삭제
```

- [ ] **Step 2: GitHub 저장소 생성**

1. [https://github.com/new](https://github.com/new) 접속
2. Repository name: `news-monitor` (원하는 이름)
3. **Public** 선택 (GitHub Pages 무료 사용에 필요)
4. **Create repository** 클릭

- [ ] **Step 3: 로컬 저장소를 GitHub에 푸시**

```bash
git remote add origin https://github.com/[계정명]/[저장소명].git
git branch -M main
git push -u origin main
```

- [ ] **Step 4: GitHub Secrets 등록**

GitHub 저장소 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

아래 3개를 각각 등록:

| Name | Value |
|------|-------|
| `GMAIL_ADDRESS` | `2wodms@gmail.com` |
| `GMAIL_APP_PASSWORD` | `gidzrodzsawilhdp` |
| `RECIPIENTS` | `2wodms@gmail.com` |

- [ ] **Step 5: GitHub Pages 활성화**

GitHub 저장소 → **Settings** → **Pages**
- Source: **Deploy from a branch**
- Branch: `main` / `/ (root)`
- **Save** 클릭

1~2분 후 `https://[계정명].github.io/[저장소명]` URL이 활성화됨

- [ ] **Step 6: GitHub Actions 수동 실행으로 동작 확인**

GitHub 저장소 → **Actions** → **공제조합 이슈 모니터** → **Run workflow**

실행 완료 후:
1. Actions 로그에서 "새 기사 N건 발견" 또는 "새 기사 없음" 확인
2. 저장소에 `articles.json`, `seen.json` 커밋 확인
3. `https://[계정명].github.io/[저장소명]` 접속하여 웹페이지 확인

---

## 준비 사항 체크리스트

구현 전 확인:
- [ ] GitHub 계정 보유 확인
- [ ] `config.env`의 실제 Gmail 정보 입력 완료 (Step 4에서 Secrets에 등록)
