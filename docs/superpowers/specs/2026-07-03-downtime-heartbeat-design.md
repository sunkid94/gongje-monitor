# 다운타임 하드닝 — 데드맨 스위치(heartbeat) 설계

**작성일:** 2026-07-03
**상태:** 설계 확정 대기 → 구현 계획(writing-plans)로 전환 예정

## 배경 / 문제

CIG 이슈 모니터의 알람 지연을 실측(`articles.json`, is_company 605건)한 결과:

- 정상 상태 지연 중앙값 **6분**, 1시간 내 **83%** — 살아있을 때 5분 RSS 경로는 잘 작동.
- 지연 3시간 초과 81건 중 **29건이 `2026-06-08T00:17` 단일 시각에 일괄 수집** = 모니터가
  ~14시간 멈춰 있다가 복구되며 쌓인 걸 한 번에 처리한 신호(당시 enrich API 크레딧 소진).

즉 체감 "늦은 알람"의 최대 원인은 **매체/피드 문제가 아니라 다운타임**이다. 그런데:

- **06-08의 직접 원인(enrich 크레딧)은 이미 방어됨** — `enrich_article`이 API 실패 시 크래시
  없이 원문 폴백(`enrich.py:128-133`)하고, 폴백률 50% 초과 시 자동 메일 경고(`_send_enrich_alert`).
- **하지만 생존감시(heartbeat/watchdog)가 전무하다.** enrich 경고는 "런이 실제로 돌아 enrich까지
  도달했을 때"만 울린다. **런 자체가 안 도는 경우**(cron 정지, OOM 프로세스 피살, VM 다운, git 락,
  디스크 풀)엔 아무 경고 없이 침묵한다. `run.sh`·cron은 레포에 없고 VM에만 존재.

## 목표

**"모니터가 일정 시간 한 사이클도 성공적으로 완료하지 못하면 운영자에게 알린다"** 는 데드맨 스위치를
붙여, 침묵 다운타임을 "수 시간 뒤 우연히 발견"에서 "~20분 내 자동 통지"로 바꾼다. 이 장치는 특정
원인(크레딧/OOM/…)에 묶이지 않고 **모든 stall 원인(미래의 미지 원인 포함)** 을 포괄한다.

### 비목표 (이번 스코프 아님)

- 개별 stall 원인 예방(OOM 방어, swap, repo 비대, 크레딧 잔액 사전점검) — 후속 작업.
- 풀런(구글·네이버) 전용 실패 감지 — 이번엔 "프로세스 생존" 한 체크만.
- 커버리지 개선(배너-폴백 끄기, 신규 피드) — 별개 문제(지연 아님).

## 접근 — 외부 데드맨 스위치(healthchecks.io)

감시자는 감시 대상과 운명을 같이하면 안 된다. VM 내부 워치독은 VM 통째 다운·cron 데몬 사망을
못 잡으므로, **VM 밖 외부 서비스**가 핑을 받고 알림한다.

- 모니터는 **매 성공 사이클마다** 외부 서비스에 "살아있음" 핑을 쏜다(아웃바운드 HTTPS만; 인바운드
  노출 없음).
- 핑이 설정된 시간(주기+grace) 넘게 끊기면 **healthchecks.io가** 운영자에게 메일 알림.
- 알림 로직·스케줄 판정을 외부가 담당 → 우리 코드는 핑 한 줄.

## 상세 설계

### 1. 핑 시점 — `main.py` `__main__` 래퍼

`main()`은 "새 기사 없음"일 때도 정상 return(`main.py:23`)한다. 따라서 조용한 뉴스 시간대도
성공으로 간주해 핑이 나가야 오탐(조용함→다운 착각)이 없다. 개별 return 지점에 흩뿌리지 않고 호출부를
감싼다:

```python
if __name__ == "__main__":
    _fast = "--fast" in sys.argv
    try:
        main(skip_email=_fast or "--no-email" in sys.argv, fast=_fast)
    except Exception:
        heartbeat.ping_fail()   # 크래시 → 즉시 실패 신호(grace 대기 없이 알림)
        raise
    else:
        heartbeat.ping()        # 정상 완료(새 기사 유무 무관) → 살아있음
```

- fast(5분)·full(매시) **둘 다 같은 체크로** 핑 → "프로세스/cron/VM 생존"을 5분 해상도로 감시.
- `except`에서 `raise`를 유지해 기존 종료코드·로그 동작 불변.

### 2. 신규 모듈 `heartbeat.py`

```python
import logging
import os
import requests

logger = logging.getLogger(__name__)
_TIMEOUT = 5


def _ping(suffix: str = "") -> None:
    url = (os.environ.get("HEALTHCHECK_URL") or "").strip()
    if not url:
        return                       # 미설정 → no-op (로컬/테스트/CI)
    try:
        requests.get(url + suffix, timeout=_TIMEOUT)
    except requests.RequestException as e:
        logger.warning("heartbeat 핑 실패(%s): %s", suffix or "success", e)


def ping() -> None:
    _ping("")


def ping_fail() -> None:
    _ping("/fail")
```

- `HEALTHCHECK_URL` 미설정 시 no-op → 로컬 실행/테스트/GH CI에서 핑 안 감.
- **모든 요청 예외를 삼킴** — healthchecks 지연·다운이 모니터 본체를 지연/중단시키지 않음. 실패는 로그만.
- `requests`는 이미 의존성(`requirements.txt`)에 존재 — 신규 의존성 없음.

### 3. 설정 / 배포

- **VM `config.env`에 한 줄 추가:** `HEALTHCHECK_URL=https://hc-ping.com/<uuid>`
- **`run.sh`·crontab 무변경** — 핑이 `main.py` 내부라 VM 실행 구조를 안 건드림.
- `config.env`는 `config.py`의 `load_dotenv`로 로드되고, `main.py`가 config를 임포트하므로
  `heartbeat._ping` 호출 시점엔 `os.environ`에 값이 채워져 있음.

### 4. healthchecks.io 웹 설정 (구현 후, 운영자와 화면 공유하며)

- 체크 1개 생성(예: "CIG monitor").
- **주기(period) 5분 / grace 15분 (기본값)** → 약 20분 침묵 시 알림.
  실제 VM fast cron 간격은 배포 검증 때 확인해 조정.
- 알림 채널: 우선 이메일. (필요 시 SMS/Slack 등 추가)
- 생성된 핑 URL을 VM `config.env`의 `HEALTHCHECK_URL`에 기입.

### 5. 테스트 (TDD)

`tests/test_heartbeat.py`:

- `HEALTHCHECK_URL` 설정 시 `ping()` → `requests.get(url, timeout=5)` 호출.
- `ping_fail()` → `requests.get(url + "/fail", ...)` 호출.
- `HEALTHCHECK_URL` 미설정 시 → `requests.get` 미호출(no-op).
- `requests.get`이 `RequestException` 던져도 → 예외 전파 안 함(삼킴).

`main.py` 래퍼 검증(단위):

- `main` 정상 완료 → `heartbeat.ping` 호출, `ping_fail` 미호출.
- `main`이 예외 → `heartbeat.ping_fail` 호출 후 예외 재전파(`ping` 미호출).

### 6. 검증 (배포 후)

1. `main` 머지 → VM cron `git pull`로 코드 반영.
2. VM `config.env`에 `HEALTHCHECK_URL` 기입.
3. healthchecks 대시보드에 5분마다 핑 도착(초록) 확인.
4. healthchecks "테스트 알림" 발송으로 이메일 경로 확인.
5. 실제 VM cron 간격 확인 후 period/grace 조정.

## 파일 영향

| 파일 | 변경 |
|------|------|
| `heartbeat.py` (신규) | `ping()`, `ping_fail()`, 내부 `_ping()` |
| `main.py` (수정) | `__main__` 블록을 try/except/else로 감싸 성공/실패 핑 |
| `tests/test_heartbeat.py` (신규) | heartbeat 단위 테스트 |
| `config.env` (VM, 레포 밖) | `HEALTHCHECK_URL` 추가 |

## 미해결 / 배포 때 결정

- **VM fast cron 실제 간격** — 스펙은 5분/grace15분 기본값. 배포 검증 때 crontab 확인해 healthchecks
  주기·grace 최종 조정.
- 알림 채널 이메일 외 추가 여부(SMS 등) — 운영자 선택, 후속.
