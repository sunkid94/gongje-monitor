import json
import os
from datetime import datetime, timedelta

ARTICLES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "articles.json")
MAX_ARTICLES = 2000        # 안전 상한 (평소엔 안 닿음)
RETENTION_DAYS = 60        # 일반 기사 보존 기간 (조합 기사는 무기한)


def load_articles() -> list:
    try:
        with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_articles(articles: list) -> None:
    """저장 정책:
    - is_company=true (조합 직접 언급) 기사는 무기한 보존
    - 나머지 기사는 RETENTION_DAYS 이내만 보존
    - 그래도 MAX_ARTICLES 초과 시 최신순으로 자름 (anti-runaway)
    """
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    company = []
    others_recent = []
    for a in articles:
        if a.get("is_company"):
            company.append(a)
            continue
        try:
            collected = datetime.strptime(a.get("collected_at", ""), "%Y-%m-%dT%H:%M:%S")
            if collected >= cutoff:
                others_recent.append(a)
        except ValueError:
            others_recent.append(a)  # 시각 파싱 실패 시 안전하게 유지
    quota_for_others = max(0, MAX_ARTICLES - len(company))
    kept = company + others_recent[:quota_for_others]
    with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)


def add_articles(new_articles: list) -> None:
    existing = load_articles()
    timestamped = [
        {**a, "collected_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
        for a in new_articles
    ]
    save_articles(timestamped + existing)
