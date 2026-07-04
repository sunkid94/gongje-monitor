"""원문 발행일 해상도.

Google News RSS는 옛 기사를 새 사건과 함께 재인덱싱하여 pubDate를 최근으로 노출
시키기 때문에, RSS pubDate 24h 컷오프만으로는 2021년 같은 옛 기사를 거를 수 없다.
원문 페이지의 article:published_time 등 메타태그에서 실제 발행 시각을 가져온다.

처리 단계:
  1) Google News RSS 링크에서 article id 추출
  2) 그 페이지에서 signature(`data-n-a-sg`)와 timestamp(`data-n-a-ts`) 추출
  3) batchexecute API에 [id, ts, sig]로 POST → 원문 URL 받음
  4) 원문 URL을 GET 해서 published meta 파싱
"""
import json
import html
import logging
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# 원문 페이지의 발행사 요약(og:description/meta description) — enrich 입력 보강용.
# 구글뉴스 RSS description 은 본문 없는 HTML 링크뿐이라 요약 품질이 낮은데,
# 발행시각 추출로 이미 원문 페이지를 GET 하므로 같은 응답에서 콘텐츠도 뽑는다(추가 요청 없음).
_CONTENT_PATTERNS = [
    re.compile(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']*)["\']', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']og:description["\']', re.I),
    re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']description["\']', re.I),
]


def _extract_content(page_html: str) -> str:
    """원문 페이지에서 발행사 요약(og:description/meta description) 추출. 없으면 ""."""
    for pat in _CONTENT_PATTERNS:
        m = pat.search(page_html)
        if m and m.group(1).strip():
            return re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()
    return ""

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ci-monitor/1.0)"}
_TIMEOUT = 10
_BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"

_ARTICLE_ID_RE = re.compile(r"/articles/([A-Za-z0-9_-]+)")
_SIG_RE = re.compile(r'data-n-a-sg="([^"]+)"')
_TS_RE = re.compile(r'data-n-a-ts="([^"]+)"')
_JSON_PREFIX_RE = re.compile(r"^\)\]\}'\s*")

_META_PATTERNS = [
    re.compile(
        r'<meta\s+property=["\']article:published_time["\']\s+content=["\']([^"\']+)["\']',
        re.I,
    ),
    re.compile(
        r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']article:published_time["\']',
        re.I,
    ),
    re.compile(
        r'<meta\s+itemprop=["\']datePublished["\']\s+content=["\']([^"\']+)["\']',
        re.I,
    ),
    re.compile(
        r'<meta\s+name=["\']pubdate["\']\s+content=["\']([^"\']+)["\']',
        re.I,
    ),
    re.compile(r'<time[^>]+datetime=["\']([^"\']+)["\']', re.I),
]

_KST = timezone(timedelta(hours=9))

# 포털 전용 발행일 위치 — 표준 메타 밖. 값이 타임존 없는 KST naive 라 +09:00 을 부착한다.
_REGDATE_RE = re.compile(
    r'<meta[^>]+property=["\']og:regDate["\'][^>]+content=["\'](\d{14})["\']', re.I)
_NATE_FIRSTDATE_RE = re.compile(
    r'firstDate["\'][^>]*>[^<]*<em>\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', re.I)


def _parse_regdate(html: str) -> Optional[datetime]:
    """다음 등: og:regDate=YYYYMMDDHHMMSS (KST naive) → KST-aware datetime."""
    m = _REGDATE_RE.search(html)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=_KST)
    except ValueError:
        return None


def _parse_nate_firstdate(html: str) -> Optional[datetime]:
    """네이트: firstDate <em>YYYY-MM-DD HH:MM</em> (KST naive) → KST-aware datetime."""
    m = _NATE_FIRSTDATE_RE.search(html)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=_KST)
    except ValueError:
        return None


def _decode_google_news_url(url: str) -> Optional[str]:
    m = _ARTICLE_ID_RE.search(url)
    if not m:
        return None
    article_id = m.group(1)

    r1 = requests.get(url, timeout=_TIMEOUT, headers=_HEADERS)
    if r1.status_code != 200:
        return None
    sig = _SIG_RE.search(r1.text)
    ts = _TS_RE.search(r1.text)
    if not (sig and ts):
        return None

    payload = [[["Fbv4je", json.dumps([
        "garturlreq",
        [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
         "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
        article_id, int(ts.group(1)), sig.group(1),
    ])]]]
    body = "f.req=" + urllib.parse.quote(json.dumps(payload))
    r2 = requests.post(
        _BATCH_URL,
        data=body,
        timeout=_TIMEOUT,
        headers={**_HEADERS, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
    )
    if r2.status_code != 200:
        return None

    cleaned = _JSON_PREFIX_RE.sub("", r2.text)
    try:
        arr = json.loads(cleaned)
        inner = json.loads(arr[0][2])
        return inner[1]
    except (json.JSONDecodeError, IndexError, TypeError):
        return None


def _extract_published_time(html: str) -> Optional[datetime]:
    for pat in _META_PATTERNS:
        m = pat.search(html)
        if not m:
            continue
        # "Z" 접미사는 3.11 이전 fromisoformat이 처리 못함 → +00:00 으로 정규화
        value = m.group(1).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            continue
    return _parse_regdate(html) or _parse_nate_firstdate(html)


def resolve_published_time_and_content(
    google_news_url: str,
) -> Tuple[Optional[datetime], str, Optional[str]]:
    """Google News RSS URL → (원문 발행 datetime, 발행사 요약 콘텐츠, 디코딩된 원문 URL).
    한 번의 GET 으로 셋 다. 디코딩된 URL 은 호출측이 깨진 링크(예: image_popup) 판별에 쓴다.
    실패 시 (None, "", None) — 디코딩만 되면 URL 은 실림."""
    try:
        real_url = _decode_google_news_url(google_news_url)
        if not real_url:
            return None, "", None
        r = requests.get(real_url, timeout=_TIMEOUT, headers=_HEADERS, allow_redirects=True)
        if r.status_code != 200:
            return None, "", real_url
        # 한국 언론사엔 EUC-KR 페이지가 많음 — charset 미선언 시 requests 가 ISO-8859-1 로
        # 오판해 한글이 깨진다. 실제 인코딩을 감지해 콘텐츠 mojibake 방지.
        if r.encoding is None or r.encoding.lower() in ("iso-8859-1", "ascii"):
            r.encoding = r.apparent_encoding
        return _extract_published_time(r.text), _extract_content(r.text), real_url
    except requests.RequestException as e:
        logger.warning("resolve_published_time 실패 (url=%s): %s", google_news_url[:80], e)
        return None, "", None


def resolve_published_time(google_news_url: str) -> Optional[datetime]:
    """Google News RSS URL → 원문 발행 datetime. 실패 시 None. (콘텐츠 없이 발행시각만.)"""
    return resolve_published_time_and_content(google_news_url)[0]
