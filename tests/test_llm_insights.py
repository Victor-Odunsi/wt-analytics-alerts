from alerts.llm_insights import generate_insight
from alerts.rules import AnomalyResult


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


def test_no_anomalies_returns_none_without_calling_api(monkeypatch):
    called = False

    def fake_post(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("alerts.llm_insights.requests.post", fake_post)
    assert generate_insight([]) is None
    assert called is False


def test_missing_api_key_returns_none(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert generate_insight([_anomaly()], api_key=None) is None


def test_successful_call_returns_stripped_content(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "  Deposits dropped sharply.  "}}]}

    def fake_post(url, headers, json, timeout):
        assert "Authorization" in headers
        assert json["model"]
        return FakeResponse()

    monkeypatch.setattr("alerts.llm_insights.requests.post", fake_post)
    result = generate_insight([_anomaly()], api_key="fake-key")
    assert result == "Deposits dropped sharply."


def test_api_failure_returns_none_instead_of_raising(monkeypatch):
    def fake_post(*args, **kwargs):
        raise RuntimeError("network error")

    monkeypatch.setattr("alerts.llm_insights.requests.post", fake_post)
    result = generate_insight([_anomaly()], api_key="fake-key")
    assert result is None


def test_empty_content_returns_none_instead_of_blank_string(monkeypatch):
    # Reasoning models (e.g. gpt-oss-120b) can burn the whole token budget on their
    # internal "reasoning" trace and return empty final content — this must not be
    # sent to Slack as a blank AI-generated summary line.
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "   "}}]}

    monkeypatch.setattr("alerts.llm_insights.requests.post", lambda *a, **k: FakeResponse())
    result = generate_insight([_anomaly()], api_key="fake-key")
    assert result is None


def test_request_uses_low_reasoning_effort(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "Deposits dropped."}}]}

    def fake_post(url, headers, json, timeout):
        captured.update(json)
        return FakeResponse()

    monkeypatch.setattr("alerts.llm_insights.requests.post", fake_post)
    generate_insight([_anomaly()], api_key="fake-key")
    assert captured["reasoning_effort"] == "low"
