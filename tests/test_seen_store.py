import json
import pytest
from unittest.mock import patch


def test_load_seen_returns_empty_set_when_file_missing():
    with patch("seen_store.SEEN_FILE", "/tmp/nonexistent_seen_xyz.json"):
        import seen_store
        import importlib
        importlib.reload(seen_store)
        result = seen_store.load_seen()
    assert result == set()


def test_load_seen_returns_urls_from_existing_file(tmp_path):
    seen_file = tmp_path / "seen.json"
    seen_file.write_text(json.dumps(["http://a.com", "http://b.com"]))
    with patch("seen_store.SEEN_FILE", str(seen_file)):
        import seen_store
        import importlib
        importlib.reload(seen_store)
        result = seen_store.load_seen()
    assert result == {"http://a.com", "http://b.com"}


def test_save_seen_writes_urls_to_file(tmp_path):
    seen_file = tmp_path / "seen.json"
    with patch("seen_store.SEEN_FILE", str(seen_file)):
        import seen_store
        import importlib
        importlib.reload(seen_store)
        seen_store.save_seen({"http://a.com", "http://b.com"})
    data = json.loads(seen_file.read_text())
    assert set(data) == {"http://a.com", "http://b.com"}
