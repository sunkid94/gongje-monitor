"""푸시 스토리 단위 중복제거.

같은 뉴스 사건이 여러 매체/표기/수식어로 흩어져 7일 내 반복 푸시되는 것을 막는다.
대표조직(canonical_org) 이 같고 핵심어 포함도(overlap) 가 임계값 이상이면 같은 스토리로 본다.
"""
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timedelta
from typing import List, Tuple

from config import COMPANY_KEYWORDS, COMPANY_ALIASES

logger = logging.getLogger(__name__)

PUSHED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pushed.json")
OVERLAP_THRESHOLD = 0.7
WINDOW_HOURS = 168   # 7일 — 며칠 이어지는 사건도 1번만 알림
_MIN_TOKEN_LEN = 2

# 등급/전망 '방향' 토큰 — 방향이 서로 다르면 같은 조직·유사 제목이라도 다른 사건(놓치면 안 됨)
RATING_DIRECTION_TOKENS = {"상향", "하향", "유지", "강등", "상승", "하락"}

# 매체명 접미사 분리용: 제목은 "… 본문 - 매체명" 형태
_PUBLISHER_SEP = " - "
# 토큰 경계로 치환할 기호 (단, '+' 는 'A+' 같은 등급 표기 보존 위해 제외)
_PUNCT_RE = re.compile(r"""["'''""()\[\]<>·,.\-–—:;!?…""'']+""")
# 선두 대괄호 섹션 태그 (예: "[마켓인]나신평…") — lead 추출 시 제거
_LEADING_BRACKET_RE = re.compile(r"^\s*\[[^\]]*\]\s*")

# 같은 조직의 다른 표기 — 여기에 추가하면 묶임.
# 주의: story_lead 가 소문자화 + 구두점을 공백으로 바꾸므로, 별칭은 그 결과 형태(공백 구분,
# 하이픈 없음)로 적어야 함. 예: "K-FINCO" 가 아니라 "k finco".
ORG_ALIASES = {
    "전문건설공제조합": ["전문조합", "k finco", "kfinco"],
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
    padded = f" {lead} "
    for name, canon in candidates:
        if f" {name} " in padded:
            return canon
    return lead


def _normalize(text: str) -> str:
    return " " + " ".join(_PUNCT_RE.sub(" ", (text or "").lower()).split()) + " "


def label_canon(label: str) -> str:
    """이벤트 라벨에서 추적 조직(정식명/별칭)을 찾아 대표명 반환. 없으면 정규화 라벨 전체(폴백).

    AI 라벨이 대표조직명으로 시작하므로 보통 바로 매칭된다. 더 긴 이름 우선(짧은 별칭 오매칭 방지),
    공백 경계 매칭.
    참고: 라벨은 AI가 대표조직 정식명으로 생성하므로(enrich 프롬프트), 한글 약칭은 거의 안 나온다.
    그래서 여기선 config.COMPANY_ALIASES(영문 브랜드 K-FINCO/CIG)만으로 충분하다. (title 폴백 경로의
    canonical_org 는 별도의 push_dedup.ORG_ALIASES 를 쓴다 — 두 경로의 별칭 소스가 다른 건 의도된 것.)
    """
    nlabel = _normalize(label)
    candidates = []
    for canon in COMPANY_KEYWORDS:
        for name in [canon] + COMPANY_ALIASES.get(canon, []):
            candidates.append((_normalize(name).strip(), canon))
    candidates.sort(key=lambda x: len(x[0]), reverse=True)
    for nname, canon in candidates:
        if nname and f" {nname} " in nlabel:
            return canon
    return nlabel.strip()


def overlap(a: set, b: set) -> float:
    """포함도 계수 = 교집합 / 더 짧은 쪽 크기. 둘 중 하나라도 비면 0.

    수식어가 붙어 길어진 헤드라인 변형(짧은 제목 ⊂ 긴 제목)을 Jaccard 보다 잘 잡는다.
    """
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


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
            "canon": item.get("canon", ""),
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
            "canon": e.get("canon", ""),
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


def _same_story(key: set, canon: str, entry: dict) -> bool:
    """이미 푸시한 entry 와 같은 스토리인지 — 대표조직 일치 + 포함도>=임계값.

    단, 등급 '방향'(상향/하향/유지 등)이 둘 다 있으면서 서로 다르면 다른 사건으로 본다
    (예: '상향' 뉴스가 직전 '유지' 알림에 묻혀 누락되는 것 방지).
    """
    if not entry["tokens"] or entry.get("canon", "") != canon:
        return False
    if overlap(key, entry["tokens"]) < OVERLAP_THRESHOLD:
        return False
    d1 = key & RATING_DIRECTION_TOKENS
    d2 = entry["tokens"] & RATING_DIRECTION_TOKENS
    if d1 and d2 and d1 != d2:
        return False
    return True


def filter_unpushed(company_articles: List[dict], now: datetime) -> Tuple[List[dict], List[dict]]:
    """7일 내 같은 대표조직·같은 사건(overlap>=임계값)으로 이미 푸시했으면 억제.

    반환: (to_push, suppressed). 새로 채택한 스토리는 pushed.json 에 기록한다.
    제목 키가 비면(추출 실패) 안전쪽으로 발송하되 이력에는 남기지 않는다.
    """
    accepted = load_pushed(now)          # 비교 기준: 이력 + 이번 배치에서 채택된 것
    now_iso = now.isoformat()
    to_push: List[dict] = []
    suppressed: List[dict] = []

    for art in company_articles:
        label = art.get("event_label")
        if label:
            key = story_key(label)
            canon = label_canon(label)
        else:
            title = art.get("title", "")
            key = story_key(title)
            canon = canonical_org(title)
        if key and any(_same_story(key, canon, e) for e in accepted):
            suppressed.append(art)
            continue
        to_push.append(art)
        if key:
            accepted.append({"tokens": key, "canon": canon, "pushed_at": now_iso, "title": art.get("title", "")})

    save_pushed(accepted, now)
    return to_push, suppressed
