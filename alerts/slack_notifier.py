import logging
import os
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"

# Named per-person rather than a single generic var so it's obvious from .env /
# deploy.sh who each ID belongs to. Every alert broadcasts to all of these that are
# set — add a name here (and the matching env var) for anyone else who should get
# every alert.
DM_RECIPIENT_ENV_VARS = ["DEV_SLACK_DM_USER_ID", "NICK_SLACK_DM_USER_ID"]


def build_message(
    client_id: str,
    anomalies: list,
    insight: str | None = None,
    generated_at: datetime | None = None,
) -> dict:
    # The underlying mart is daily-grain only (see docs/ga4_daily_marts_schema.md
    # upstream) — there's no per-event time-of-day to show, each anomaly's `date`
    # already covers that. What's useful instead is when THIS alert was generated,
    # so a reader can tell how fresh it is at a glance.
    generated_at = generated_at or datetime.now(timezone.utc)
    lines = [
        f"*GA4 event anomalies — {client_id}*",
        f"_Generated {generated_at.strftime('%Y-%m-%d %H:%M UTC')}_",
    ]
    if insight:
        # Labeled explicitly so readers don't mistake the LLM's phrasing for an
        # additional mechanical fact alongside the z_score/pct_change lines below.
        lines.append(f"_{insight}_ (AI-generated summary)")
        lines.append("")
    for a in anomalies:
        arrow = "\U0001F53A" if a.direction == "above" else "\U0001F53B"
        lines.append(f"{arrow} `{a.event_name}` on {a.date}: {a.event_count:,} events — {a.reason}")
    return {"text": "\n".join(lines)}


def _default_dm_user_ids() -> list[str]:
    return [
        uid
        for var in DM_RECIPIENT_ENV_VARS
        if (uid := os.environ.get(var))
    ]


def _post_dm(bot_token: str, dm_user_id: str, message: dict) -> None:
    # chat.postMessage accepts a user ID in place of a channel ID and Slack
    # auto-opens/reuses the DM with that user — no separate conversations.open call
    # needed.
    payload = {"channel": dm_user_id, **message}
    resp = requests.post(
        SLACK_POST_MESSAGE_URL,
        headers={"Authorization": f"Bearer {bot_token}"},
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    # chat.postMessage returns HTTP 200 even on failure (e.g. missing chat:write
    # scope, invalid user ID) — the real result is in the "ok" field.
    if not body.get("ok"):
        raise RuntimeError(f"Slack chat.postMessage to {dm_user_id} failed: {body.get('error')}")


def send_alert(
    client_id: str,
    anomalies: list,
    bot_token: str | None = None,
    dm_user_ids: list[str] | None = None,
    insight: str | None = None,
) -> None:
    if not anomalies:
        logger.info("No anomalies to report — skipping Slack post")
        return

    bot_token = bot_token or os.environ.get("SLACK_BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("SLACK_BOT_TOKEN not set — cannot send Slack alert")

    dm_user_ids = dm_user_ids if dm_user_ids is not None else _default_dm_user_ids()
    if not dm_user_ids:
        raise RuntimeError(
            f"No Slack DM recipients configured — set at least one of "
            f"{DM_RECIPIENT_ENV_VARS}"
        )

    message = build_message(client_id, anomalies, insight=insight)

    errors = {}
    for dm_user_id in dm_user_ids:
        try:
            _post_dm(bot_token, dm_user_id, message)
            logger.info(f"DM'd {len(anomalies)} anomalies to {dm_user_id} for {client_id}")
        except Exception as e:
            errors[dm_user_id] = str(e)
            logger.warning(f"Failed to DM {dm_user_id}: {e}")

    # One recipient having a stale/invalid ID shouldn't block delivery to everyone
    # else — only raise if literally no one got the alert.
    if errors and len(errors) == len(dm_user_ids):
        raise RuntimeError(f"Slack DM failed for every recipient: {errors}")
