from datetime import datetime, timezone

import pytest

from alerts.rules import AnomalyResult
from alerts.slack_notifier import build_message, send_alert


def _anomaly(**overrides):
    base = dict(
        event_name="confirmation_deposit_placed",
        date="2026-09-23",
        event_count=17000,
        direction="below",
        confidence="full",
        reason="z_score=-2.40 (threshold 2.0), -41.2% vs 8-week same-weekday baseline",
        is_anomaly=True,
    )
    base.update(overrides)
    return AnomalyResult(**base)


def test_message_without_insight_has_no_ai_label():
    payload = build_message("betika", [_anomaly()])
    assert "AI-generated" not in payload["text"]
    assert "confirmation_deposit_placed" in payload["text"]


def test_message_with_insight_labels_it_clearly():
    payload = build_message("betika", [_anomaly()], insight="Deposits dropped sharply.")
    assert "Deposits dropped sharply." in payload["text"]
    assert "AI-generated" in payload["text"]
    # the raw per-event stats line must still be present alongside the narrative
    assert "confirmation_deposit_placed" in payload["text"]


def test_message_includes_generated_at_timestamp():
    ts = datetime(2026, 9, 29, 6, 3, tzinfo=timezone.utc)
    payload = build_message("betika", [_anomaly()], generated_at=ts)
    assert "Generated 2026-09-29 06:03 UTC" in payload["text"]


def test_message_defaults_generated_at_to_now_when_omitted():
    before = datetime.now(timezone.utc)
    payload = build_message("betika", [_anomaly()])
    after = datetime.now(timezone.utc)
    assert before.strftime("%Y-%m-%d") in payload["text"] or after.strftime("%Y-%m-%d") in payload["text"]


def test_send_alert_with_no_anomalies_skips_the_api_call(monkeypatch):
    called = False

    def fake_post(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("alerts.slack_notifier.requests.post", fake_post)
    send_alert("betika", [], bot_token="xoxb-fake", dm_user_ids=["U123"])
    assert called is False


def test_send_alert_posts_to_chat_post_message_with_bearer_token(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("alerts.slack_notifier.requests.post", fake_post)
    send_alert("betika", [_anomaly()], bot_token="xoxb-fake", dm_user_ids=["U123"])

    assert captured["url"] == "https://slack.com/api/chat.postMessage"
    assert captured["headers"]["Authorization"] == "Bearer xoxb-fake"
    assert captured["json"]["channel"] == "U123"
    assert "confirmation_deposit_placed" in captured["json"]["text"]


def test_send_alert_broadcasts_to_every_recipient(monkeypatch):
    posted_to = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def fake_post(url, headers, json, timeout):
        posted_to.append(json["channel"])
        return FakeResponse()

    monkeypatch.setattr("alerts.slack_notifier.requests.post", fake_post)
    send_alert("betika", [_anomaly()], bot_token="xoxb-fake", dm_user_ids=["U_DEV", "U_NICK"])

    assert posted_to == ["U_DEV", "U_NICK"]


def test_send_alert_one_bad_recipient_does_not_block_the_rest(monkeypatch):
    posted_to = []

    class FakeResponse:
        def __init__(self, ok, error=None):
            self._ok = ok
            self._error = error

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": self._ok, "error": self._error}

    def fake_post(url, headers, json, timeout):
        posted_to.append(json["channel"])
        if json["channel"] == "U_BAD":
            return FakeResponse(ok=False, error="user_not_found")
        return FakeResponse(ok=True)

    monkeypatch.setattr("alerts.slack_notifier.requests.post", fake_post)
    # must not raise — U_GOOD still got the alert
    send_alert("betika", [_anomaly()], bot_token="xoxb-fake", dm_user_ids=["U_BAD", "U_GOOD"])

    assert posted_to == ["U_BAD", "U_GOOD"]


def test_send_alert_raises_when_every_recipient_fails(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": False, "error": "not_in_channel"}

    monkeypatch.setattr("alerts.slack_notifier.requests.post", lambda *a, **k: FakeResponse())

    with pytest.raises(RuntimeError, match="every recipient"):
        send_alert("betika", [_anomaly()], bot_token="xoxb-fake", dm_user_ids=["U123"])


def test_send_alert_requires_bot_token(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="SLACK_BOT_TOKEN"):
        send_alert("betika", [_anomaly()], bot_token=None, dm_user_ids=["U123"])


def test_send_alert_requires_at_least_one_recipient(monkeypatch):
    monkeypatch.delenv("DEV_SLACK_DM_USER_ID", raising=False)
    monkeypatch.delenv("NICK_SLACK_DM_USER_ID", raising=False)
    with pytest.raises(RuntimeError, match="No Slack DM recipients"):
        send_alert("betika", [_anomaly()], bot_token="xoxb-fake", dm_user_ids=None)
