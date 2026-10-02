# wt-analytics-alerts

Anomaly flagging/alerting on top of the GA4 daily event marts that
[wt-ingestion-service](../wt-ingestion-service) builds for Betika. That repo stops at exposing
facts (raw counts + a same-weekday statistical baseline) — this repo is where the judgment call
("is this worth telling someone about?") and the Slack notification live.

## What it does

Once a day, for each monitored GA4 event (`confirmation_bet_placed`, `confirmation_deposit_placed`,
`signup_success`):

1. Reads yesterday's row from `wt-bigquery.client_betika_marts.mart_ga4_events_baseline__daily__betika`.
2. Evaluates it against its same-weekday baseline (`alerts/rules.py`) — flags it only if there's
   enough baseline history (`same_weekday_samples >= 4`) *and* `z_score` clears the threshold.
   Thin-history rows are logged as low-confidence, never alerted on.
3. If there's at least one flagged anomaly, asks an LLM via Groq (`alerts/llm_insights.py`,
   currently `openai/gpt-oss-120b` — Llama 3.3 70B Instruct was the original target but Groq
   retired it; override with `GROQ_MODEL` if their catalog changes again) to phrase the stats as
   a short narrative — explicitly instructed not to guess at causes, since no fixtures/marketing
   calendar is fed in. If `GROQ_API_KEY` is unset or the call fails, the alert still goes out with
   just the raw stats.
4. DMs any flagged anomalies to every configured recipient (via `chat.postMessage` with a user ID
   as the `channel`, using a bot token), with the AI-generated summary (clearly labeled as such)
   above the raw per-event stats. The bot needs the `chat:write` scope. Recipients are named env
   vars (`DEV_SLACK_DM_USER_ID`, `NICK_SLACK_DM_USER_ID` — see `DM_RECIPIENT_ENV_VARS` in
   `alerts/slack_notifier.py`); everyone with an ID set gets every alert. One recipient having a
   stale ID doesn't block delivery to the others.

**Known limitation, inherited from the upstream mart**: the baseline is purely calendar-driven, so
it can't distinguish a real anomaly from a football-fixture irregularity (an international break,
a UCL off-week, a derby week) — see the comment at the top of `alerts/rules.py`.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env
# fill in GOOGLE_APPLICATION_CREDENTIALS, SLACK_BOT_TOKEN, at least one
# *_SLACK_DM_USER_ID, and (optionally) GROQ_API_KEY
```

## Run

```bash
python main.py                              # yesterday, betika
python main.py --date 2026-09-23             # backfill a specific date
```

## Test

```bash
pytest
```

## Deploy

Runs as a Cloud Run Job in `wt-bigquery` (same GCP project as the marts), mirroring
wt-ingestion-service's deploy pattern:

```bash
bash deploy.sh --setup   # first time only: creates the Slack bot token + Groq key secrets
bash deploy.sh           # build + deploy
bash deploy.sh --run     # trigger a manual run
```

See the end of `deploy.sh`'s output for the Cloud Scheduler command. Currently one runs daily:

- `wt-analytics-alerts-daily-betika` — `0 7 * * *` `Africa/Lagos` (7am WAT / 9am EAT for Nick in
  Kenya), a little after the upstream marts finish rebuilding at ~05:00 UTC. A second daily
  trigger (midnight WAT) was tried and removed 2026-09-29 — since the mart only rebuilds once a
  day and `main.py` always evaluates "yesterday (UTC)" relative to run time, a second same-day run
  just re-checks identical data and double-sends any alert.
