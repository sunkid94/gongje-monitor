# CIG 이슈 모니터 — 문서 인덱스

기계설비건설공제조합 이슈 모니터(sunkid94/gongje-monitor)의 설계(spec)·구현계획(plan)
문서 지도. 기능 진화 순으로 정리. 각 항목은 `specs/` 설계서와 `plans/` 구현계획 짝.

## 1. 초기 구축
- **뉴스 모니터** — 조합 이슈 수집·메일 보고 뼈대
  - spec: `specs/2026-04-11-news-monitor-design.md`
  - plan: `plans/2026-04-11-news-monitor.md`
- **웹 대시보드** — 이슈 로그 웹사이트(GitHub Pages)
  - spec: `specs/2026-04-12-web-dashboard-design.md`
  - plan: `plans/2026-04-12-web-dashboard.md`
- **AI 요약 + 건설산업 뉴스 확장**
  - spec: `specs/2026-04-18-ai-summary-and-industry-news-design.md`
  - plan: `plans/2026-04-18-ai-summary-and-industry-news.md`

## 2. 임원 공개 개편
- **임원 공개 개편** — 대외 신뢰용 UI·운영 정비
  - spec: `specs/2026-04-23-gongje-monitor-executive-rollout-design.md`
  - plan: `plans/2026-04-23-gongje-monitor-executive-rollout.md`

## 3. 인프라 이전
- **Oracle Cloud 이전** — GitHub Actions cron → Oracle VM(정시성 확보)
  - plan: `plans/2026-05-27-oracle-cloud-cig-monitor-migration.md`

## 4. 푸시 중복제거 (진화)
- **v1 스토리 단위** — `specs/2026-06-04-push-story-dedup-design.md` / `plans/2026-06-04-push-story-dedup.md`
- **v2 조직 별칭 통합·7일 창** — `specs/2026-06-05-push-dedup-v2-org-alias-design.md` / `plans/2026-06-05-push-dedup-v2.md`
- **v3 AI 이벤트 라벨** — `specs/2026-06-08-dedup-v3-event-label-design.md` / `plans/2026-06-08-dedup-v3.md`

## 5. 수집 정확도
- **멀티소스 크롤러** — 네이버 + 구글 + 기계설비신문 RSS
  - spec: `specs/2026-06-07-multi-source-crawler-design.md`
  - plan: `plans/2026-06-07-multi-source-crawler.md`
- **관련도 게이트** — 조합기사 AI 관련도 판정(오탐 필터)
  - spec: `specs/2026-06-08-relevance-gate-design.md` / `plans/2026-06-08-relevance-gate.md`
  - v2(추적 조직 전체·별칭): `specs/2026-06-08-relevance-gate-v2-design.md` / `plans/2026-06-08-relevance-gate-v2.md`

## 6. 운영 개선 (2026-07)
- **커밋 빈도·방식 재설계** — seen.json 추적해제 + 주간 gc(`.git` 5.3G→175M), swap, 히스토리 통합
  - `specs/2026-07-01-cig-monitor-commit-redesign.md`
- **실시간 fast-path** — 직접 RSS만 2분 주기(업계지 ~2분 내). **직접 피드 추가 시 배너 오염 함정** 포함
  - `specs/2026-07-02-cig-monitor-fastpath-realtime.md`

## 관련 메모리(운영 지식)
- `reference_cig_monitor_oom_flock` — OOM/flock/swap/히스토리 통합
- `reference_cig_monitor_deploy` — VM 배포(scp + cron git pull) 워크플로
- `reference_cig_keyword_naming` — 소스 지연·직접 RSS 확대·배너 오염 함정
- `reference_cig_enrich_fallback` — enrich 폴백/본문 페치/관련도 게이트
- `reference_cig_push_subscriptions` — 웹푸시 구독 메커니즘
- `project_cig_monitor_oracle_migration` — 운영 환경(cron 스케줄·SSH)
