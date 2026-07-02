import json
import os
import re
from datetime import datetime, timedelta
from typing import Optional

ARTICLES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "articles.json")
MAX_ARTICLES = 2000           # 전체 안전 상한 (평소엔 안 닿음)
MAX_CORP_ARTICLES = 1000      # 종합건설사 카테고리 캡 (단일 카테고리가 전체를 압도하지 않도록)
RETENTION_DAYS = 60           # 일반 기사 보존 기간 (조합 기사는 무기한)
CORP_CATEGORY = "종합건설사"

TITLE_SHORT_LEN = 12          # title 길이 임계값 — 미만이면 짧다고 판정
DESC_STUB_TEXT_LEN = 15       # description HTML 제거 후 텍스트 길이 임계값

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITY_RE = re.compile(r"&[a-zA-Z#0-9]+;")


def is_empty_stub(title: str, description: str) -> bool:
    """Google News 가 가끔 발급하는 '제목만 있는' 빈 entry 판정.

    조건 (둘 다 만족해야 stub 으로 판정):
    1) title 이 짧다 (TITLE_SHORT_LEN 미만) — "장관 - 국토교통부" 같이 한두 단어뿐인 케이스
    2) description 텍스트 콘텐츠도 짧다 (DESC_STUB_TEXT_LEN 미만)

    Google News RSS 의 description 은 항상 `<a>제목</a>&nbsp;<font>발행지</font>` 형태라
    HTML 제거 후 텍스트가 제목+발행지 뿐이다. 짧은 제목 + 짧은 description = 본문 없음.

    description 이 아예 비어 있으면(테스트 픽스처·비표준 소스 등) stub 으로 단정하지 않음 —
    실제 운영 환경에서는 RSS 가 항상 description 을 채워 보내므로 false negative 발생 X.
    """
    title = (title or "").strip()
    description = description or ""
    if not title and not description:
        return False  # 양쪽 다 정보 없음 — 보수적으로 통과 (테스트 픽스처 호환)
    if not title:
        return True   # description 만 있고 title 비어있으면 RSS 노이즈
    if not description:
        return False  # title 만 있고 description 없으면 통과 (비표준 소스)
    if len(title) >= TITLE_SHORT_LEN:
        return False
    text = _HTML_TAG_RE.sub("", description)
    text = _HTML_ENTITY_RE.sub(" ", text)
    return len(text.strip()) < DESC_STUB_TEXT_LEN


def parse_collected_at(s: str) -> datetime:
    """collected_at 문자열을 timezone-aware datetime 으로 파싱.

    구버전(타임존 없음, "2026-05-31T22:04:55")도 호환 — 시스템 로컬 타임존으로 간주한다.
    """
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def format_collected_at(dt: Optional[datetime] = None) -> str:
    """collected_at 직렬화 포맷 — 타임존 오프셋 포함 ("...+09:00").

    프론트엔드(index.html) 의 relativeTime() 이 타임존 오프셋을 정상 인식하려면
    저장 시점에 타임존을 명시해야 한다. (없으면 JS 는 UTC 로 간주해 9시간 미래로 계산함)
    """
    if dt is None:
        dt = datetime.now().astimezone()
    elif dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.isoformat(timespec="seconds")


def load_articles() -> list:
    try:
        with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def filter_duplicates(new_articles: list) -> list:
    """기존 저장본 + 신규 배치 내부에서 (publisher, cluster_id) 가 일치하는 중복 제거.

    Google News 가 같은 기사에 매번 다른 리다이렉트 URL 을 발급하기 때문에
    seen_store(URL 기반) 만으로는 같은 매체의 같은 기사 재수집을 못 막는다.
    이 함수는 enrich 가 부여한 cluster_id(정규화 제목 해시) 와 publisher 조합으로
    한 번 더 거른다.
    """
    existing = load_articles()
    seen_keys = {
        (a.get("publisher"), a.get("cluster_id"))
        for a in existing
        if a.get("publisher") and a.get("cluster_id")
    }
    out = []
    for a in new_articles:
        publisher = a.get("publisher")
        cluster_id = a.get("cluster_id")
        if publisher and cluster_id:
            key = (publisher, cluster_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)  # 같은 배치 내 후속 중복도 차단
        out.append(a)
    return out


def _dedup_existing(articles: list) -> list:
    """저장본 내 (publisher, cluster_id) 중복 제거 — 가장 오래된 entry 만 유지.

    save_articles 호출 시 매번 적용되어 누적된 중복을 자동 정리한다.
    """
    oldest_idx_by_key: dict = {}
    no_key_idx: set = set()
    for i, a in enumerate(articles):
        publisher = a.get("publisher")
        cluster_id = a.get("cluster_id")
        if not (publisher and cluster_id):
            no_key_idx.add(i)
            continue
        key = (publisher, cluster_id)
        existing_i = oldest_idx_by_key.get(key)
        if existing_i is None:
            oldest_idx_by_key[key] = i
            continue
        current_coll = a.get("collected_at", "")
        existing_coll = articles[existing_i].get("collected_at", "")
        if current_coll and (not existing_coll or current_coll < existing_coll):
            oldest_idx_by_key[key] = i
    kept = no_key_idx | set(oldest_idx_by_key.values())
    return [a for i, a in enumerate(articles) if i in kept]


def save_articles(articles: list) -> None:
    """저장 정책:
    - is_company=true (조합·협회 직접 언급) 기사는 무기한 보존
    - 종합건설사 카테고리는 RETENTION_DAYS 이내 + 최신순 MAX_CORP_ARTICLES 개로 캡
    - 그 외 일반 기사는 RETENTION_DAYS 이내 보존
    - 전체가 MAX_ARTICLES 를 넘으면 일반 기사부터 최신순으로 자름 (anti-runaway)
    - (publisher, cluster_id) 중복은 가장 오래된 entry 만 유지
    - 본문이 없는 빈 껍데기 entry(예: 제목 "장관"만 있는 RSS 노이즈) 폐기

    입력 articles 는 최신 우선 정렬 가정 (add_articles 가 새 기사를 앞에 prepend).
    저장 시 collected_at 을 타임존 명시 포맷으로 마이그레이션한다 (구버전 데이터 자동 업그레이드).
    """
    articles = [a for a in articles if not is_empty_stub(a.get("title", ""), a.get("description", ""))]
    articles = _dedup_existing(articles)
    cutoff = datetime.now().astimezone() - timedelta(days=RETENTION_DAYS)
    company = []
    corp = []
    others = []
    for a in articles:
        if a.get("collected_at"):
            try:
                normalized = format_collected_at(parse_collected_at(a["collected_at"]))
                if normalized != a["collected_at"]:
                    a = {**a, "collected_at": normalized}
            except ValueError:
                pass

        if a.get("is_company"):
            company.append(a)
            continue
        try:
            collected = parse_collected_at(a.get("collected_at", ""))
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
    now_str = format_collected_at()
    timestamped = [
        {**a, "collected_at": now_str}
        for a in new_articles
    ]
    save_articles(timestamped + existing)
