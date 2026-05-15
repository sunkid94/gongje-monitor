"""articles.json 일괄 재처리 — 원문 발행일 backfill / 옛 기사 제거.

각 기사 link에 resolve_published_time() 호출 →
  - 7일 이내: published_at 부여 후 보존
  - 7일 초과: 제거 + seen.json에 추가하여 재수집 차단
  - 해상 실패(None): 보존 (다음 사이클에 자연 처리됨)

사용법: python3 backfill_pubdate.py
"""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from pub_date import resolve_published_time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
log = logging.getLogger("backfill")

INPUT = 'articles.json'
BACKUP = 'articles.json.pre-pubdate-backfill'
SEEN = 'seen.json'
MAX_AGE_DAYS = 7
WORKERS = 3
SAVE_EVERY = 50
THROTTLE_SECONDS = 0.5


def save(articles, drops, seen):
    kept = [a for i, a in enumerate(articles) if i not in drops]
    with open(INPUT, 'w') as f:
        json.dump(kept, f, ensure_ascii=False)
    with open(SEEN, 'w') as f:
        json.dump(sorted(seen), f, ensure_ascii=False)


def main():
    start = time.time()
    with open(INPUT) as f:
        articles = json.load(f)
    log.info("loaded %d articles", len(articles))

    import os
    if not os.path.exists(BACKUP):
        with open(BACKUP, 'w') as f:
            json.dump(articles, f, ensure_ascii=False)
        log.info("backup → %s", BACKUP)
    else:
        log.info("backup already exists, skip → %s", BACKUP)

    try:
        with open(SEEN) as f:
            seen = set(json.load(f))
    except FileNotFoundError:
        seen = set()
    log.info("seen links: %d", len(seen))

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    log.info("cutoff: %s (older = drop)", cutoff.isoformat())

    todo = [(i, a) for i, a in enumerate(articles)
            if not a.get('published_at') and a.get('link')]
    log.info("to resolve: %d", len(todo))

    resolved = 0
    unresolved = 0
    drops = set()

    def task(item):
        i, a = item
        try:
            dt = resolve_published_time(a['link'])
            time.sleep(THROTTLE_SECONDS)
            return i, dt
        except Exception as e:
            log.warning("[%d] exception: %s", i, e)
            time.sleep(THROTTLE_SECONDS)
            return i, None

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(task, item) for item in todo]
        for n, fut in enumerate(as_completed(futures), 1):
            i, dt = fut.result()
            a = articles[i]
            if dt is None:
                unresolved += 1
            else:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    drops.add(i)
                    seen.add(a.get('link'))
                    log.info("DROP [%s] %s | %s",
                             dt.date().isoformat(),
                             a.get('keyword') or a.get('category'),
                             (a.get('title_clean') or a.get('title') or '')[:60])
                else:
                    a['published_at'] = dt.isoformat()
                    resolved += 1
            if n % SAVE_EVERY == 0:
                save(articles, drops, seen)
                elapsed = time.time() - start
                eta = (elapsed / n) * (len(todo) - n)
                log.info("progress %d/%d | resolved=%d unresolved=%d dropped=%d | elapsed=%.0fs eta=%.0fs",
                         n, len(todo), resolved, unresolved, len(drops), elapsed, eta)

    save(articles, drops, seen)
    elapsed = time.time() - start
    kept = len(articles) - len(drops)
    log.info("DONE in %.0fs | total=%d kept=%d resolved=%d unresolved=%d dropped=%d",
             elapsed, len(articles), kept, resolved, unresolved, len(drops))


if __name__ == '__main__':
    main()
