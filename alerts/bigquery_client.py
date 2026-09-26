import logging

from google.cloud import bigquery

logger = logging.getLogger(__name__)


def fetch_baseline_rows(
    bq_project: str, bq_dataset: str, table: str, events: list[str], target_date: str
) -> list[dict]:
    """
    Fetch one row per event_name from the same-weekday baseline mart for
    target_date. Pass yesterday's date (UTC) under normal operation — GA4 data
    for "today" isn't final until the day ends, and the upstream mart won't have
    rebuilt with it yet.
    """
    client = bigquery.Client(project=bq_project)
    query = f"""
        SELECT date, event_name, event_count, same_weekday_samples,
               baseline_mean, baseline_stddev, z_score, baseline_pct_change, direction
        FROM `{bq_project}.{bq_dataset}.{table}`
        WHERE event_name IN UNNEST(@events)
          AND date = @target_date
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("events", "STRING", events),
            bigquery.ScalarQueryParameter("target_date", "DATE", target_date),
        ]
    )
    rows = [dict(row) for row in client.query(query, job_config=job_config).result()]
    logger.info(f"Fetched {len(rows)} baseline rows for {target_date}")
    return rows
