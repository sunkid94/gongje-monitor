import push_dedup


def test_story_key_strips_publisher_suffix():
    key = push_dedup.story_key("전문건설공제조합, 피치 국제신용등급 'A+' 유지 - 이데일리")
    assert "이데일리" not in key
    assert "전문건설공제조합" in key
    assert "피치" in key
    assert "유지" in key


def test_story_key_keeps_rating_token_and_drops_punctuation():
    key = push_dedup.story_key("K-FINCO, 피치 신용등급 'A+' 유지 - 네이트")
    assert "a+" in key          # 'A+' 는 소문자화되어 토큰으로 유지
    assert "," not in "".join(key)


def test_story_key_drops_single_char_tokens():
    key = push_dedup.story_key("A B 전문건설공제조합 - 매체")
    assert "a" not in key       # 길이 1 토큰 제거
    assert "b" not in key
    assert "전문건설공제조합" in key


def test_story_key_empty_title_returns_empty_set():
    assert push_dedup.story_key("") == set()
    assert push_dedup.story_key(None) == set()


def test_similarity_identical_sets_is_one():
    s = {"a", "b", "c"}
    assert push_dedup.similarity(s, s) == 1.0


def test_similarity_disjoint_sets_is_zero():
    assert push_dedup.similarity({"a"}, {"b"}) == 0.0


def test_similarity_jaccard_value():
    # 교집합 4, 합집합 6 → 0.666...
    a = {"전문건설공제조합", "피치", "국제신용등급", "a+", "유지"}
    b = {"전문건설공제조합", "피치", "신용등급", "a+", "유지"}
    assert push_dedup.similarity(a, b) == 4 / 6


def test_similarity_empty_sets_is_zero():
    assert push_dedup.similarity(set(), set()) == 0.0
    assert push_dedup.similarity({"a"}, set()) == 0.0
