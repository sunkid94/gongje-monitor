# 조합 기사 아카이브 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 조합 기사 전 기간을 제목+링크 리스트(archive.json + archive.html)로 영구 보존하고, 메인 대시보드에는 최근 30일 조합 기사만 남겨 articles.json 볼륨을 유계로 만든다.

**Architecture:** 신규 `archive_store.py`가 수집된 조합 기사를 `archive.json`(lean, 영구)에 link 중복 없이 적재한다. `article_store.save_articles`는 조합 기사를 무기한 대신 30일 보존한다(archive.json이 원장이라 유실 없음). `main.py`가 두 저장을 연결하고, 신규 `archive.html`이 archive.json을 월별 제목-링크로 렌더한다.

**Tech Stack:** Python 3.9+ (json, datetime), pytest(+tmp_path/monkeypatch), 바닐라 JS(archive.html). 신규 의존성 없음.

설계 스펙: `docs/superpowers/specs/2026-07-04-company-article-archive-design.md`

## Global Constraints

- 신규 의존성 금지.
- archive.json 항목은 **lean 스키마 고정**: `{"title", "link", "date", "keyword"}`. title=`title_clean`우선, date=`published_at`우선(없으면 `collected_at`).
- archive.json은 **link 기준 중복 제거, 보존기간 없음(영구)**. 안전 상한 `MAX_ARCHIVE=20000`.
- 조합 기사 대시보드 보존: `RETENTION_DAYS_COMPANY=30`.
- archive.json 파싱 실패 시 **기존 파일을 덮어쓰지 않고 중단**.
- 배포 시 **시딩(기존 785건 → archive.json)을 30일 보존 적용보다 먼저** 수행(유실 방지).

## File Structure

| 파일 | 책임 |
|------|------|
| `archive_store.py` (신규) | `append_articles()` — is_company lean 적재, link dedup, 파손 보호 |
| `archive.json` (신규 데이터) | 조합 기사 lean 영구 목록 (배포 시딩으로 최초 생성) |
| `article_store.py` (수정) | `RETENTION_DAYS_COMPANY=30`, 조합 기사 30일 보존 |
| `main.py` (수정) | `archive_store.append_articles(deduped)` 호출 |
| `archive.html` (신규) | archive.json 월별 제목-링크 리스트 페이지 |
| `index.html` (수정) | 헤더 nav에 아카이브 링크 |
| `tests/test_archive_store.py` (신규), `tests/test_article_store.py` (확장) | 단위 테스트 |

---

### Task 1: `archive_store.py` — 조합 기사 lean 적재

**Files:**
- Create: `archive_store.py`, `tests/test_archive_store.py`

**Interfaces:**
- Produces: `append_articles(articles: list) -> None` — Task 3(main)이 호출.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_archive_store.py`:

```python
import json

import archive_store


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_appends_only_company(tmp_path, monkeypatch):
    f = tmp_path / "archive.json"
    monkeypatch.setattr(archive_store, "ARCHIVE_FILE", str(f))
    archive_store.append_articles([
        {"is_company": True, "title": "조합기사", "link": "http://a/1",
         "published_at": "2026-07-03T10:00:00+09:00", "keyword": "기계설비건설공제조합"},
        {"is_company": False, "title": "산업기사", "link": "http://a/2"},
    ])
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert len(saved) == 1
    assert saved[0] == {"title": "조합기사", "link": "http://a/1",
                        "date": "2026-07-03T10:00:00+09:00", "keyword": "기계설비건설공제조합"}


def test_dedup_existing_links(tmp_path, monkeypatch):
    f = tmp_path / "archive.json"
    _write(f, [{"title": "old", "link": "http://a/1", "date": "x", "keyword": "k"}])
    monkeypatch.setattr(archive_store, "ARCHIVE_FILE", str(f))
    archive_store.append_articles([{"is_company": True, "title": "dup", "link": "http://a/1"}])
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert len(saved) == 1   # 이미 있는 link → 추가 안 함


def test_lean_uses_title_clean_and_collected_fallback(tmp_path, monkeypatch):
    f = tmp_path / "archive.json"
    monkeypatch.setattr(archive_store, "ARCHIVE_FILE", str(f))
    archive_store.append_articles([
        {"is_company": True, "title": "원제목 - 매체", "title_clean": "깨끗한제목",
         "link": "http://a/3", "collected_at": "2026-07-04T09:00:00+09:00"},
    ])
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert saved[0]["title"] == "깨끗한제목"                       # title_clean 우선
    assert saved[0]["date"] == "2026-07-04T09:00:00+09:00"        # published_at 없으면 collected_at


def test_corrupt_archive_not_overwritten(tmp_path, monkeypatch):
    f = tmp_path / "archive.json"
    f.write_text("{ broken json", encoding="utf-8")
    monkeypatch.setattr(archive_store, "ARCHIVE_FILE", str(f))
    archive_store.append_articles([{"is_company": True, "title": "x", "link": "http://a/9"}])
    assert f.read_text(encoding="utf-8") == "{ broken json"       # 파손 파일 덮어쓰지 않음
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_archive_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'archive_store'`

- [ ] **Step 3: `archive_store.py` 구현**

```python
import json
import logging
import os

logger = logging.getLogger(__name__)

ARCHIVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archive.json")
MAX_ARCHIVE = 20000


def _load() -> list:
    with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _lean(a: dict) -> dict:
    return {
        "title": a.get("title_clean") or a.get("title", ""),
        "link": a.get("link", ""),
        "date": a.get("published_at") or a.get("collected_at", ""),
        "keyword": a.get("keyword", ""),
    }


def append_articles(articles: list) -> None:
    """articles 중 is_company 인 것을 archive.json 에 lean 형태로 추가(link 중복 제거).

    archive.json 파손 시 덮어쓰지 않고 중단한다(원장 보호)."""
    try:
        existing = _load()
    except FileNotFoundError:
        existing = []
    except json.JSONDecodeError as e:
        logger.error("archive.json 파싱 실패 — 아카이브 적재 중단: %s", e)
        return

    seen_links = {a.get("link") for a in existing if a.get("link")}
    added = False
    for a in articles:
        if not a.get("is_company"):
            continue
        link = a.get("link", "")
        if not link or link in seen_links:
            continue
        existing.append(_lean(a))
        seen_links.add(link)
        added = True
    if not added:
        return
    if len(existing) > MAX_ARCHIVE:
        existing = existing[-MAX_ARCHIVE:]
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest tests/test_archive_store.py -q`
Expected: PASS — 4개 통과

- [ ] **Step 5: 커밋**

```bash
git add archive_store.py tests/test_archive_store.py
git commit -m "feat: archive_store — 조합 기사 lean 영구 적재(link dedup)"
```

---

### Task 2: `article_store` — 조합 기사 30일 보존

**Files:**
- Modify: `article_store.py` (상단 상수, `save_articles` company 블록 146~161행)
- Test: `tests/test_article_store.py` (확장)

**Interfaces:**
- Consumes/Produces: 기존 `save_articles(articles)` 동작 유지 + 조합 기사 30일 컷.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_article_store.py` 끝에 추가:

```python
def test_company_article_pruned_after_30_days(tmp_path, monkeypatch):
    import article_store
    from datetime import datetime, timedelta
    monkeypatch.setattr(article_store, "ARTICLES_FILE", str(tmp_path / "articles.json"))
    now = datetime.now().astimezone()
    old = article_store.format_collected_at(now - timedelta(days=40))
    recent = article_store.format_collected_at(now - timedelta(days=5))
    article_store.save_articles([
        {"is_company": True, "title": "오래된 조합기사입니다", "link": "c1",
         "collected_at": old, "publisher": "p", "cluster_id": "1"},
        {"is_company": True, "title": "최근 조합기사입니다", "link": "c2",
         "collected_at": recent, "publisher": "p", "cluster_id": "2"},
    ])
    links = {a["link"] for a in article_store.load_articles()}
    assert "c2" in links       # 30일 이내 유지
    assert "c1" not in links    # 30일 초과 제거
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_article_store.py::test_company_article_pruned_after_30_days -q`
Expected: FAIL — `c1`이 남아있어 assert 실패(현재 조합은 무기한 보존)

- [ ] **Step 3: `article_store.py` 수정**

상단 상수 영역(`RETENTION_DAYS = 60` 아래)에 추가:

```python
RETENTION_DAYS_COMPANY = 30   # 조합 기사도 대시보드엔 30일만 (전 기간은 archive.json)
```

`save_articles` 안의 `cutoff = ...` 다음 줄에 company 컷오프 추가:

```python
    cutoff = datetime.now().astimezone() - timedelta(days=RETENTION_DAYS)
    company_cutoff = datetime.now().astimezone() - timedelta(days=RETENTION_DAYS_COMPANY)
```

company 블록(현재):

```python
        if a.get("is_company"):
            company.append(a)
            continue
```

을 30일 컷 적용으로 교체:

```python
        if a.get("is_company"):
            try:
                if parse_collected_at(a.get("collected_at", "")) < company_cutoff:
                    continue
            except ValueError:
                pass  # 시각 파싱 실패 시 보존
            company.append(a)
            continue
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest tests/test_article_store.py -q`
Expected: PASS — 신규 + 기존 전부 통과

- [ ] **Step 5: 커밋**

```bash
git add article_store.py tests/test_article_store.py
git commit -m "feat: 조합 기사 30일 보존(무기한→30일, 전 기간은 아카이브)"
```

---

### Task 3: `main.py` — 아카이브 적재 연결

**Files:**
- Modify: `main.py` (import + `add_articles(deduped)` 직전, 현재 49행)

**Interfaces:**
- Consumes: `archive_store.append_articles` (Task 1), 기존 `add_articles`.

- [ ] **Step 1: import 추가** — main.py의 `from article_store import ...` 아래에:

```python
import archive_store
```

- [ ] **Step 2: 적재 호출 추가** — `add_articles(deduped)` (현재 49행) **직전**에:

```python
    archive_store.append_articles(deduped)
    add_articles(deduped)
```

(아카이브 적재를 보존 pruning 발생 전에 수행 — is_company 전량이 archive에 남도록.)

- [ ] **Step 3: 임포트 스모크**

Run: `python3 -c "import main, archive_store; print('import OK')"`
Expected: `import OK`

- [ ] **Step 4: 커밋**

```bash
git add main.py
git commit -m "feat: main에서 archive_store 적재 연결"
```

---

### Task 4: `archive.html` + 대시보드 링크

**Files:**
- Create: `archive.html`
- Modify: `index.html` (nav, 591~594행 `nav-actions`)

*(JS 하네스 없음 — 수동/시각 확인.)*

- [ ] **Step 1: `archive.html` 생성**

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>조합 기사 아카이브</title>
  <style>
    body { font-family: -apple-system, "Segoe UI", sans-serif; max-width: 860px; margin: 0 auto;
           padding: 24px; color: #1a2b45; background: #f7f9fc; }
    h1 { font-size: 22px; }
    .back { display: inline-block; margin-bottom: 16px; color: #2b6cb0; text-decoration: none; }
    .month { margin: 28px 0 8px; font-size: 16px; font-weight: 800; border-bottom: 2px solid #dfe6f0;
             padding-bottom: 6px; }
    ul { list-style: none; padding: 0; margin: 0; }
    li { padding: 7px 0; border-bottom: 1px dashed #e3e9f2; font-size: 14px; }
    li .date { color: #7a8aa0; margin-right: 8px; font-variant-numeric: tabular-nums; }
    li a { color: #1a2b45; text-decoration: none; }
    li a:hover { text-decoration: underline; }
    .empty { color: #7a8aa0; }
  </style>
</head>
<body>
  <a class="back" href="index.html">← 대시보드로</a>
  <h1>📁 조합 기사 아카이브</h1>
  <div id="list" class="empty">불러오는 중…</div>
  <script>
    function fmtDate(iso) {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return '';
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${m}-${day}`;
    }
    function monthKey(iso) {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return '날짜 미상';
      return `${d.getFullYear()}년 ${d.getMonth() + 1}월`;
    }
    function esc(s) {
      return String(s || '').replace(/[&<>"']/g, c =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }
    fetch('archive.json?cb=' + Date.now())
      .then(r => r.json())
      .then(items => {
        items.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
        const groups = {};
        for (const it of items) (groups[monthKey(it.date)] ||= []).push(it);
        const el = document.getElementById('list');
        el.className = '';
        el.innerHTML = Object.entries(groups).map(([month, arr]) => `
          <div class="month">${esc(month)} <span class="date">(${arr.length})</span></div>
          <ul>${arr.map(it => `
            <li><span class="date">${fmtDate(it.date)}</span><a href="${esc(it.link)}" target="_blank" rel="noopener">${esc(it.title)}</a></li>
          `).join('')}</ul>
        `).join('') || '<p class="empty">아카이브가 비어 있습니다.</p>';
      })
      .catch(() => { document.getElementById('list').innerHTML = '<p class="empty">불러오기 실패</p>'; });
  </script>
</body>
</html>
```

- [ ] **Step 2: `index.html` nav에 링크 추가** — `nav-actions` div(591~594행)의 `install-btn` 앞에:

```html
      <a class="archive-link" href="archive.html" style="align-self:center;margin-right:12px;color:var(--sub,#5a6b85);text-decoration:none;font-size:13px;font-weight:600;">📁 조합기사 전체</a>
```

- [ ] **Step 3: 로컬 브라우저 확인** — 임시 샘플로 렌더 검증:

```bash
cd /Users/2wodms/workspace/claude-introduction
printf '[{"title":"테스트 조합기사 A","link":"https://example.com/a","date":"2026-06-15T10:00:00+09:00","keyword":"기계설비건설공제조합"},{"title":"테스트 조합기사 B","link":"https://example.com/b","date":"2026-07-02T09:00:00+09:00","keyword":"건설공제조합"}]' > archive.json
python3 -m http.server 8766
```
브라우저 `http://localhost:8766/archive.html` → **월별 그룹(2026년 7월/6월), 발행일순, 제목 클릭 시 원문 이동** 확인. index.html 헤더의 `📁 조합기사 전체` 링크 클릭 시 archive.html 로 이동 확인. 확인 후 `Ctrl+C`, 그리고 **샘플 삭제**(실제 archive.json은 배포 시딩으로 생성):

```bash
rm archive.json
```

- [ ] **Step 4: 커밋** (archive.json은 커밋하지 않음 — 배포 시딩본이 원본)

```bash
git add archive.html index.html
git commit -m "feat: 조합 기사 아카이브 페이지 + 대시보드 링크"
```

---

### Task 5: 전체 회귀

- [ ] **Step 1: 전체 테스트 + 스모크**

Run: `python3 -m pytest -q`
Expected: 전체 통과(archive_store 4 + article_store 신규 1 포함, 회귀 없음)

Run: `python3 -c "import main, archive_store, article_store; print('OK')"`
Expected: `OK`

---

## 배포 & 검증 (구현·테스트 완료 후)

1. `main` 머지 → push → VM 반영(flock pull).
2. **시딩 1회(VM, flock) — 30일 보존 적용 전에 먼저**:

```bash
ssh -i ~/.ssh/oracle_cig.key ubuntu@140.245.72.164 \
  'cd cig-monitor && flock -w 120 /tmp/cig-monitor.lock ./venv/bin/python -c "import archive_store, article_store; archive_store.append_articles(article_store.load_articles()); import json; print(len(json.load(open(\"archive.json\"))), \"archived\")"'
```
Expected: `785 archived`(현재 조합 기사 수) 근처.

3. **커밋·push(VM, flock)** — archive.json 을 저장소에 반영:

```bash
ssh -i ~/.ssh/oracle_cig.key ubuntu@140.245.72.164 \
  'cd cig-monitor && flock -w 120 /tmp/cig-monitor.lock bash -c "git add archive.json && git commit -m \"chore: 조합 기사 아카이브 시딩\" && git pull --rebase origin main && git push origin main"'
```

4. 다음 정상 실행에서 `save_articles`가 30일 초과 조합 기사를 articles.json에서 제외 → 대시보드 조합 기사가 최근 30일치만 남는지 확인.
5. `https://sunkid94.github.io/gongje-monitor/archive.html` — 전체 조합 기사가 월별 제목-링크로 뜨는지, 링크 클릭 시 원문 이동 확인. (GitHub Pages 캐시 지연 감안; `raw.githubusercontent.com/.../main/archive.json` 로 확정 검증)
6. 로컬 `git pull --rebase origin main` 로 archive.json 동기화.

---

## Self-Review 결과

- **스펙 커버리지:** archive.json+archive_store(Task 1)·조합 30일 보존(Task 2)·main 연결(Task 3)·archive.html+링크(Task 4)·회귀(Task 5)·시딩 먼저 후 보존(배포 2·4)·월별 발행일순(Task 4)·파손 보호(Task 1) — 스펙 전 항목 대응.
- **플레이스홀더:** 코드/명령/기대출력 실제 내용. archive.html·index.html 링크는 하네스 부재 명시 후 수동 검증으로 대체(플레이스홀더 아님). `785 archived`는 현재 실측 근사치로 표기.
- **타입 일관성:** `append_articles(list)->None`, lean 스키마 `{title,link,date,keyword}`가 Task 1 구현·테스트·Task 4 렌더(`it.title/link/date`)에서 일치. `RETENTION_DAYS_COMPANY=30`가 Task 2 구현·테스트 일치. main은 `deduped` 그대로 넘김(Task 3).
