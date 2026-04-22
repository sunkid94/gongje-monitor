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
