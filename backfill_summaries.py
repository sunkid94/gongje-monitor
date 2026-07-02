"""articles.json 폴백 요약 백필 — AI 요약 실패로 원문 일부(설명 앞 200자)로
대체된 기사들을 다시 AI 요약으로 재생성한다.

폴백 판정: summary == description[:200] (enrich 실패 시 동작과 동일).
크레딧 소진 등이 복구된 뒤 1회 실행한다(과거 기사는 자동 재요약되지 않으므로).

사용법:
    python3 backfill_summaries.py --dry-run     # 폴백 건수만 확인
    python3 backfill_summaries.py               # 전체 재요약
    python3 backfill_summaries.py --limit 50    # 일부만(테스트)
"""
import argparse
import json
import logging
import os
import subprocess
import time

from enrich import enrich_article, is_fallback_summary, _PUBLISHER_SUFFIX_RE, _TRACKED_ORGS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill-summaries")

REPO = os.path.dirname(os.path.abspath(__file__))
INPUT = os.path.join(REPO, "articles.json")
BACKUP = INPUT + ".pre-summary-backfill"


def commit_and_push(message: str, files=("articles.json",), retries: int = 3) -> bool:
    """변경된 파일을 commit 후 GitHub에 push. run.sh 와 동일한 pull --rebase + 재시도 방식.

    백필은 수집 파이프라인(run.sh) 밖에서 도므로 push 로직이 없으면 재요약본이
    VM 작업트리에만 남는다(2026-06-28 사건). 그래서 백필 자체가 push 하도록 한다.
    """
    def git(*args) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", REPO, *args],
                              capture_output=True, text=True)

    if git("diff", "--quiet", "--", *files).returncode == 0:
        log.info("변경 없음 — push 건너뜀")
        return True

    git("add", *files)
    if git("commit", "-m", message).returncode != 0:
        log.error("git commit 실패 — push 중단")
        return False

    for i in range(1, retries + 1):
        if (git("pull", "--rebase", "origin", "main").returncode == 0
                and git("push", "origin", "main").returncode == 0):
            log.info("git push 성공")
            return True
        log.warning("git push 재시도 %d/%d", i, retries)
        time.sleep(5)
    log.error("git push %d회 실패 — VM에서 수동 push 필요", retries)
    return False


def _title_clean(article: dict) -> str:
    return article.get("title_clean") or _PUBLISHER_SUFFIX_RE.sub("", article.get("title", ""))


def backfill_articles(articles: list, enrich_fn=enrich_article, delay: float = 0.0) -> int:
    """폴백 요약 기사를 재요약. articles 를 제자리 수정하고 갱신 건수를 반환한다."""
    updated = 0
    for a in articles:
        if not is_fallback_summary(a.get("summary", ""), a.get("description", "")):
            continue
        orgs = _TRACKED_ORGS if a.get("is_company") else None
        ai = enrich_fn(_title_clean(a), a.get("description", ""), orgs=orgs)
        a["summary"] = ai["summary"]
        a["sentiment"] = ai["sentiment"]
        if ai.get("event_label"):
            a["event_label"] = ai["event_label"]
        updated += 1
        if delay:
            time.sleep(delay)
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="재요약 없이 폴백 건수만 출력")
    parser.add_argument("--limit", type=int, default=0, help="최대 N건만 재요약(0=전체)")
    parser.add_argument("--delay", type=float, default=0.3, help="API 호출 간 간격(초)")
    parser.add_argument("--no-push", action="store_true",
                        help="재요약 후 자동 commit·push 하지 않음(기본은 push)")
    args = parser.parse_args()

    with open(INPUT, encoding="utf-8") as f:
        articles = json.load(f)
    fallbacks = [a for a in articles
                 if is_fallback_summary(a.get("summary", ""), a.get("description", ""))]
    log.info("전체 %d건 / 폴백 %d건", len(articles), len(fallbacks))

    if args.dry_run:
        return
    if not fallbacks:
        log.info("재요약할 폴백 기사 없음")
        return

    if not os.path.exists(BACKUP):
        with open(BACKUP, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        log.info("백업 저장: %s", BACKUP)

    targets = fallbacks[: args.limit] if args.limit else fallbacks
    log.info("재요약 대상 %d건 시작…", len(targets))
    n = backfill_articles(targets, delay=args.delay)

    with open(INPUT, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    log.info("완료: %d건 재요약 → %s 저장", n, os.path.basename(INPUT))

    if args.no_push:
        log.info("--no-push 지정 — 자동 push 생략(수동 commit·push 필요)")
    elif n:
        commit_and_push(f"chore: 백필 재요약 {n}건 반영 (AI 요약 폴백 복구)")


if __name__ == "__main__":
    main()
