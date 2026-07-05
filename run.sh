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
