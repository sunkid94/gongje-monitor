# heartbeat를 "publish 성공" 기준으로 — 사각지대 보완 설계

**작성일:** 2026-07-05
**상태:** 설계 확정 대기 → 구현 계획(writing-plans)로 전환 예정

## 배경 / 문제

heartbeat 데드맨 스위치가 "main.py 실행 성공" 시점에 핑한다(`main.py` `run_cli`). 그런데 2026-07-05, `run.sh`가 archive.json을 커밋하지 않아 **git push가 28시간 마비**됐는데도 main.py 자체는 정상이라 **핑이 계속 초록** → healthchecks가 경고를 안 보냈다. 대시보드(origin/GitHub Pages)만 07-04에 얼어붙었다.

즉 heartbeat가 **"origin에 성공적으로 올렸는가(publish)"를 감시하지 못하는 사각지대**가 있다. (실시간 웹푸시 알람은 main.py 내부라 정상 동작했음 — 이번 건 대시보드 publish만의 문제였다.)

추가로, 이 버그가 리뷰에 안 잡힌 근본 이유는 **`run.sh`가 레포에 없고 VM 전용·git 미추적**이라 코드 리뷰 대상이 아니었기 때문이다.

## 목표

heartbeat 핑을 "main 실행"이 아니라 **"publish 성공(또는 올릴 것 없음)"** 시점으로 옮겨, push 마비를 ~20분 내 감지한다. 겸사겸사 `run.sh`를 레포로 편입해 재발을 리뷰 가능하게 한다.

## 상세 설계

### 1. 핑 위치를 `main.py` → `run.sh`로 이동

`run.sh`가 `curl`로 직접 healthchecks에 핑한다(파이썬 불필요, config.env의 `HEALTHCHECK_URL` 사용):

| 상황 | 동작 |
|---|---|
| git push 성공 | `curl $HEALTHCHECK_URL` (성공 핑) |
| 올릴 변경 없음(조용한 사이클) | `curl $HEALTHCHECK_URL` (성공 핑 — 건강함) |
| git push 3회 실패 | `curl $HEALTHCHECK_URL/fail` (실패 핑 → 즉시 경고) |
| main.py 크래시 | `set -e`로 run.sh 중단 → 핑 없음 → grace(15분) 후 경고 |
| flock 스킵(이전 실행 중) | 핑 없음 — 실행 중인 인스턴스가 핑함 |

핑 함수(멱등·비차단):

```bash
hc_ping() {
    [ -n "$HEALTHCHECK_URL" ] && curl -fsS -m 5 "${HEALTHCHECK_URL}$1" -o /dev/null 2>/dev/null || true
}
```

push 블록의 성공 지점에 `hc_ping ""`, 실패 지점에 `hc_ping "/fail"`, 변경 없음(else)에 `hc_ping ""`.

### 2. `run.sh`를 레포에 편입

현재 VM 전용·미추적인 `run.sh`(오늘 `git add articles.json archive.json` 수정 포함)를 레포에 커밋한다. 이후 `run.sh` 변경은 git으로 배포·리뷰된다. (경로 `/home/ubuntu/cig-monitor` 하드코딩 — VM 전용 스크립트라 그대로 유지.)

**최종 `run.sh`** (오늘 fix + heartbeat 핑 반영):

```bash
#!/bin/bash
set -e
cd /home/ubuntu/cig-monitor

# 중복 실행 방지 (2026-06-29 OOM 이력)
exec 9>/tmp/cig-monitor.lock
if ! flock -n 9; then
    echo "$(date "+%Y-%m-%d %H:%M:%S") INFO 이전 실행 진행중 — 이번 틱 건너뜀" >> monitor.log
    exit 0
fi

set -a
source ./config.env
set +a

hc_ping() {
    [ -n "$HEALTHCHECK_URL" ] && curl -fsS -m 5 "${HEALTHCHECK_URL}$1" -o /dev/null 2>/dev/null || true
}

./venv/bin/python main.py "$@" >> monitor.log 2>&1

# articles.json/archive.json 변경 있으면 push (seen.json 은 VM 로컬 — git 미추적)
if ! git diff --quiet articles.json 2>/dev/null; then
    git add articles.json archive.json
    git commit -m "chore: 기사 업데이트 $(date "+%Y-%m-%d %H:%M KST")" >> monitor.log 2>&1
    for i in 1 2 3; do
        if git pull --rebase origin main >> monitor.log 2>&1 && \
           git push origin main >> monitor.log 2>&1; then
            echo "$(date "+%Y-%m-%d %H:%M:%S") INFO git push 성공" >> monitor.log
            hc_ping ""
            exit 0
        fi
        sleep 5
    done
    echo "$(date "+%Y-%m-%d %H:%M:%S") ERROR git push 3회 실패" >> monitor.log
    hc_ping "/fail"
    exit 1
else
    hc_ping ""
fi
```

### 3. `main.py`에서 heartbeat 제거

`run_cli` 래퍼와 heartbeat 호출을 제거하고 `__main__`을 원래대로 되돌린다:

```python
if __name__ == "__main__":
    _fast = "--fast" in sys.argv
    main(skip_email=_fast or "--no-email" in sys.argv, fast=_fast)
```

`import heartbeat` 제거. (`import archive_store`는 유지 — main이 여전히 사용.) 단일 진실원천 = run.sh push. "main 성공=초록"이 오해를 낳던 것을 제거.

### 4. `heartbeat.py` 및 테스트 삭제

`heartbeat.py`, `tests/test_heartbeat.py`, `tests/test_main_heartbeat.py` 삭제(더 이상 사용 안 함 — dead code 제거).

### 5. 검증

- `python3 -m pytest -q` → heartbeat 테스트 9개 제거 후 회귀 없음(229 예상), import 스모크.
- `run.sh` 문법: `bash -n run.sh`.
- 배포 후: healthchecks에 5분 간격 핑 유지(초록) 확인. **실패 경로 실검증**: VM에서 강제로 push 실패를 유발(또는 `curl $HEALTHCHECK_URL/fail`) → 대시보드 down + 메일 수신 확인 → 성공 핑으로 복구.
- `curl` 존재 확인(`which curl` — Ubuntu 기본 포함).

## 파일 영향

| 파일 | 변경 |
|------|------|
| `run.sh` (신규, 레포 편입) | heartbeat 핑(push 성공/실패/무변경) + 오늘 archive.json 커밋 fix |
| `main.py` (수정) | `run_cli`·`import heartbeat` 제거, `__main__` 원복 |
| `heartbeat.py` (삭제) | run.sh로 이전 |
| `tests/test_heartbeat.py`, `tests/test_main_heartbeat.py` (삭제) | 대상 코드 제거 |

## 배포 & 검증

VM의 `run.sh`는 현재 미추적 상태 → 레포의 tracked `run.sh`로 교체 필요:
- VM에서 flock 잡고: 미추적 `run.sh` 제거 → `git pull`(tracked run.sh 반영) → `bash -n run.sh`.
- 이후 정상 cron이 push 성공 시 핑 → healthchecks 초록 유지 확인.

## 미해결 / 배포 때 결정

- main.py 크래시 시 즉시 `/fail`을 원하면 `trap 'hc_ping "/fail"' ERR` 추가 가능(이번엔 미포함 — 크래시는 핑 부재로 grace 후 감지).
- HEALTHCHECK_URL 은 이미 config.env 에 존재(heartbeat 도입 때).
