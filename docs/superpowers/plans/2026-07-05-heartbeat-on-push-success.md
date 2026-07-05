# heartbeat를 publish 성공 기준으로 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** heartbeat 핑을 "main 실행"이 아니라 "git push 성공(또는 올릴 것 없음)" 시점으로 옮겨 publish 마비를 ~20분 내 감지하고, run.sh를 레포로 편입한다.

**Architecture:** `run.sh`(레포 신규)가 `curl`로 healthchecks에 핑한다 — push 성공/무변경 시 성공 핑, push 실패 시 `/fail` 핑, main 크래시는 `set -e` 중단으로 핑 부재→경고. `main.py`의 heartbeat 래퍼와 `heartbeat.py`(+테스트)는 삭제한다.

**Tech Stack:** bash(run.sh, curl), Python 3.9+, pytest. 신규 의존성 없음.

설계 스펙: `docs/superpowers/specs/2026-07-05-heartbeat-on-push-success-design.md`

## Global Constraints

- 핑은 `run.sh`에서 `curl -fsS -m 5` 로, `HEALTHCHECK_URL` 미설정 시 no-op, 비차단(`|| true`).
- 단일 진실원천 = git push 성공. `main.py`는 heartbeat 호출 안 함.
- `run.sh` 경로 `/home/ubuntu/cig-monitor` 하드코딩 유지(VM 전용 스크립트).
- 오늘(07-05) 적용한 `git add articles.json archive.json` fix를 레포 run.sh에 포함.

## File Structure

| 파일 | 변경 |
|------|------|
| `run.sh` (신규, 레포 편입) | heartbeat 핑(push 성공/실패/무변경) + archive.json 커밋 |
| `main.py` (수정) | `run_cli`·`import heartbeat` 제거, `__main__` 원복 |
| `heartbeat.py` (삭제), `tests/test_heartbeat.py` (삭제), `tests/test_main_heartbeat.py` (삭제) | run.sh로 이전 |

---

### Task 1: `run.sh` 레포 편입 (heartbeat 핑 포함)

**Files:**
- Create: `run.sh`

- [ ] **Step 1: `run.sh` 생성** — 아래 내용 그대로:

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

- [ ] **Step 2: 문법 검사**

Run: `bash -n run.sh`
Expected: 출력 없음(문법 OK). 비정상 종료 코드 없으면 통과.

- [ ] **Step 3: 커밋**

```bash
git add run.sh
git commit -m "feat: run.sh 레포 편입 + heartbeat를 push 성공 기준으로(publish 감시)"
```

---

### Task 2: `main.py` heartbeat 제거 + heartbeat 파일/테스트 삭제

**Files:**
- Modify: `main.py`
- Delete: `heartbeat.py`, `tests/test_heartbeat.py`, `tests/test_main_heartbeat.py`

- [ ] **Step 1: `main.py` import에서 heartbeat 제거** — 현재:

```python
from seen_store import load_seen, save_seen

import archive_store
import heartbeat
```

교체:

```python
from seen_store import load_seen, save_seen

import archive_store
```

- [ ] **Step 2: `run_cli` 제거하고 `__main__` 원복** — 현재:

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

교체:

```python
if __name__ == "__main__":
    _fast = "--fast" in sys.argv
    main(skip_email=_fast or "--no-email" in sys.argv, fast=_fast)
```

- [ ] **Step 3: heartbeat 파일·테스트 삭제**

```bash
git rm heartbeat.py tests/test_heartbeat.py tests/test_main_heartbeat.py
```

- [ ] **Step 4: 전체 회귀 + 스모크**

Run: `python3 -m pytest -q`
Expected: 통과, 테스트 수가 heartbeat 9개 감소(238→229). heartbeat 관련 실패/잔존 없음.

Run: `python3 -c "import main; print('import OK')"`
Expected: `import OK` (heartbeat 임포트 에러 없음)

Run: `grep -rn "heartbeat" main.py tests/ || echo "잔존 없음"`
Expected: `잔존 없음`

- [ ] **Step 5: 커밋**

```bash
git add main.py
git commit -m "refactor: main.py heartbeat 제거 — publish 감시는 run.sh가 담당"
```

---

### Task 3: 배포 & 검증

VM의 `run.sh`는 현재 git 미추적 → 레포의 tracked run.sh로 교체해야 한다.

- [ ] **Step 1: 머지·push** — feature 브랜치 → `main` 머지 후 `git pull --rebase origin main && git push`.

- [ ] **Step 2: VM run.sh 교체 (flock)** — 미추적 run.sh 제거 후 tracked 반영:

```bash
ssh -i ~/.ssh/oracle_cig.key ubuntu@140.245.72.164 \
  'cd cig-monitor && flock -w 120 /tmp/cig-monitor.lock bash -c "
    git stash push -- run.sh 2>/dev/null; rm -f run.sh
    git pull --rebase origin main 2>&1 | tail -2
    ls -l run.sh && bash -n run.sh && echo run.sh-syntax-ok
    which curl
  "'
```
Expected: run.sh 존재, `run.sh-syntax-ok`, curl 경로 출력.

- [ ] **Step 3: 핑 정상 확인** — 몇 분 뒤 healthchecks 대시보드가 계속 **초록**(push 성공마다 핑) 유지되는지 확인.

- [ ] **Step 4: 실패 경로 실검증(선택)** — VM에서 `source config.env && curl -fsS "$HEALTHCHECK_URL/fail"` 로 강제 down → 대시보드 빨강 + 메일 수신 확인 → 다음 정상 실행이 성공 핑으로 복구.

---

## Self-Review 결과

- **스펙 커버리지:** run.sh 핑 이동+레포편입(Task 1)·main heartbeat 제거(Task 2)·heartbeat 파일 삭제(Task 2)·VM run.sh 교체+검증(Task 3)·실패경로 검증(Task 3 S4) — 스펙 전 항목 대응.
- **플레이스홀더:** run.sh 전문/명령/기대출력 실제 내용. run.sh는 bash라 단위테스트 대신 `bash -n`+운영 검증(명시).
- **타입 일관성:** `hc_ping()` 정의·호출(`hc_ping ""`, `hc_ping "/fail"`) 일치. main.py `__main__` 원복 블록이 heartbeat 도입 전과 동일(`_fast`/`main(...)`). `import archive_store` 유지(main이 사용), `import heartbeat`만 제거.
- **주의:** VM run.sh 미추적→tracked 전환 시 `git pull`이 "untracked overwrite" 거부하므로 Step 2에서 `rm -f run.sh` 선행. flock으로 cron과 격리.
