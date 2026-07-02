from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import importlib


def _resp(items, error=None):
    r = MagicMock()
    r.json.return_value = {"errorCode": error, "errorMessage": "e"} if error else {"items": items}
    return r


def _item(title, link, pub="Fri, 05 Jun 2026 08:00:00 +0900", desc=""):
    return {"title": title, "originallink": link, "link": link, "description": desc, "pubDate": pub}


def _env():
    return patch.dict("os.environ", {"NAVER_CLIENT_ID": "id", "NAVER_CLIENT_SECRET": "sec"})


def _frozen_dt():
    fixed = datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc)   # 18:00 KST — pub 08:00 KST is within 24h
    m = MagicMock(spec=datetime)
    m.now.side_effect = lambda tz=None: fixed
    return m


def test_naver_maps_item_with_publisher_suffix():
    import source_naver
    importlib.reload(source_naver)
    items = [_item("K-FINCO 하반기 채용", "https://www.koscaj.com/news/1", desc="전문건설공제조합 채용")]
    with _env(), patch("source_naver.requests.get", return_value=_resp(items)), \
         patch("source_naver.COMPANY_KEYWORDS", ["전문건설공제조합"]), \
         patch("source_naver.CATEGORY_KEYWORDS", {}):
        source_naver.datetime = _frozen_dt()
        out = source_naver.fetch()
    assert len(out) == 1
    assert out[0]["title"] == "K-FINCO 하반기 채용 - 대한전문건설신문"
    assert out[0]["link"] == "https://www.koscaj.com/news/1"
    assert out[0]["is_company"] is True


def test_naver_filters_irrelevant_items():
    import source_naver
    importlib.reload(source_naver)
    items = [_item("전세사기 대처법", "https://x.com/1", desc="부동산")]
    with _env(), patch("source_naver.requests.get", return_value=_resp(items)), \
         patch("source_naver.COMPANY_KEYWORDS", ["전문건설공제조합"]), \
         patch("source_naver.CATEGORY_KEYWORDS", {}):
        source_naver.datetime = _frozen_dt()
        out = source_naver.fetch()
    assert out == []


def test_naver_handles_api_error():
    import source_naver
    importlib.reload(source_naver)
    with _env(), patch("source_naver.requests.get", return_value=_resp([], error="024")), \
         patch("source_naver.COMPANY_KEYWORDS", ["전문건설공제조합"]), \
         patch("source_naver.CATEGORY_KEYWORDS", {}):
        out = source_naver.fetch()
    assert out == []


def test_naver_skips_when_no_keys():
    import source_naver
    importlib.reload(source_naver)
    with patch.dict("os.environ", {}, clear=True), \
         patch("source_naver.COMPANY_KEYWORDS", ["전문건설공제조합"]), \
         patch("source_naver.CATEGORY_KEYWORDS", {}):
        out = source_naver.fetch()
    assert out == []


def test_naver_skips_seen_link():
    import source_naver
    importlib.reload(source_naver)
    items = [_item("전문건설공제조합 소식", "https://www.koscaj.com/news/2", desc="전문건설공제조합")]
    with _env(), patch("source_naver.requests.get", return_value=_resp(items)), \
         patch("source_naver.COMPANY_KEYWORDS", ["전문건설공제조합"]), \
         patch("source_naver.CATEGORY_KEYWORDS", {}):
        source_naver.datetime = _frozen_dt()
        out = source_naver.fetch(seen={"https://www.koscaj.com/news/2"})
    assert out == []


def test_naver_drops_old_articles():
    import source_naver
    importlib.reload(source_naver)
    # pub 2026-05-31, frozen now 2026-06-05 18:00 KST → 24h 창 밖
    items = [_item("전문건설공제조합 옛 기사", "https://www.koscaj.com/old",
                   pub="Mon, 01 Jun 2026 00:00:00 +0900", desc="전문건설공제조합")]
    with _env(), patch("source_naver.requests.get", return_value=_resp(items)), \
         patch("source_naver.COMPANY_KEYWORDS", ["전문건설공제조합"]), \
         patch("source_naver.CATEGORY_KEYWORDS", {}):
        source_naver.datetime = _frozen_dt()
        out = source_naver.fetch()
    assert out == []
