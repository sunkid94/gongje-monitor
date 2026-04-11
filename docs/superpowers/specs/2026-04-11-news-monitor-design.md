# 공제조합 이슈 모니터링 및 자동 보고 시스템 설계

**작성일:** 2026-04-11  
**작성자:** 홍보담당자 + Claude Code  
**상태:** 승인됨

---

## 개요

4개 공제조합 관련 뉴스를 자동으로 수집하고, Claude AI로 요약 및 중요도를 판단하여 임원에게 이메일로 보고하는 시스템.

**모니터링 대상 조합:**
- 기계설비건설공제조합
- 엔지니어링공제조합
- 건설공제조합
- 전문건설공제조합

---

## 아키텍처

```
┌─────────────────────────────────────────────┐
│              macOS (cron/launchd)            │
│                                             │
│  ┌──────────┐    ┌──────────┐    ┌────────┐ │
│  │  뉴스 수집 │───▶│ 요약/판단 │───▶│ 이메일  │ │
│  │ (crawler)│    │(Claude AI)│   │ 발송   │ │
│  └──────────┘    └──────────┘    └────────┘ │
│        │                              │      │
│  ┌─────▼──────┐              ┌────────▼───┐  │
│  │ seen.json  │              │  Gmail     │  │
│  │(중복 방지)  │              │  SMTP      │  │
│  └────────────┘              └────────────┘  │
└─────────────────────────────────────────────┘
```

---

## 구성 요소

| 파일 | 역할 |
|------|------|
| `main.py` | 전체 흐름 조율, cron 진입점 |
| `crawler.py` | 네이버 뉴스 검색 API로 키워드별 기사 수집 |
| `summarizer.py` | Claude API로 요약 + 긍정/부정/중립 판단 |
| `mailer.py` | Gmail SMTP로 이메일 발송 |
| `seen.json` | 처리된 기사 URL 저장 (중복 방지) |
| `config.env` | API 키 및 이메일 설정 (git 제외) |

---

## 데이터 흐름

1. cron이 `main.py` 실행 (1시간 30분마다)
2. `crawler.py`가 네이버 뉴스 API로 4개 키워드 각각 검색
3. 최근 24시간 이내 기사 중 `seen.json`에 없는 새 기사 필터링
4. 새 기사가 있으면 `summarizer.py`가 Claude API로 각 기사 처리
   - 2~3줄 요약 생성
   - 긍정 / 부정 / 중립 중 하나로 중요도 판단
5. `mailer.py`가 Gmail SMTP로 이메일 발송
6. 처리된 기사 URL을 `seen.json`에 저장
7. 새 기사가 없으면 이메일 발송하지 않음

---

## 이메일 형식

**제목:** `[이슈 알림] 기계설비건설공제조합 외 N건 (YYYY-MM-DD HH:MM)`

**본문 구조 (기사별):**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━
[조합명] ⚠️ 부정 / ✅ 긍정 / ➖ 중립
━━━━━━━━━━━━━━━━━━━━━━━━━━━
제목: 기사 제목
링크: https://...
요약: 2~3줄 요약 텍스트
중요도: 🔴 부정 / 🟢 긍정 / ⚪ 중립
```

---

## 설정

### 필요한 준비물
- 네이버 개발자 센터 API 키 (무료)
- Anthropic API 키
- Gmail 앱 비밀번호 (2단계 인증 후 발급)
- Python 3.x

### config.env
```
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
ANTHROPIC_API_KEY=...
GMAIL_ADDRESS=내이메일@gmail.com
GMAIL_APP_PASSWORD=...
RECIPIENTS=임원1@company.com,임원2@company.com
```

### cron 설정
```
0 */2 * * * /usr/bin/python3 /path/to/main.py
```

---

## 프로젝트 구조

```
claude-introduction/
├── main.py
├── crawler.py
├── summarizer.py
├── mailer.py
├── config.env              # git 제외 (.gitignore)
├── seen.json               # 처리된 기사 목록
├── requirements.txt
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-04-11-news-monitor-design.md
```

---

## 제약사항

- macOS가 실행 중이어야 cron 작동
- 네이버 뉴스 검색 API 일일 호출 한도: 25,000건 (충분)
- Claude API 비용: 기사당 약 $0.001 수준
