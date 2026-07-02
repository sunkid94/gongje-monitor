# CIG 이슈 모니터 — Oracle Cloud 이전 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로컬 맥 cron을 Oracle Cloud Always Free VM의 cron으로 이전하여, 매시 17분 정확한 시각에 누락 없이 CIG 이슈 메일·푸시가 발송되도록 한다.

**Architecture:** Oracle Cloud Always Free 티어의 Ubuntu 22.04 VM 1대에 기존 파이썬 코드를 그대로 옮기고, 시스템 cron으로 `17 * * * *` 스케줄을 등록한다. 누락 감지는 Healthchecks.io 무료 플랜의 핑 모니터링으로 처리한다. 맥은 스케줄러 역할에서 완전히 제외된다.

**Tech Stack:** Oracle Cloud Infrastructure (Always Free 티어), Ubuntu 22.04 ARM (VM.Standard.A1.Flex) 또는 AMD (VM.Standard.E2.1.Micro), Python 3.10+, 시스템 cron, Healthchecks.io

**용어 표기 규칙:**
- 🧑 = 사용자 본인이 직접 수행 (Oracle 콘솔, 카드, 휴대폰 인증 등)
- 🤖 = Claude가 SSH·코드 편집으로 수행
- 🤝 = 함께 (Claude가 명령 알려주고 사용자가 결과 알려줌)

---

## 사전 준비

- 신용카드 (Oracle 본인 확인용. 자동 과금 없음)
- 휴대폰 (SMS 인증)
- 약 90분 시간 (Oracle 가입 30분 + 셋업 60분)

---

## Phase 1: Oracle Cloud 계정 & VM 생성 🧑

### Task 1: Oracle Cloud Free Tier 가입

**소요:** ~20분

- [ ] **Step 1: 가입 페이지 접속**

브라우저에서 https://signup.cloud.oracle.com/ 접속 → "Sign up" 클릭

- [ ] **Step 2: 계정 정보 입력**

- Country/Territory: **South Korea**
- Name: 본인 영문명
- Email: 본인 메일 (회사 메일 권장)

이메일로 온 인증 링크 클릭.

- [ ] **Step 3: 계정 세부 정보**

- Password: 강한 비밀번호 (대소문자·숫자·기호 포함 12자 이상)
- Cloud Account Name: **cig-monitor** (전역 고유. 이미 있으면 `cig-monitor-2wodms`)
- Home Region: **South Korea Central (Chuncheon)** ← 한국 시각 처리에 유리

- [ ] **Step 4: 주소·휴대폰 인증**

주소 입력 후 휴대폰 SMS 코드 인증.

- [ ] **Step 5: 카드 인증**

신용카드 정보 입력. **$1 임시 승인 후 자동 환불**됨. Always Free 한도 안에서만 쓰면 절대 청구되지 않음.

- [ ] **Step 6: 가입 완료 확인**

10~30분 후 "Your account is ready" 이메일 도착 → Oracle Cloud 콘솔(https://cloud.oracle.com) 로그인 확인.

**검증:** 콘솔 홈 화면 진입 시 "Sign in to Oracle Cloud" 페이지에서 본인 Cloud Account Name + 사용자 ID로 로그인 가능.

---

### Task 2: VM 인스턴스 생성

**소요:** ~15분

- [ ] **Step 1: Compute Instance 생성 화면으로**

콘솔 좌상단 햄버거 메뉴 → **Compute → Instances → Create Instance**

- [ ] **Step 2: 인스턴스 기본 설정**

- Name: `cig-monitor`
- Compartment: 기본값
- Placement → Availability domain: 기본값 (1개만 표시되면 그대로)

- [ ] **Step 3: 이미지 선택**

"Image and shape" 섹션 → "Edit" → "Change image" → **Ubuntu** 선택 → 버전 **Canonical Ubuntu 22.04** 선택 → "Select image"

- [ ] **Step 4: Shape 선택 (Always Free 필수)**

"Change shape" 클릭 →

**1차 시도:** Ampere → `VM.Standard.A1.Flex` 선택 → OCPU 1, Memory 6 GB로 설정 (Always Free 한도)

→ "Always Free Eligible" 라벨이 보여야 함.

> ⚠️ A1.Flex가 "Out of capacity" 에러로 실패하면 **2차 시도**:
> Specialty and previous generation → `VM.Standard.E2.1.Micro` 선택 (사양 작지만 Always Free, 거의 항상 가용)

- [ ] **Step 5: 네트워킹**

- "Primary VNIC information": 기본값 그대로 (새 VCN 자동 생성)
- "Assign a public IPv4 address" 체크되어 있는지 확인

- [ ] **Step 6: SSH 키**

"Add SSH keys" → **Generate a key pair for me** 선택 →

- **"Save private key"** 클릭 → 다운로드 파일을 `~/.ssh/oracle_cig.key`로 저장
- **"Save public key"** 클릭 → 백업용으로 같은 폴더에 저장

> ⚠️ 이 private key는 **단 한 번만** 다운로드 가능. 잃어버리면 VM 새로 만들어야 함.

- [ ] **Step 7: 부트 볼륨**

기본값 (50 GB). Always Free 한도 안.

- [ ] **Step 8: Create 클릭**

5~10분 대기 → 상태가 **"Running"** (녹색)으로 변하면 완료.

- [ ] **Step 9: Public IP 확인**

인스턴스 상세 화면에서 **"Public IPv4 Address"** 복사해서 메모해두기. 예: `152.67.123.45`

**검증:** 인스턴스 상태 = Running, Public IP 할당됨.

---

### Task 3: SSH 포트(22) 열기

Oracle은 기본적으로 22번 포트가 닫혀 있지 않지만, 보안 리스트에 명시적으로 허용해야 함.

- [ ] **Step 1: 보안 리스트 진입**

인스턴스 상세 → "Primary VNIC" 섹션 → "Subnet" 링크 → "Security Lists" → "Default Security List ..."

- [ ] **Step 2: Ingress Rule 확인**

다음 규칙이 있는지 확인:
- Source CIDR: `0.0.0.0/0`
- Destination Port Range: `22`
- Protocol: TCP

없으면 "Add Ingress Rules"로 위 내용 추가.

**검증:** 22번 포트 Ingress Rule 존재.

---

## Phase 2: SSH 접속 & 서버 기본 셋업

### Task 4: SSH 접속 테스트 🤝

- [ ] **Step 1: 키 파일 권한 설정** (사용자 맥에서)

```bash
chmod 600 ~/.ssh/oracle_cig.key
```

- [ ] **Step 2: 첫 SSH 접속**

```bash
ssh -i ~/.ssh/oracle_cig.key ubuntu@<PUBLIC_IP>
```

`<PUBLIC_IP>`는 Task 2 Step 9에서 메모한 IP.

처음 접속 시 `yes` 입력하여 known_hosts 등록.

**검증:** 프롬프트가 `ubuntu@cig-monitor:~$` 형태로 바뀜.

---

### Task 5: 서버 기본 패키지 설치 🤖

- [ ] **Step 1: 시스템 업데이트**

```bash
sudo apt update && sudo apt upgrade -y
```

- [ ] **Step 2: 필요 패키지 설치**

```bash
sudo apt install -y python3 python3-pip python3-venv git ca-certificates curl
```

- [ ] **Step 3: 시간대를 한국 시각으로**

```bash
sudo timedatectl set-timezone Asia/Seoul
timedatectl
```

**검증:** `timedatectl` 출력에 `Time zone: Asia/Seoul (KST, +0900)` 표시. cron은 시스템 시각 기준이므로 이걸 안 하면 17분이 한국 17분이 아니게 됨.

---

## Phase 3: 코드 배포 & 환경 변수

### Task 6: 코드 업로드 🤖

레포가 GitHub에 공개되어 있지 않을 수도 있으므로 `scp`로 직접 업로드한다. (사용자가 명령은 맥 터미널에서 실행)

- [ ] **Step 1: 작업 디렉토리 생성** (서버에서)

```bash
mkdir -p ~/cig-monitor && cd ~/cig-monitor
```

- [ ] **Step 2: 코드 파일 업로드** (사용자 맥 터미널에서)

```bash
cd /Users/2wodms/workspace/claude-introduction
scp -i ~/.ssh/oracle_cig.key \
    main.py crawler.py enrich.py mailer.py notifier.py \
    article_store.py seen_store.py config.py backfill_pubdate.py \
    config.env articles.json seen.json subscriptions.json \
    ubuntu@<PUBLIC_IP>:~/cig-monitor/
```

> seen.json, subscriptions.json이 없으면 그 파일만 빼고 업로드.

- [ ] **Step 3: 업로드 확인** (서버에서)

```bash
cd ~/cig-monitor && ls -la
```

**검증:** `main.py`, `config.env`, `articles.json`, `seen.json`(있는 경우), `subscriptions.json`(있는 경우) 모두 존재.

---

### Task 7: 파이썬 가상환경 & 의존성 🤖

- [ ] **Step 1: requirements.txt 생성** (서버에서)

```bash
cd ~/cig-monitor
cat > requirements.txt << 'EOF'
anthropic
requests
feedparser
beautifulsoup4
pywebpush
python-dotenv
EOF
```

> 실제 `import` 문 점검 후 부족한 라이브러리는 추가. 현재 코드 기준 위 6개로 충분.

- [ ] **Step 2: venv 생성 및 의존성 설치**

```bash
cd ~/cig-monitor
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

- [ ] **Step 3: 설치 확인**

```bash
venv/bin/python -c "import anthropic, requests, feedparser, bs4, pywebpush; print('OK')"
```

**검증:** "OK" 출력.

---

### Task 8: 환경 변수 점검 🤝

- [ ] **Step 1: config.env 내용 확인** (서버에서)

```bash
cat ~/cig-monitor/config.env
```

- [ ] **Step 2: 필요 변수 모두 존재 확인**

다음 키가 모두 있어야 함:
- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `RECIPIENTS`
- `ANTHROPIC_API_KEY`
- `VAPID_PRIVATE_KEY` (푸시 발송 시)
- `WEBPUSH_SUBSCRIPTIONS` (또는 subscriptions.json 파일)

없는 게 있으면 사용자가 맥 `config.env`에서 복사해서 추가. (만약 맥 config.env가 불완전하면 사용자가 누락분 채워야 함)

- [ ] **Step 3: 파일 권한 제한**

```bash
chmod 600 ~/cig-monitor/config.env
```

**검증:** API 키들이 모두 채워져 있고, 파일 권한 `-rw-------`.

---

## Phase 4: Healthchecks.io 누락 감지 추가

### Task 9: Healthchecks.io 체크 생성 🧑

**소요:** ~5분

- [ ] **Step 1: 가입**

https://healthchecks.io/ → "Sign Up" → 이메일·비밀번호.

- [ ] **Step 2: 체크 생성**

대시보드 → "Add Check" →
- Name: `CIG 이슈 모니터`
- Schedule: "Simple" → **Period: 1 hour**, **Grace Time: 15 minutes**
- (Grace 15분이면 17분에 안 돌고 32분이 지나도 안 오면 경보)

- [ ] **Step 3: 핑 URL 복사**

체크 상세 화면의 핑 URL (예: `https://hc-ping.com/abc-123-def`) 복사해서 알려주기.

- [ ] **Step 4: 알림 채널 설정**

"Integrations" → "Email" → 본인 메일 등록 (이미 가입 시 메일과 동일).

> 선택: SMS·Slack·Telegram 같은 채널도 추가 가능. 임원 보고용이면 SMS 통합 추천하지만 유료. 일단 이메일로 시작.

**검증:** Healthchecks 체크 상태가 "New" (회색)로 표시되고 핑 URL 받음.

---

### Task 10: main.py에 핑 호출 추가 🤖

**Files:**
- Modify: `~/cig-monitor/main.py` (끝에 추가)
- Modify: `~/cig-monitor/config.env` (HEALTHCHECK_URL 추가)

- [ ] **Step 1: config.env에 핑 URL 추가** (서버에서)

```bash
echo "HEALTHCHECK_URL=https://hc-ping.com/<RECEIVED_UUID>" >> ~/cig-monitor/config.env
```

`<RECEIVED_UUID>` 부분은 Task 9 Step 3에서 받은 URL.

- [ ] **Step 2: main.py 수정**

`main.py`를 다음과 같이 수정 (전체 교체):

```python
import logging
import os

import requests

from article_store import add_articles
from crawler import fetch_new_articles
from enrich import enrich_articles
from mailer import send_email
from notifier import send_company_push
from seen_store import load_seen, save_seen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def _ping_healthcheck(suffix: str = "") -> None:
    url = (os.environ.get("HEALTHCHECK_URL") or "").strip()
    if not url:
        return
    try:
        requests.get(url + suffix, timeout=5)
    except requests.RequestException as e:
        logger.warning("Healthcheck 핑 실패: %s", e)


def main() -> None:
    _ping_healthcheck("/start")
    try:
        seen = load_seen()
        new_articles = fetch_new_articles(seen)

        if not new_articles:
            logger.info("새 기사 없음. 이메일 미발송.")
            _ping_healthcheck()
            return

        logger.info("새 기사 %d건 발견. enrich 중...", len(new_articles))
        enriched = enrich_articles(new_articles)

        new_urls = {a["link"] for a in enriched}
        send_email(enriched)
        save_seen(seen | new_urls)
        add_articles(enriched)
        send_company_push(enriched)
        logger.info("%d건 이슈 이메일 발송 완료.", len(enriched))
        _ping_healthcheck()
    except Exception:
        logger.exception("main 실행 중 예외")
        _ping_healthcheck("/fail")
        raise


if __name__ == "__main__":
    main()
```

> 변경 요지: 시작 시 `/start` 핑, 정상 종료 시 빈 핑(성공), 예외 시 `/fail` 핑. Healthchecks가 "실행 시작/실패"까지 구분해서 표시함.

**검증:** `cat ~/cig-monitor/main.py`로 위 내용 확인.

---

## Phase 5: 수동 1회 테스트 실행

### Task 11: 1회 실행 & 발송 확인 🤖

- [ ] **Step 1: 수동 실행** (서버에서)

```bash
cd ~/cig-monitor
source venv/bin/activate
python main.py
```

- [ ] **Step 2: 본인 메일함 확인** (사용자)

수신함에서 "[CIG] ..." 제목의 메일 도착 확인. (새 기사가 없으면 메일은 안 오지만 로그에 "새 기사 없음" 표시되어야 함)

- [ ] **Step 3: Healthchecks 대시보드 확인** (사용자)

해당 체크의 상태가 **"Up"** (녹색)으로 바뀌고, "Last Ping: a few seconds ago" 표시.

**검증:** 메일 도착 OR "새 기사 없음" 로그 + Healthchecks "Up" 상태.

> ❌ 실패하면: 로그에서 에러 메시지 확인. 흔한 원인 — `ANTHROPIC_API_KEY` 누락, `GMAIL_APP_PASSWORD` 오타, `subscriptions.json` 미존재(이건 푸시만 건너뜀, 메일은 발송됨).

---

## Phase 6: cron 등록

### Task 12: 시스템 cron 등록 🤖

- [ ] **Step 1: 실행 스크립트 작성** (서버에서)

```bash
cat > ~/cig-monitor/run.sh << 'EOF'
#!/bin/bash
set -e
cd /home/ubuntu/cig-monitor
set -a
source ./config.env
set +a
./venv/bin/python main.py >> /home/ubuntu/cig-monitor/monitor.log 2>&1
EOF
chmod +x ~/cig-monitor/run.sh
```

- [ ] **Step 2: 스크립트 단독 테스트**

```bash
~/cig-monitor/run.sh && echo "스크립트 정상 종료"
tail -20 ~/cig-monitor/monitor.log
```

- [ ] **Step 3: crontab 등록**

```bash
(crontab -l 2>/dev/null; echo "17 * * * * /home/ubuntu/cig-monitor/run.sh") | crontab -
crontab -l
```

**검증:** `crontab -l` 출력에 `17 * * * * /home/ubuntu/cig-monitor/run.sh` 한 줄.

---

### Task 13: 다음 17분 발사 관측 🤝

- [ ] **Step 1: 다음 17분까지 대기**

현재 시각이 예를 들어 14:32라면 15:17까지 대기.

- [ ] **Step 2: 발사 시각에 로그 tail** (서버에서)

```bash
tail -f ~/cig-monitor/monitor.log
```

15:17:00 시점에 새 INFO 라인이 흘러나와야 함.

- [ ] **Step 3: 본인 메일·Healthchecks 확인**

- 새 기사 있으면 메일 도착
- Healthchecks 마지막 핑 시각이 방금 시간으로 갱신

**검증:** 17분 정각에 실행 + Healthchecks "Up" 갱신.

---

## Phase 7: 관측 & 맥 cron 제거

### Task 14: 48시간 관측

- [ ] **Step 1: 48시간 동안 매시 17분 발사 확인**

랜덤한 시각 6~10회 정도 메일함·Healthchecks 상태 점검. 시간 기록표:

| 시각 | 메일 도착 | Healthchecks Up |
|---|---|---|
| Day 1 09:17 | ☐ | ☐ |
| Day 1 14:17 | ☐ | ☐ |
| Day 1 22:17 | ☐ | ☐ |
| Day 2 03:17 | ☐ | ☐ |
| Day 2 12:17 | ☐ | ☐ |

- [ ] **Step 2: 누락 확인**

Healthchecks 대시보드의 "Events" 탭에서 누락 이벤트 0건 확인.

**검증:** 48시간 동안 누락 0건.

---

### Task 15: 기존 맥 cron 제거 🤝

48시간 관측 통과 후 진행.

- [ ] **Step 1: 맥 crontab 백업** (사용자 맥에서)

```bash
crontab -l > ~/crontab-backup-$(date +%Y%m%d).txt
cat ~/crontab-backup-*.txt
```

- [ ] **Step 2: 맥 cron에서 monitor 줄만 제거**

```bash
crontab -l | grep -v "claude-introduction/main.py" | crontab -
crontab -l
```

**검증:** `crontab -l` 출력에 `claude-introduction/main.py` 라인 없음.

- [ ] **Step 3: 맥의 monitor.log 보관**

```bash
mv /Users/2wodms/workspace/claude-introduction/monitor.log \
   /Users/2wodms/workspace/claude-introduction/monitor.log.archive-$(date +%Y%m%d)
```

**검증:** 더 이상 맥에서는 새 로그가 추가되지 않음. Oracle 서버에서만 발생.

---

## 완료 기준

- [ ] Oracle VM에서 매시 17분에 안정적으로 cron 발사
- [ ] Healthchecks.io "Up" 상태 유지
- [ ] 누락 발생 시 본인 메일로 즉시 경보
- [ ] 맥에서는 더 이상 모니터링 cron 실행되지 않음
- [ ] 48시간 무사고 관측 완료

---

## 부록: 트러블슈팅

**Oracle A1.Flex가 "Out of capacity"로 계속 실패:**
A1은 인기 많아서 자주 품절. E2.1.Micro로 폴백하거나, 다른 시각에 재시도 (한국 기준 새벽 시간대 성공률 높음).

**SSH 접속 거부:**
1. 보안 리스트의 22번 포트 Ingress 확인
2. 키 파일 권한 600 확인
3. 사용자명 `ubuntu` 확인 (`opc`가 아님 — A1.Flex의 경우 `ubuntu`)

**cron이 17분에 안 도는데 수동 실행은 됨:**
1. `timedatectl`로 시간대 확인 (UTC면 17분이 한국 시각 02:17이 됨)
2. cron 데몬 동작 확인: `systemctl status cron`
3. cron 로그: `grep CRON /var/log/syslog | tail`

**Healthchecks가 계속 "Down":**
1. 핑 URL이 config.env에 정확히 등록됐는지
2. 서버에서 외부 HTTPS 가능한지: `curl -v https://hc-ping.com/`
3. 보안 리스트의 Egress (보통 기본값 all-allow)

**메일 발송 실패 (Gmail SMTP):**
1. Gmail 앱 비밀번호 (16자) 사용 중인지 — 일반 비밀번호로는 거부됨
2. Google 계정에 2단계 인증 활성화 + 앱 비밀번호 생성 필요

---
> 📑 관련 문서 전체 지도: [CIG 이슈 모니터 문서 인덱스](../CIG-MONITOR-INDEX.md)
