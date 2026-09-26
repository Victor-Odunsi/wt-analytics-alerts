import logging
import os

import requests

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
# Llama 3.3 70B Instruct was the original target model but Groq has since retired
# it (confirmed against the live /models endpoint 2026-09-26 — no Llama model of
# any size remained in the catalog). gpt-oss-120b is Groq's current closest
# equivalent by size/capability; override via GROQ_MODEL if that changes again.
DEFAULT_MODEL = "openai/gpt-oss-120b"

# Told explicitly not to guess at causes (fixture calendar, promotions, outages):
# the upstream baseline is purely calendar-driven (see alerts/rules.py) and this
# script has no fixtures-calendar or campaign-calendar input, so any cause the
# model offered would be an unsupported guess dressed up as an explanation.
SYSTEM_PROMPT = (
    "You write a short, factual summary for a Slack alert about GA4 event anomalies "
    "on a betting platform. You are given only the statistics for each anomaly — no "
    "fixture calendar, no marketing calendar, no other context. Do not guess at "
    "causes (e.g. do not mention football matches, promotions, or outages) unless "
    "they are explicitly stated in the input, since none are. State what changed and "
    "by how much, in plain language, in at most 3 sentences total. No preamble, no "
    "recommendations, no markdown headers."
)


def _format_anomaly(a) -> str:
    return (
        f"- {a.event_name} on {a.date}: {a.event_count:,} events, "
        f"{a.direction or 'unknown'} baseline, {a.reason}"
    )


def _build_prompt(anomalies: list) -> str:
    return "Anomalies detected:\n" + "\n".join(_format_anomaly(a) for a in anomalies)


def generate_insight(
    anomalies: list, api_key: str | None = None, model: str | None = None
) -> str | None:
    """
    Ask an LLM (via Groq, see DEFAULT_MODEL) to phrase the detected anomalies as a
    short narrative for the Slack alert. Never raises — returns None if there's
    nothing to summarize, no API key is configured, or the call fails, so the alert
    still goes out with the raw stats even when the LLM is unavailable.
    """
    if not anomalies:
        return None

    api_key = api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY not set — skipping LLM insight, sending raw stats only")
        return None

    model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(anomalies)},
        ],
        "temperature": 0.2,
        "max_tokens": 400,
        # gpt-oss-120b is a reasoning model — its internal "reasoning" trace draws
        # from the same max_tokens budget as the final "content". At the default
        # effort, a long system prompt like ours can burn the whole budget on
        # reasoning and leave content empty (finish_reason "length", empty string).
        # "low" is plenty for a task this simple and leaves the budget for content.
        "reasoning_effort": "low",
    }

    try:
        resp = requests.post(
            GROQ_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if not content:
            logger.warning("LLM returned empty content — sending raw stats only")
            return None
        return content
    except Exception as e:
        logger.warning(f"LLM insight generation failed, sending raw stats only: {e}")
        return None
