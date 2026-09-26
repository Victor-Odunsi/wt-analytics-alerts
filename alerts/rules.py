import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# A same-weekday baseline needs real history before its z_score means anything —
# a ~14-day/1-2-sample backfill once flagged confirmation_deposit_placed as
# dropping ~56-58%, which looked like a serious anomaly; with a full 8-sample
# baseline the same dates came back at z_score ~-1.0, well within normal range.
# Rows below this many samples are reported as low-confidence, never as anomalies.
MIN_SAMPLES_FOR_ZSCORE = 4

Z_SCORE_THRESHOLD = 2.0

# NOTE: this rule is calendar-only, same as its upstream baseline — it cannot
# distinguish a real anomaly from a football-fixture-calendar irregularity (an
# international break, a UCL off-week, a derby). That's a known, deliberate gap
# (no fixtures-calendar signal is ingested). If fixture-driven false positives
# become a real problem, address it with a fixtures-calendar input, not by
# further tuning these thresholds.


@dataclass
class AnomalyResult:
    event_name: str
    date: str
    event_count: int
    direction: str | None
    confidence: str  # "full" | "low"
    reason: str
    is_anomaly: bool


def evaluate_row(row: dict) -> AnomalyResult:
    samples = row.get("same_weekday_samples") or 0
    z_score = row.get("z_score")
    pct_change = row.get("baseline_pct_change")
    direction = row.get("direction")

    if samples < MIN_SAMPLES_FOR_ZSCORE or z_score is None:
        return AnomalyResult(
            event_name=row["event_name"],
            date=str(row["date"]),
            event_count=row["event_count"],
            direction=direction,
            confidence="low",
            reason=f"only {samples} same-weekday sample(s) — baseline not established yet",
            is_anomaly=False,
        )

    is_anomaly = abs(z_score) >= Z_SCORE_THRESHOLD
    pct_str = f"{pct_change:+.1f}%" if pct_change is not None else "n/a"
    return AnomalyResult(
        event_name=row["event_name"],
        date=str(row["date"]),
        event_count=row["event_count"],
        direction=direction,
        confidence="full",
        reason=f"z_score={z_score:.2f} (threshold {Z_SCORE_THRESHOLD}), "
        f"{pct_str} vs {samples}-week same-weekday baseline",
        is_anomaly=is_anomaly,
    )


def evaluate_rows(rows: list[dict]) -> list[AnomalyResult]:
    return [evaluate_row(row) for row in rows]
