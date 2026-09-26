from alerts.rules import MIN_SAMPLES_FOR_ZSCORE, Z_SCORE_THRESHOLD, evaluate_row


def _row(**overrides):
    base = {
        "event_name": "confirmation_deposit_placed",
        "date": "2026-09-23",
        "event_count": 41000,
        "same_weekday_samples": 8,
        "baseline_mean": 41276.0,
        "baseline_stddev": 3000.0,
        "z_score": 0.0,
        "baseline_pct_change": 0.0,
        "direction": "below",
    }
    base.update(overrides)
    return base


def test_low_sample_count_is_not_flagged_as_anomaly():
    row = _row(same_weekday_samples=MIN_SAMPLES_FOR_ZSCORE - 1, z_score=-3.5)
    result = evaluate_row(row)
    assert result.confidence == "low"
    assert result.is_anomaly is False


def test_high_zscore_with_full_baseline_is_flagged():
    row = _row(z_score=Z_SCORE_THRESHOLD + 0.1)
    result = evaluate_row(row)
    assert result.confidence == "full"
    assert result.is_anomaly is True


def test_normal_zscore_with_full_baseline_is_not_flagged():
    row = _row(z_score=1.0)
    result = evaluate_row(row)
    assert result.confidence == "full"
    assert result.is_anomaly is False


def test_null_zscore_is_treated_as_low_confidence():
    row = _row(z_score=None)
    result = evaluate_row(row)
    assert result.confidence == "low"
    assert result.is_anomaly is False
