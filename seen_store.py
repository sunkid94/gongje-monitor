import json
import os

try:
    SEEN_FILE
except NameError:
    SEEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json")


def load_seen() -> set:
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_seen(seen: set) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False)
