import json
import os
from datetime import datetime, timedelta

ARTICLES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "articles.json")
MAX_ARTICLES = 2000           # 전체 안전 상한 (평소엔 안 닿음)
MAX_CORP_ARTICLES = 1000      # 종합건설사 카테고리 캡 (단일 카테고리가 전체를 압도하지 않도록)
RETENTION_DAYS = 60           # 일반 기사 보존 기간 (조합 기사는 무기한)
CORP_CATEGORY = "종합건설사"


def load_articles() -> list:
    try:
        with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_articles(articles: list) -> None:
    """저장 정책:
    - is_company=true (조합·협회 직접 언급) 기사는 무기한 보존
    - 종합건설사 카테고리는 RETENTION_DAYS 이내 + 최신순 MAX_CORP_ARTICLES 개로 캡
    - 그 외 일반 기사는 RETENTION_DAYS 이내 보존
    - 전체가 MAX_ARTICLES 를 넘으면 일반 기사부터 최신순으로 자름 (anti-runaway)

    입력 articles 는 최신 우선 정렬 가정 (add_articles 가 새 기사를 앞에 prepend).
    """
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    company = []
    corp = []
    others = []
    for a in articles:
        if a.get("is_company"):
            company.append(a)
            continue
        try:
            collected = datetime.strptime(a.get("collected_at", ""), "%Y-%m-%dT%H:%M:%S")
            if collected < cutoff:
                continue
        except ValueError:
            pass  # 시각 파싱 실패 시 보존
        if a.get("category") == CORP_CATEGORY:
            corp.append(a)
        else:
            others.append(a)
    corp = corp[:MAX_CORP_ARTICLES]
    quota_for_others = max(0, MAX_ARTICLES - len(company) - len(corp))
    kept = company + corp + others[:quota_for_others]
    with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)


def add_articles(new_articles: list) -> None:
    existing = load_articles()
    timestamped = [
        {**a, "collected_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
        for a in new_articles
    ]
    save_articles(timestamped + existing)
