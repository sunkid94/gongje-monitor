from unittest.mock import patch

import pytest

import main


def test_run_cli_pings_on_success():
    with patch("main.main") as mmain, \
         patch("main.heartbeat.ping") as mping, \
         patch("main.heartbeat.ping_fail") as mfail:
        main.run_cli(["main.py"])
    mmain.assert_called_once_with(skip_email=False, fast=False)
    mping.assert_called_once()
    mfail.assert_not_called()


def test_run_cli_pings_fail_and_reraises_on_exception():
    with patch("main.main", side_effect=RuntimeError("boom")), \
         patch("main.heartbeat.ping") as mping, \
         patch("main.heartbeat.ping_fail") as mfail:
        with pytest.raises(RuntimeError):
            main.run_cli(["main.py"])
    mfail.assert_called_once()
    mping.assert_not_called()


def test_run_cli_fast_flag_sets_skip_email_and_fast():
    with patch("main.main") as mmain, \
         patch("main.heartbeat.ping"), patch("main.heartbeat.ping_fail"):
        main.run_cli(["main.py", "--fast"])
    mmain.assert_called_once_with(skip_email=True, fast=True)


def test_run_cli_no_email_flag_sets_skip_email_only():
    with patch("main.main") as mmain, \
         patch("main.heartbeat.ping"), patch("main.heartbeat.ping_fail"):
        main.run_cli(["main.py", "--no-email"])
    mmain.assert_called_once_with(skip_email=True, fast=False)
