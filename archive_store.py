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
