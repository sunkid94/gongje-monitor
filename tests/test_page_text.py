from unittest.mock import MagicMock, patch

import page_text

# ND소프트 CMS(기계설비신문·전문건설신문·한국건설신문·건설이코노미뉴스 공통) 기사 페이지 축약판.
# 본문 요소(#article-view-content-div) 밖의 메뉴·'많이 본 뉴스'·스크립트·푸터에 협회명이 섞여 있다.
ND_PAGE = """<html><head><title>수열히트펌프 - 기계설비신문</title></head><body>
<nav><a href="/list?sec=1">기계설비건설협회</a></nav>
<aside class="box-skin"><h3>많이 본 뉴스</h3>
  <a href="/news/articleView.html?idxno=52518">기계설비협회-한국물가협회, 적정 공사비 확보 위한 MOU 체결</a>
</aside>
<div class="article-body">
<article id="article-view-content-div" class="article-veiw-body" itemprop="articleBody">
  <p>정부가 데이터센터와 대형 복합건물의 탈탄소를 목표로 수열에너지 보급 확대를 추진하고 있다.</p>
  <div style="text-align:center"><figure><figcaption>사진=기계설비신문</figcaption></figure></div>
  <p>지난 28일 기계설비업계에 따르면 KS 규격이 528kW(약 150RT) 이하에 멈춰 있다.</p>
  <script>$(function(){ var x = "기계설비협회"; })</script>
</article>
</div>
<footer>Copyright 기계설비신문</footer>
</body></html>"""


def test_extract_article_text_returns_body_element_text_only():
    text = page_text.extract_article_text(ND_PAGE)
    assert "수열에너지 보급 확대" in text
    assert "150RT" in text
    # 사이드바('많이 본 뉴스')·메뉴·본문 내 <script>·푸터는 제외
    assert "기계설비협회" not in text
    assert "많이 본 뉴스" not in text
    assert "Copyright" not in text


def test_extract_article_text_keeps_nested_elements_until_body_closes():
    # 본문 안에 <div>가 중첩돼도(cenews 는 본문 자체가 <div>) 첫 닫힘 태그에서 끊지 않는다
    html = ('<div id="article-view-content-div"><div class="a"><p>첫 단락</p></div>'
            '<p>둘째 단락</p></div><aside>기계설비협회</aside>')
    text = page_text.extract_article_text(html)
    assert "첫 단락" in text
    assert "둘째 단락" in text
    assert "기계설비협회" not in text


def test_extract_article_text_unescapes_entities_and_collapses_whitespace():
    html = '<article id="article-view-content-div"><p>협회&middot;조합&nbsp;공동\n\n   발표</p></article>'
    assert page_text.extract_article_text(html) == "협회·조합 공동 발표"


def test_extract_article_text_falls_back_to_itemprop_articlebody():
    html = '<section itemprop="articleBody"><p>본문입니다</p></section><nav>기계설비협회</nav>'
    assert page_text.extract_article_text(html) == "본문입니다"


def test_extract_article_text_returns_none_when_no_body_element():
    # 본문 요소를 못 찾으면 페이지 전체로 폴백하지 않는다(사이드바·배너 오염 방지)
    assert page_text.extract_article_text("<html><body><p>기계설비협회</p></body></html>") is None
    assert page_text.extract_article_text("") is None


def test_fetch_article_text_returns_none_on_http_error():
    with patch("page_text.requests.get", side_effect=RuntimeError("timeout")):
        assert page_text.fetch_article_text("http://x/1") is None


def test_fetch_article_text_returns_none_when_page_has_no_body_element():
    resp = MagicMock(text="<html><body>사이드바 기계설비협회</body></html>", status_code=200)
    with patch("page_text.requests.get", return_value=resp):
        assert page_text.fetch_article_text("http://x/1") is None


def test_fetch_article_text_extracts_from_fetched_page():
    resp = MagicMock(text=ND_PAGE, status_code=200)
    with patch("page_text.requests.get", return_value=resp) as getter:
        text = page_text.fetch_article_text("http://x/1")
    assert "150RT" in text
    assert "기계설비협회" not in text
    getter.assert_called_once()
