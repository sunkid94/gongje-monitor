import json
from unittest.mock import patch
import notifier


def _article(title):
    return {"title": title, "is_company": True, "link": title}


def test_distinct_articles_get_distinct_tags():
    # 서로 다른 기사는 꼬리표가 달라야 알림이 안 덮어쓰고 쌓임
    a = json.loads(notifier._build_payload([{"title": "A", "link": "http://a"}]))
    b = json.loads(notifier._build_payload([{"title": "B", "link": "http://b"}]))
    assert a["tag"] != b["tag"]
    assert a["tag"].startswith("cig-")


def test_same_article_stable_tag():
    # 같은 기사는 같은 꼬리표(혹시 재발송돼도 중복 표시 안 함)
    a = json.loads(notifier._build_payload([{"title": "A", "link": "http://a"}]))
    b = json.loads(notifier._build_payload([{"title": "A", "link": "http://a"}]))
    assert a["tag"] == b["tag"]


def test_single_push_links_to_article():
    # 단일 기사 푸시는 url이 그 기사 링크여야 알림 클릭 시 기사로 이동
    art = {"title": "전문건설공제조합 A+ 유지", "link": "https://news.example/abc"}
    payload = json.loads(notifier._build_payload([art]))
    assert payload["url"] == "https://news.example/abc"


def test_multi_push_links_to_dashboard():
    # 여러 기사 묶음 푸시는 특정 기사로 못 보내므로 대시보드로
    arts = [
        {"title": "기사1", "link": "https://news.example/1"},
        {"title": "기사2", "link": "https://news.example/2"},
    ]
    payload = json.loads(notifier._build_payload(arts))
    assert payload["url"] == notifier.SITE_URL


def test_single_push_falls_back_to_dashboard_without_link():
    # 링크 없는 기사면 대시보드로 폴백
    payload = json.loads(notifier._build_payload([{"title": "링크없음"}]))
    assert payload["url"] == notifier.SITE_URL


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


@patch("notifier.webpush")
@patch("notifier._load_subscriptions")
def test_no_record_when_vapid_key_missing(mock_subs, mock_webpush, tmp_path, monkeypatch):
    # 구독자는 있으나 VAPID 키 없음 → 발송 불가 → 스토리 기록 안 함
    mock_subs.return_value = [{"sub": {"endpoint": "https://x"}, "name": "tester"}]
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    pushed = tmp_path / "pushed.json"
    with patch("push_dedup.PUSHED_FILE", str(pushed)):
        notifier.send_company_push([_article("전문건설공제조합, 피치 신용등급 A+ 유지 - 네이트")])
    assert not pushed.exists()
    assert mock_webpush.call_count == 0
