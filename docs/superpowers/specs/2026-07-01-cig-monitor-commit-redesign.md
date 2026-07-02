# CIG 모니터 커밋 빈도·방식 재설계

- 날짜: 2026-07-01
- 대상: sunkid94/gongje-monitor (Oracle VM `~/cig-monitor`, 140.245.72.164)
- 상태: 구현·검증 완료

## 배경 / 문제

CIG 이슈 모니터는 Oracle Always Free VM(메모리 954MB, swap 0)에서 cron으로 돈다:
매시 17분 풀모드 + 5분 간격 푸시모드(`run.sh --no-email`). 각 실행이 끝나면
변경된 데이터를 GitHub `main`에 커밋·푸시하고, GitHub Pages가 `main` 루트에서
`index.html`+`articles.json`을 그대로 서빙한다.

두 가지 문제가 겹쳐 터졌다:

1. **cron 실행 중첩 → OOM.** 복구 후 대량 백로그(1,023건)+신규 키워드로 한 실행이
   5분을 초과하자, 다음 5분 cron이 이전 실행이 끝나기 전에 시작 → run.sh/main.py가
   중첩 → 메모리 고갈 → OOM killer가 `git`(pack-objects)을 SIGKILL → push 실패
   (`pack-objects died of signal 9`). run.sh에 중복 실행 방지 장치가 없었음.
2. **`.git` 비대 = 5.3GB.** 5,737개의 "기사 업데이트" 커밋이 누적된 결과.

## 근본 원인 분석 (증거 기반)

- **평상시 churn은 작다.** 5분 간격 연속 커밋 간 `articles.json` diff는 32,105줄 중
  약 60줄(신규 기사 몇 건 추가 + 오래된 것 몇 건 교체)뿐. "1만 줄 변경"은
  따라잡기·백필 같은 **일회성 전체 재작성** 이벤트에서만 발생.
- **진짜 낭비는 `seen.json` + gc 부재.** 매 커밋이 `articles.json`(2.6MB)과
  **`seen.json`(5.7MB)** 을 함께 새로 쓴다. seen.json은 모니터의 "이미 본 링크"
  내부 dedup 상태일 뿐 **웹사이트는 읽지 않는다**(index.html은 articles.json·
  weekly.json만 fetch). VM에만 있으면 되는데 5분마다 GitHub로 푸시되고 있었다.
- repo가 장기간 `git gc` 없이 방치돼 팩이 최적 압축되지 않았다.

## 제약

- GitHub Pages가 `main` 루트에서 직접 서빙 → `articles.json`은 `main`에 있어야 함.
- **로컬 클론(맥북)에서 `git pull`이 계속 깨끗해야 함** → `main`에 routine force-push
  불가(force-push는 매번 로컬 재동기화를 강요).

## 검토한 방식

| | 방식 | 판정 |
|---|---|---|
| **A** | 커밋 대상 정리(seen.json 추적 해제) + 주간 gc | **채택** — 최소 변경, pull 안전 |
| B | 변동 데이터를 `gh-pages` 브랜치로 분리(force-amend 단일 커밋) | 기각 — seen.json만 빼면 불필요하게 복잡 |
| C | 현행 유지 + 주간 자동 squash | 기각 — 매주 force-push로 로컬 pull 깨짐 |

## 설계 (Approach A)

force-push 없이, main 이력을 그대로 두고 커밋에 들어가는 것과 유지보수만 손본다.

1. **`seen.json` git 추적 해제**
   - `git rm --cached seen.json` (디스크 파일은 유지) + `.gitignore`에 `seen.json`
   - main에 **일반 커밋**으로 반영 (force-push 아님 → 로컬 pull 안전)
   - VM 모니터는 디스크의 seen.json을 계속 사용(동작 불변)
2. **`run.sh`가 `articles.json`만 커밋**
   - `git add articles.json seen.json` → `git add articles.json`
   - `git diff --quiet` 체크도 articles.json만
3. **중복 실행 방지 (flock)** — OOM 재발 차단
   - run.sh 앞부분에 `exec 9>/tmp/cig-monitor.lock; flock -n 9 || exit 0`
   - 이전 실행이 진행 중이면 이번 cron 틱은 즉시 건너뜀
4. **주간 비파괴 gc cron**
   - `0 4 * * 0 cd ~/cig-monitor && git gc --prune=now >> gc.log 2>&1`
   - 팩을 항상 delta-압축 상태로 유지, dangling 회수. 히스토리 재작성 없음.

### 선행 일회성 조치 (재설계의 전제)

- **swap 4GB 추가**(`/swapfile`, fstab 영구, `vm.swappiness=10`) → OOM 내성 확보
  (available 메모리 76MB→528MB).
- **히스토리 1회 통합**: `git commit-tree HEAD^{tree}`로 단일 루트 커밋 생성 →
  `update-ref` + force-push + `reflog expire` + `gc --prune=now`. 내용(트리)은
  동일하게 보존. `.git` 5.3GB→171MB. (이 force-push로 로컬 클론은 한 번
  `reset --hard`로 재동기화함. 이후로는 force-push 없음.)

## 구현 위치

- `run.sh` (VM 전용, git 미추적): flock 가드 + `git add articles.json`
- `.gitignore`: `seen.json` 추가
- VM crontab: run.sh 2줄 + 주간 gc 1줄
- `seen.json`: `git rm --cached`로 추적 해제 (커밋 `ef943db`)

## 결과 (검증됨)

- 커밋당 객체 증가: **~8MB → ~180KB (약 50배↓)** — 이후 검증 커밋이
  `articles.json`만 변경함을 실측(`17ac475`).
- `.git`: 5.3GB → **175MB** 정착. 팩 최대 객체는 seen.json(과거)·articles.json뿐
  (엉뚱한 대용량 바이너리 없음).
- flock 동작 확인: 중첩 cron 틱이 "이전 실행 진행중 — 건너뜀"으로 skip.
- swap 사용 관찰됨(OOM 없이 백로그 처리). load 21→0 정상화.
- main은 일반 push만 → 로컬 pull `--ff-only`로 깨끗하게 유지.

## 범위 밖 / 향후

- gh-pages 분리, 커밋 빈도 자체 변경, 상시 히스토리 재작성 — 하지 않음.
- **주의**: `articles.json` 5분 커밋이 다시 장기 누적되면 언젠가 또 커질 수 있음.
  주간 gc가 팩을 압축 유지하지만, 수개월 뒤 재점검 가치.
- (별건) 전문지 RSS 본문 폴백 분류·실시간 fast-path 는 별도 개선으로 같은 시기 반영됨 —
  커밋 재설계와는 무관. `[[reference_cig_keyword_naming]]` 참고. 직접 RSS 피드 추가 시
  **배너 오염 함정**(전 페이지 조합 배너로 본문폴백 오분류)은
  `docs/superpowers/specs/2026-07-02-cig-monitor-fastpath-realtime.md` 의
  "직접 피드 추가 시 함정 — 배너 오염" 섹션 참고.

## 관련 문서 / 메모리

- `docs/superpowers/CIG-MONITOR-INDEX.md` — CIG 모니터 전체 문서 인덱스(허브)
- `docs/superpowers/specs/2026-07-02-cig-monitor-fastpath-realtime.md` — 실시간 fast-path + **배너 오염 함정**
- `reference_cig_monitor_oom_flock` — OOM/flock/swap/히스토리 통합 상세
- `reference_cig_monitor_deploy` — VM 배포(scp + cron git pull) 워크플로
- `project_cig_monitor_oracle_migration` — 운영 환경(cron 스케줄, SSH)
