from enrich import normalize_title, extract_publisher


def test_normalize_title_strips_publisher_suffix():
    assert normalize_title("현대건설 사우디 수주 확대 - 조선비즈") == "현대건설사우디수주확대"


def test_normalize_title_removes_whitespace_and_punctuation():
    assert normalize_title('"태영건설" 워크아웃, 1주년…') == "태영건설워크아웃1주년"


def test_normalize_title_handles_no_suffix():
    assert normalize_title("그냥 제목") == "그냥제목"


def test_normalize_title_handles_multiple_dashes():
    # 마지막 " - " 만 제거
    assert normalize_title("A-B 논란 - 매경") == "ab논란"


def test_extract_publisher_returns_suffix():
    assert extract_publisher("현대건설 사우디 수주 확대 - 조선비즈") == "조선비즈"


def test_extract_publisher_returns_empty_when_no_suffix():
    assert extract_publisher("그냥 제목") == ""


def test_extract_publisher_trims_whitespace():
    assert extract_publisher("제목 -  머니투데이  ") == "머니투데이"


from enrich import cluster_articles


def _art(title, link):
    return {"title": title, "link": link, "description": ""}


def test_cluster_articles_assigns_cluster_id():
    articles = [_art("제목A", "l1"), _art("제목B", "l2")]
    result = cluster_articles(articles)
    assert "cluster_id" in result[0]
    assert result[0]["cluster_id"] != result[1]["cluster_id"]


def test_cluster_articles_groups_exact_normalized_match():
    articles = [
        _art("태영건설 워크아웃 1주년 - 조선비즈", "l1"),
        _art("태영건설 워크아웃 1주년 - 매경", "l2"),
    ]
    result = cluster_articles(articles)
    assert result[0]["cluster_id"] == result[1]["cluster_id"]


def test_cluster_articles_groups_jaccard_similar():
    # 토큰 자카드 >= 0.85 → 같은 cluster
    articles = [
        _art("태영건설 워크아웃 1주년 재무 개선 미흡", "l1"),
        _art("태영건설 워크아웃 1주년 재무개선 미흡", "l2"),  # 공백 1개 차이
    ]
    result = cluster_articles(articles)
    assert result[0]["cluster_id"] == result[1]["cluster_id"]


def test_cluster_articles_keeps_different_apart():
    articles = [
        _art("태영건설 워크아웃 1주년", "l1"),
        _art("현대건설 사우디 수주", "l2"),
    ]
    result = cluster_articles(articles)
    assert result[0]["cluster_id"] != result[1]["cluster_id"]


def test_cluster_articles_cluster_id_is_4char_hex():
    articles = [_art("제목", "l1")]
    result = cluster_articles(articles)
    assert len(result[0]["cluster_id"]) == 4
    assert all(c in "0123456789abcdef" for c in result[0]["cluster_id"])
