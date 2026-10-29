from unittest.mock import patch

import main


def test_main_saves_judged_links_even_when_nothing_new_fetched():
    """소스가 '본문까지 봤는데 무관'으로 판정한 링크(seen_out)는 수집 0건이어도 seen 에 저장돼야
    24h 윈도 동안 2분마다 같은 기사를 재페치·재판정하지 않는다."""
    def fake_fetch(seen, seen_out=None):
        seen_out.add("http://kmec/judged")
        return []

    with patch.object(main, "load_seen", return_value={"http://old"}), \
         patch.object(main, "fetch_new_articles", side_effect=fake_fetch), \
         patch.object(main, "save_seen") as save:
        main.main(skip_email=True, fast=False)
    save.assert_called_once_with({"http://old", "http://kmec/judged"})


def test_main_fast_path_saves_judged_links_too():
    def fake_fetch(seen, seen_out=None):
        seen_out.add("http://rss/judged")
        return []

    with patch.object(main, "load_seen", return_value=set()), \
         patch.object(main, "fetch_trade_only", side_effect=fake_fetch), \
         patch.object(main, "save_seen") as save:
        main.main(skip_email=True, fast=True)
    save.assert_called_once_with({"http://rss/judged"})


def test_main_does_not_rewrite_seen_when_nothing_fetched_or_judged():
    # seen.json 은 수만 건(13MB) — 변화 없으면 2분마다 다시 쓰지 않는다
    def fake_fetch(seen, seen_out=None):
        return []

    with patch.object(main, "load_seen", return_value={"http://old"}), \
         patch.object(main, "fetch_trade_only", side_effect=fake_fetch), \
         patch.object(main, "save_seen") as save:
        main.main(skip_email=True, fast=True)
    save.assert_not_called()
