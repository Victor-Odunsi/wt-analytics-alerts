# GA4 event-anomaly alerting config. Betika only — matches the only client with a
# GA4 per-event pull configured in wt-ingestion-service (source of
# wt-bigquery.client_betika_marts.mart_ga4_events_baseline__daily__betika).
GA4_EVENT_ALERTS = {
    "betika": {
        "bq_project": "wt-bigquery",
        "bq_dataset": "client_betika_marts",
        "baseline_table": "mart_ga4_events_baseline__daily__betika",
        "events": [
            "confirmation_bet_placed",
            "confirmation_deposit_placed",
            "signup_success",
        ],
    },
}
