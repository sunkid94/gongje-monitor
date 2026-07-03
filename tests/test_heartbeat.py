from unittest.mock import patch

import requests

import heartbeat


def test_ping_calls_get_when_url_set():
    with patch.dict("os.environ", {"HEALTHCHECK_URL": "https://hc-ping.com/abc"}), \
         patch("heartbeat.requests.get") as mget:
        heartbeat.ping()
    mget.assert_called_once_with("https://hc-ping.com/abc", timeout=5)


def test_ping_fail_appends_fail_suffix():
    with patch.dict("os.environ", {"HEALTHCHECK_URL": "https://hc-ping.com/abc"}), \
         patch("heartbeat.requests.get") as mget:
        heartbeat.ping_fail()
    mget.assert_called_once_with("https://hc-ping.com/abc/fail", timeout=5)


def test_ping_noop_when_url_missing():
    with patch.dict("os.environ", {}, clear=True), \
         patch("heartbeat.requests.get") as mget:
        heartbeat.ping()
    mget.assert_not_called()


def test_ping_strips_whitespace_url():
    with patch.dict("os.environ", {"HEALTHCHECK_URL": "  https://hc-ping.com/abc  "}), \
         patch("heartbeat.requests.get") as mget:
        heartbeat.ping()
    mget.assert_called_once_with("https://hc-ping.com/abc", timeout=5)


def test_ping_swallows_request_exception():
    with patch.dict("os.environ", {"HEALTHCHECK_URL": "https://hc-ping.com/abc"}), \
         patch("heartbeat.requests.get", side_effect=requests.RequestException("boom")):
        heartbeat.ping()   # 예외가 전파되면 안 됨
