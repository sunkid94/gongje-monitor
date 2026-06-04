from unittest.mock import patch
import notifier


def _article(title):
    return {"title": title, "is_company": True, "link": title}


@patch("notifier.webpush")
@patch("notifier._load_subscriptions")
def test_duplicate_story_not_sent_on_second_batch(mock_subs, mock_webpush, tmp_path, monkeypatch):
    mock_subs.return_value = [{"sub": {"endpoint": "https://x"}, "name": "tester"}]
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "dummy-key")
    with patch("push_dedup.PUSHED_FILE", str(tmp_path / "pushed.json")):
        notifier.send_company_push([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - 네이트")])
        first_calls = mock_webpush.call_count
        notifier.send_company_push([_article("전문건설공제조합, 피치 국제신용등급 'A+' 유지 - 이데일리")])
        second_calls = mock_webpush.call_count - first_calls
    assert first_calls == 1     # 첫 스토리 발송
    assert second_calls == 0    # 같은 스토리 재발송 안 함


@patch("notifier.webpush")
@patch("notifier._load_subscriptions")
def test_no_record_when_no_subscribers(mock_subs, mock_webpush, tmp_path, monkeypatch):
    # 구독자 없음 → filter_unpushed 호출 전 반환, 이력 미생성 → 나중에 정상 발송 가능
    mock_subs.return_value = []
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "dummy-key")
    pushed = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(pushed)):
        notifier.send_company_push([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - 네이트")])
    assert not pushed.exists()  # 발송 못 했으면 스토리를 '푸시됨'으로 기록하지 않음
