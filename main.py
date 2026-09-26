"""
WT Analytics Alerts — GA4 event anomaly detection for Betika.

Reads the target date's row (default: yesterday, UTC) from
mart_ga4_events_baseline__daily__betika for the monitored events, evaluates each
against its same-weekday baseline, and posts any anomalies to Slack.

Usage:
    python main.py
    python main.py --client betika --date 2026-09-23
"""
import argparse
import logging
from datetime import datetime, timedelta, timezone

from alerts.bigquery_client import fetch_baseline_rows
from alerts.llm_insights import generate_insight
from alerts.rules import evaluate_rows
from alerts.slack_notifier import send_alert
from config.clients import GA4_EVENT_ALERTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("main")


def run(client: str, target_date: str) -> None:
    config = GA4_EVENT_ALERTS[client]
    rows = fetch_baseline_rows(
        bq_project=config["bq_project"],
        bq_dataset=config["bq_dataset"],
        table=config["baseline_table"],
        events=config["events"],
        target_date=target_date,
    )
    results = evaluate_rows(rows)

    for r in results:
        if r.confidence == "low":
            logger.info(f"[low-confidence] {r.event_name}: {r.reason}")
        elif r.is_anomaly:
            logger.warning(f"[anomaly] {r.event_name}: {r.reason}")
        else:
            logger.info(f"[ok] {r.event_name}: {r.reason}")

    anomalies = [r for r in results if r.is_anomaly]
    insight = generate_insight(anomalies)
    send_alert(client, anomalies, insight=insight)


def main() -> None:
    parser = argparse.ArgumentParser(description="GA4 event anomaly alerting")
    parser.add_argument("--client", default="betika", choices=list(GA4_EVENT_ALERTS))
    parser.add_argument(
        "--date", default=None, help="Date to evaluate, YYYY-MM-DD (default: yesterday UTC)"
    )
    args = parser.parse_args()

    target_date = args.date or (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    run(args.client, target_date)


if __name__ == "__main__":
    main()
