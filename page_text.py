"""원문 기사 페이지에서 '기사 본문 요소'의 텍스트만 추출.

왜 본문 요소만인가(2026-10-29 150RT 사건): 페이지 전체 HTML 로 조직명을 부분문자열 매칭하면
'많이 본 뉴스' 사이드바·배너 주석(<!--전문건설공제조합120-->)·메뉴에 섞인 조직명 때문에 그 매체의
모든 기사가 조합 기사로 오분류된다. 본문 요소를 못 찾으면 None 을 돌려주고 페이지 전체로 폴백하지 않는다.
"""
import logging
import re
from html.parser import HTMLParser
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ci-monitor/1.0)"}
_TIMEOUT = 10
# ND소프트 CMS(기계설비신문·대한전문건설신문·한국건설신문·건설이코노미뉴스 공통) 본문 컨테이너.
# 같은 요소에 itemprop="articleBody" 도 붙어 있어 schema.org 마크업을 쓰는 다른 매체도 잡힌다.
_BODY_ID = "article-view-content-div"
_BODY_ITEMPROP = "articleBody"
_SKIP_TAGS = {"script", "style"}
_WS_RE = re.compile(r"\s+")


class _BodyTextParser(HTMLParser):
    """본문 컨테이너를 찾아 그 안의 텍스트만 모은다.

    중첩 깊이는 컨테이너와 같은 태그명(div/article/section)만 세어, 닫히지 않은 <p> 같은 흔한
    비정형 HTML 에도 컨테이너 끝을 제대로 찾는다. 컨테이너가 닫히면 이후는 모두 무시한다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = False
        self.parts = []
        self._tag = None        # 컨테이너 태그명
        self._depth = 0         # 컨테이너와 같은 태그명의 중첩 깊이 (0 = 컨테이너 밖/종료)
        self._skip = None       # 현재 열린 script/style 태그명
        self._done = False

    def handle_starttag(self, tag, attrs):
        if self._done:
            return
        if not self.found:
            a = dict(attrs)
            if a.get("id") == _BODY_ID or a.get("itemprop") == _BODY_ITEMPROP:
                self.found = True
                self._tag = tag
                self._depth = 1
            return
        if tag == self._tag:
            self._depth += 1
        elif tag in _SKIP_TAGS and self._skip is None:
            self._skip = tag

    def handle_endtag(self, tag):
        if self._done or not self.found:
            return
        if tag == self._skip:
            self._skip = None
            return
        if tag == self._tag:
            self._depth -= 1
            if self._depth == 0:
                self._done = True

    def handle_data(self, data):
        if self.found and not self._done and self._skip is None:
            self.parts.append(data)


def extract_article_text(html: str) -> Optional[str]:
    """HTML 에서 본문 요소의 텍스트(태그 제거·엔티티 해제·공백 정리). 본문 요소가 없으면 None."""
    if not html:
        return None
    parser = _BodyTextParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as e:  # html.parser 는 관대하지만 방어
        logger.warning("본문 파싱 실패: %s", e)
        return None
    if not parser.found:
        return None
    return _WS_RE.sub(" ", " ".join(parser.parts)).strip()


def fetch_article_text(url: str) -> Optional[str]:
    """원문 페이지를 받아 본문 텍스트를 추출. 페치 실패·본문 요소 없음 → None(판정 불가, 호출자가 보류)."""
    try:
        r = requests.get(url, timeout=_TIMEOUT, headers=_HEADERS)
        r.raise_for_status()
    except Exception as e:
        logger.warning("본문 페치 실패(%s): %s", url, e)
        return None
    text = extract_article_text(r.text)
    if text is None:
        logger.info("본문 요소 없음 — 판정 보류: %s", url)
    return text
