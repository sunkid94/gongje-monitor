"""1회성 마이그레이션: 구 articles.json 에 신규 필드를 채운다.

사용법:
    python scripts/migrate_articles.py                 # articles.json 자동 백업 후 변환
    python scripts/migrate_articles.py path/to/file.json
"""
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import COMPANY_KEYWORDS, CATEGORY_KEYWORDS

_PUBLISHER_SUFFIX_RE = re.compile(r"\s+-\s+([^-]+?)\s*$")


def _lookup_category(keyword: str) -> str:
    if keyword in COMPANY_KEYWORDS:
        return "조합"
    for category, kws in CATEGORY_KEYWORDS.items():
        if keyword in kws:
            return category
    return "(미분류)"


def _migrate_one(article: dict) -> dict:
    if "category" in article and "sentiment" in article:
        return article  # 이미 마이그레이션됨

    keyword = article.get("keyword", "")
    title = article.get("title", "")
    m = _PUBLISHER_SUFFIX_RE.search(title)
    publisher = m.group(1).strip() if m else ""
    title_clean = _PUBLISHER_SUFFIX_RE.sub("", title)

    link = article.get("link", "")
    cluster_id = hashlib.sha1(link.encode("utf-8")).hexdigest()[:4]

    return {
        **article,
        "category": _lookup_category(keyword),
        "is_company": keyword in COMPANY_KEYWORDS,
        "title_clean": title_clean,
        "publisher": publisher,
        "sentiment": "neutral",
        "importance": 0,
        "cluster_id": cluster_id,
    }


def migrate(path: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    migrated = [_migrate_one(a) for a in articles]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(migrated, f, ensure_ascii=False, indent=2)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "articles.json")
    backup = target + ".pre-migration-backup"
    if not os.path.exists(backup):
        shutil.copy2(target, backup)
        print(f"백업 저장: {backup}")
    migrate(target)
    print(f"마이그레이션 완료: {target}")


if __name__ == "__main__":
    main()
