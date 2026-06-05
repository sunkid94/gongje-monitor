"""푸시 스토리 단위 중복제거.

같은 뉴스 사건이 여러 매체/cluster_id 로 흩어져 24시간 내 반복 푸시되는 것을 막는다.
제목 핵심어 집합(story_key) 의 Jaccard 유사도가 임계값 이상이면 같은 스토리로 간주한다.
"""
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timedelta
from typing import List, Tuple

logger = logging.getLogger(__name__)

PUSHED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pushed.json")
SIMILARITY_THRESHOLD = 0.6
WINDOW_HOURS = 24
_MIN_TOKEN_LEN = 2

# 매체명 접미사 분리용: 제목은 "… 본문 - 매체명" 형태
_PUBLISHER_SEP = " - "
# 토큰 경계로 치환할 기호 (단, '+' 는 'A+' 같은 등급 표기 보존 위해 제외)
_PUNCT_RE = re.compile(r"""["'''""()\[\]<>·,.\-–—:;!?…""'']+""")
# 선두 대괄호 섹션 태그 (예: "[마켓인]나신평…") — lead 추출 시 제거
_LEADING_BRACKET_RE = re.compile(r"^\s*\[[^\]]*\]\s*")

# 같은 조직의 다른 표기 — 여기에 추가하면 묶임 (모두 소문자/정규화 형태로 비교됨)
ORG_ALIASES = {
    "전문건설공제조합": ["전문조합", "k finco", "kfinco", "k-finco"],
    "기계설비건설공제조합": ["cig", "기계설비공제조합"],   # 우리 조합
}


def story_key(title: str) -> set:
    """제목을 정규화해 핵심어 토큰 집합을 반환."""
    if not title:
        return set()
    body = title.rsplit(_PUBLISHER_SEP, 1)[0] if _PUBLISHER_SEP in title else title
    cleaned = _PUNCT_RE.sub(" ", body).lower()
    return {tok for tok in cleaned.split() if len(tok) >= _MIN_TOKEN_LEN}


def story_lead(title: str) -> str:
    """제목의 선두 조직명(첫 쉼표 앞)을 정규화해 반환 — 스토리 동일성의 앵커.

    같은 이벤트라도 주체 조직이 다르면(예: 기계설비건설공제조합 vs 전문건설공제조합)
    별개 스토리로 보고 억제하지 않기 위함. 매체명 접미사 제거 후 첫 쉼표 앞을 사용한다.
    선두 대괄호 섹션 태그(예: "[마켓인]")는 제거한다. 쉼표가 없으면 본문 전체가 lead가 된다.
    """
    if not title:
        return ""
    body = title.rsplit(_PUBLISHER_SEP, 1)[0] if _PUBLISHER_SEP in title else title
    head = body.split(",", 1)[0]
    head = _LEADING_BRACKET_RE.sub("", head)
    cleaned = _PUNCT_RE.sub(" ", head).lower()
    return " ".join(cleaned.split())


def canonical_org(title: str) -> str:
    """선두 조직명을 대표 이름으로 환산. 별칭이면 대표값, 아니면 lead 원본.

    ORG_ALIASES 의 대표명 또는 별칭 문자열이 정규화된 lead 에 포함되면 그 대표명을 반환한다.
    목록에 없으면 lead 를 그대로 돌려준다(보수적 = 안 묶음). 더 구체적인(긴) 후보부터
    검사해 짧은 별칭의 오매칭을 줄인다.
    """
    lead = story_lead(title)
    if not lead:
        return ""
    candidates = []
    for canon, aliases in ORG_ALIASES.items():
        for name in [canon] + aliases:
            candidates.append((name.lower(), canon))
    candidates.sort(key=lambda x: len(x[0]), reverse=True)
    for name, canon in candidates:
        if name in lead:
            return canon
    return lead


def similarity(a: set, b: set) -> float:
    """Jaccard 유사도. 합집합이 비면 0."""
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def load_pushed(now: datetime) -> List[dict]:
    """pushed.json 로드 — WINDOW_HOURS 이내 항목만, tokens 를 set 으로 복원.

    파일 없음/JSON 손상 시 빈 리스트(안전쪽: 이력 없으면 발송 진행 → 알림 누락 방지).
    """
    try:
        with open(PUSHED_FILE, "r", encoding="utf-8") as fp:
            raw = json.load(fp)
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("pushed.json 로드 실패(빈 이력으로 진행): %s", e)
        return []

    cutoff = now - timedelta(hours=WINDOW_HOURS)
    out = []
    for item in raw if isinstance(raw, list) else []:
        try:
            pushed_at = _parse_dt(item["pushed_at"])
        except (KeyError, ValueError, TypeError):
            continue
        if pushed_at < cutoff:
            continue
        out.append({
            "tokens": set(item.get("tokens", [])),
            "lead": item.get("lead", ""),
            "pushed_at": item["pushed_at"],
            "title": item.get("title", ""),
        })
    return out


def save_pushed(entries: List[dict], now: datetime) -> None:
    """WINDOW_HOURS 경과분 정리 후 원자적(temp + os.replace)으로 저장. tokens 는 list 직렬화."""
    cutoff = now - timedelta(hours=WINDOW_HOURS)
    serializable = []
    for e in entries:
        try:
            if _parse_dt(e["pushed_at"]) < cutoff:
                continue
        except (KeyError, ValueError, TypeError):
            continue
        serializable.append({
            "tokens": sorted(e.get("tokens", [])),
            "lead": e.get("lead", ""),
            "pushed_at": e["pushed_at"],
            "title": e.get("title", ""),
        })
    dir_ = os.path.dirname(os.path.abspath(PUSHED_FILE))
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".pushed-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(serializable, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, PUSHED_FILE)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def filter_unpushed(company_articles: List[dict], now: datetime) -> Tuple[List[dict], List[dict]]:
    """24h 내 이미 푸시한 스토리와 Jaccard >= 임계값이면 억제.

    반환: (to_push, suppressed). 새로 채택한 스토리는 pushed.json 에 기록한다.
    제목 키가 비면(추출 실패) 안전쪽으로 발송하되 이력에는 남기지 않는다.
    """
    accepted = load_pushed(now)          # 비교 기준: 이력 + 이번 배치에서 채택된 것
    now_iso = now.isoformat()
    to_push: List[dict] = []
    suppressed: List[dict] = []

    for art in company_articles:
        title = art.get("title", "")
        key = story_key(title)
        lead = story_lead(title)
        if key and any(
            e["tokens"] and e.get("lead", "") == lead
            and similarity(key, e["tokens"]) >= SIMILARITY_THRESHOLD
            for e in accepted
        ):
            suppressed.append(art)
            continue
        to_push.append(art)
        if key:
            accepted.append({"tokens": key, "lead": lead, "pushed_at": now_iso, "title": title})

    save_pushed(accepted, now)
    return to_push, suppressed
