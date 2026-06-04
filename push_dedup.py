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


def story_key(title: str) -> set:
    """제목을 정규화해 핵심어 토큰 집합을 반환."""
    if not title:
        return set()
    body = title.rsplit(_PUBLISHER_SEP, 1)[0] if _PUBLISHER_SEP in title else title
    cleaned = _PUNCT_RE.sub(" ", body).lower()
    return {tok for tok in cleaned.split() if len(tok) >= _MIN_TOKEN_LEN}


def similarity(a: set, b: set) -> float:
    """Jaccard 유사도. 합집합이 비면 0."""
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)
