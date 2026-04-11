import json
import os
from datetime import datetime

# Use setdefault-style initialization so that importlib.reload does not
# overwrite values that have already been patched by tests.
import sys as _sys
_mod = _sys.modules[__name__]

if not hasattr(_mod, "ARTICLES_FILE"):
    ARTICLES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "articles.json")
else:
    ARTICLES_FILE = _mod.ARTICLES_FILE  # preserve patched value across reload

if not hasattr(_mod, "MAX_ARTICLES"):
    MAX_ARTICLES = 500
else:
    MAX_ARTICLES = _mod.MAX_ARTICLES  # preserve patched value across reload


def load_articles() -> list:
    try:
        with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_articles(articles: list) -> None:
    with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
        json.dump(articles[:MAX_ARTICLES], f, ensure_ascii=False, indent=2)


def add_articles(new_articles: list) -> None:
    existing = load_articles()
    timestamped = [
        {**a, "collected_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
        for a in new_articles
    ]
    save_articles(timestamped + existing)
