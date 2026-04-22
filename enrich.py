import hashlib
import re


_PUBLISHER_SUFFIX_RE = re.compile(r"\s+-\s+([^-]+?)\s*$")


def extract_publisher(title: str) -> str:
    m = _PUBLISHER_SUFFIX_RE.search(title)
    return m.group(1).strip() if m else ""


def normalize_title(title: str) -> str:
    title = _PUBLISHER_SUFFIX_RE.sub("", title)
    return re.sub(r"[\s\W_]+", "", title.lower())


def _tokens(title: str) -> set:
    cleaned = _PUBLISHER_SUFFIX_RE.sub("", title)
    return set(re.findall(r"\w+", cleaned.lower()))


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _cluster_id(norm: str) -> str:
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:4]


def cluster_articles(articles: list) -> list:
    """각 기사에 cluster_id 부여. 정규화 제목 완전 일치 또는 토큰 자카드 0.85 이상이면 동일 cluster."""
    clusters = []  # list of (representative_norm, cluster_id, token_set)
    result = []

    for a in articles:
        norm = normalize_title(a["title"])
        tokens = _tokens(a["title"])
        matched_id = None

        for rep_norm, cid, rep_tokens in clusters:
            if norm == rep_norm or _jaccard(tokens, rep_tokens) >= 0.85:
                matched_id = cid
                break

        if matched_id is None:
            matched_id = _cluster_id(norm or a["link"])
            clusters.append((norm, matched_id, tokens))

        result.append({**a, "cluster_id": matched_id})

    return result
