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
    # is_company 기사(조합 직접 언급)는 무조건 보존, 나머지에서 limit 채움.
    # 종합건설사 등 대량 키워드 추가 시 조합 기사가 밀려나지 않게.
    company = [a for a in articles if a.get("is_company")]
    others = [a for a in articles if not a.get("is_company")]
    quota_for_others = max(0, MAX_ARTICLES - len(company))
    kept = company + others[:quota_for_others]
    with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)


def add_articles(new_articles: list) -> None:
    existing = load_articles()
    timestamped = [
        {**a, "collected_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
        for a in new_articles
    ]
    save_articles(timestamped + existing)
