# 다운타임 하드닝 — 데드맨 스위치(heartbeat) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 모니터가 한 사이클도 성공 완료하지 못하면 외부 서비스(healthchecks.io)가 ~20분 내 운영자에게 알리도록, 매 성공 사이클에 "살아있음" 핑을 쏘는 데드맨 스위치를 붙인다.

**Architecture:** 얇은 `heartbeat.py`(성공 핑/실패 핑, URL 미설정 시 no-op, 모든 요청 예외 삼킴)를 만들고, `main.py`의 CLI 진입점을 `run_cli()`로 감싸 정상 완료 시 `ping()`, 크래시 시 `ping_fail()` 후 재-raise 한다. 알림 판정·스케줄은 외부 healthchecks.io가 담당하므로 우리 코드는 핑만.

**Tech Stack:** Python 3.10+, `requests==2.32.3`(기존 의존성), `pytest==8.3.4`, `unittest.mock`. 신규 의존성 없음.

설계 스펙: `docs/superpowers/specs/2026-07-03-downtime-heartbeat-design.md`

## Global Constraints

- 신규 의존성 추가 금지 — `requests`는 이미 `requirements.txt`에 존재.
- `HEALTHCHECK_URL` 환경변수 **미설정 시 완전 no-op** — 로컬 실행/테스트/GH CI에서 핑이 나가면 안 됨.
- heartbeat는 **모니터 본체를 절대 지연/중단시키지 않는다** — 모든 `requests` 예외를 삼키고 로그만 남김. 타임아웃 5초.
- 요청 URL·타임아웃 형식 고정: `requests.get(url, timeout=5)` / 실패 핑은 `requests.get(url + "/fail", timeout=5)`.
- 크래시 시 `main.py`의 기존 종료코드·예외 전파 동작을 보존한다(핑 후 `raise`).

## File Structure

| 파일 | 책임 |
|------|------|
| `heartbeat.py` (신규) | 외부 healthcheck 핑 — `ping()`, `ping_fail()`, 내부 `_ping(suffix)` |
| `tests/test_heartbeat.py` (신규) | heartbeat 단위 테스트(호출/누락/예외삼킴) |
| `main.py` (수정) | `import heartbeat` + `run_cli(argv)` 래퍼 + `__main__`이 `run_cli(sys.argv)` 호출 |
| `tests/test_main_heartbeat.py` (신규) | `run_cli` 성공→ping / 예외→ping_fail+재raise / 플래그 전달 검증 |
| `config.env` (VM, 레포 밖) | `HEALTHCHECK_URL` 추가 — 배포 단계 |

---

### Task 1: `heartbeat.py` 모듈

**Files:**
- Create: `heartbeat.py`
- Test: `tests/test_heartbeat.py`

**Interfaces:**
- Consumes: `os.environ["HEALTHCHECK_URL"]`(선택), `requests`.
- Produces: `ping() -> None`, `ping_fail() -> None` — Task 2(`main.py`)가 호출.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_heartbeat.py`:

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_heartbeat.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'heartbeat'`

- [ ] **Step 3: `heartbeat.py` 구현**

```python
import logging
import os

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 5


def _ping(suffix: str = "") -> None:
    """HEALTHCHECK_URL 로 핑. 미설정 시 no-op. 모든 요청 예외는 삼키고 로그만."""
    url = (os.environ.get("HEALTHCHECK_URL") or "").strip()
    if not url:
        return
    try:
        requests.get(url + suffix, timeout=_TIMEOUT)
    except requests.RequestException as e:
        logger.warning("heartbeat 핑 실패(%s): %s", suffix or "success", e)


def ping() -> None:
    """정상 완료 신호."""
    _ping("")


def ping_fail() -> None:
    """실패 신호 — grace 대기 없이 즉시 알림 트리거."""
    _ping("/fail")
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest tests/test_heartbeat.py -v`
Expected: PASS — 5개 모두 통과

- [ ] **Step 5: 커밋**

```bash
git add heartbeat.py tests/test_heartbeat.py
git commit -m "feat: heartbeat 모듈 — 외부 데드맨 스위치 핑(ping/ping_fail)"
```

---

### Task 2: `main.py` CLI 래퍼로 성공/실패 핑

**Files:**
- Modify: `main.py` (파일 끝 `__main__` 블록 — 현재 `main.py:54-56`)
- Test: `tests/test_main_heartbeat.py`

**Interfaces:**
- Consumes: `heartbeat.ping()`, `heartbeat.ping_fail()` (Task 1), 기존 `main(skip_email, fast)`.
- Produces: `run_cli(argv: list) -> None` — `__main__`이 `run_cli(sys.argv)`로 호출.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_main_heartbeat.py`:

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest tests/test_main_heartbeat.py -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'run_cli'`

- [ ] **Step 3: `main.py` 수정** — 상단 import에 heartbeat 추가:

`main.py`의 import 블록(현재 `main.py:4-9`) 맨 아래에 한 줄 추가:

```python
import heartbeat
```

그리고 파일 끝의 현재 블록:

```python
if __name__ == "__main__":
    _fast = "--fast" in sys.argv
    main(skip_email=_fast or "--no-email" in sys.argv, fast=_fast)
```

를 다음으로 교체:

```python
def run_cli(argv: list) -> None:
    """CLI 진입점 — main() 을 감싸 성공/실패 heartbeat 핑을 쏜다.

    성공(새 기사 유무 무관)이면 ping(), 크래시면 ping_fail() 후 재-raise 로
    기존 종료코드·예외 전파 동작을 보존한다.
    """
    fast = "--fast" in argv
    try:
        main(skip_email=fast or "--no-email" in argv, fast=fast)
    except Exception:
        heartbeat.ping_fail()
        raise
    else:
        heartbeat.ping()


if __name__ == "__main__":
    run_cli(sys.argv)
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest tests/test_main_heartbeat.py -v`
Expected: PASS — 4개 모두 통과

- [ ] **Step 5: 전체 회귀 + 임포트 스모크**

Run: `python3 -m pytest -q`
Expected: 전체 통과(신규 9개 포함, 기존 회귀 없음)

Run: `python3 -c "import main, heartbeat; print('import OK')"`
Expected: `import OK`

- [ ] **Step 6: 커밋**

```bash
git add main.py tests/test_main_heartbeat.py
git commit -m "feat: main CLI 진입점을 run_cli 로 감싸 성공/실패 heartbeat 핑"
```

---

## 배포 & 검증 (구현·테스트 완료 후, 운영자와 함께)

코드로 테스트 불가한 외부/VM 단계 — 화면 공유하며 진행(오라클 콘솔 교훈: UI 추측 금지).

- [ ] **healthchecks.io 체크 생성**
  - 무료 계정 → 새 체크 생성(예: "CIG monitor").
  - **Period 5분 / Grace 15분**(기본값) → 약 20분 침묵 시 알림. 실제 VM fast cron 간격 확인 후 조정.
  - 알림 채널: 이메일 우선.
  - 발급된 핑 URL(`https://hc-ping.com/<uuid>`) 확보.

- [ ] **VM `config.env`에 한 줄 추가** (`run.sh`·crontab 무변경):

```
HEALTHCHECK_URL=https://hc-ping.com/<uuid>
```

- [ ] **배포** — `main` 머지 → VM cron `git pull --rebase`로 코드 반영.

- [ ] **핑 도착 확인** — healthchecks 대시보드에 5분마다 핑(초록) 표시되는지 확인.

- [ ] **알림 경로 확인** — healthchecks "Send Test Notification"으로 이메일 수신 확인.

- [ ] **실패 핑 확인(선택)** — VM에서 `curl -fsS "$HEALTHCHECK_URL/fail"` 한 번 → 대시보드가 즉시 down 표시되는지 확인 후 다시 성공 핑으로 복구.

- [ ] **주기 튜닝** — 실제 crontab fast 간격 확인해 period/grace 최종 조정.

---

## Self-Review 결과

- **스펙 커버리지:** 핑 시점(Task 2 `run_cli`)·`heartbeat.py` 모듈(Task 1)·URL 미설정 no-op(Task 1 test)·예외 삼킴(Task 1 test)·config.env 한 줄/cron 무변경(배포 섹션)·healthchecks 웹설정 5분·grace15(배포 섹션)·테스트(Task 1·2)·검증(배포 섹션) — 스펙 전 항목 대응.
- **플레이스홀더:** 코드/테스트/명령 전 단계 실제 내용. `<uuid>`는 healthchecks가 발급하는 실제 값의 자리표시로, 배포 단계에서 확보한다고 명시(의도된 런타임 값).
- **타입 일관성:** `heartbeat.ping()/ping_fail() -> None`을 Task 1이 정의, Task 2가 `main.heartbeat.ping`·`main.heartbeat.ping_fail`로 패치/호출 — 이름 일치. `run_cli(argv: list)` 시그니처가 Task 2 test와 `__main__` 호출부에서 일치. `requests.get(url, timeout=5)` 형식이 구현·테스트 assert에서 일치.
