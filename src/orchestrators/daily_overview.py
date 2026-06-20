"""
Daily overview job (runs at settings.daily_summary_time, default 6 PM).

list_open_entries(since=today_midnight) -> Claude/Groq drafts summary ->
post_message() + send_summary_email(to=daily_recipients).

Per 03_BUILD_PLAN.md Day 10: failures in one delivery channel (Slack vs
email) must not block the other — both are attempted independently.

Can also be run standalone for manual testing:
    python -m src.orchestrators.daily_overview
"""

from __future__ import annotations

from datetime import datetime, time, timezone

from src.core import slack_ops
from src.core.config import settings
from src.core.email_ops import send_summary_email
from src.core.llm_ops import draft_daily_overview
from src.core.tracker import get_tracker
from src.utils.logging_setup import get_logger

logger = get_logger("daily_overview")


def _today_midnight_utc_iso() -> str:
    now = datetime.now(timezone.utc)
    midnight = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    return midnight.isoformat()


def run() -> dict:
    result = {"entries": 0, "slack_posted": False, "email_sent": False}

    tracker = get_tracker()
    since = _today_midnight_utc_iso()
    logger.info("Building daily overview (since=%s)", since)

    try:
        entries = tracker.list_open_entries(since=since)
    except Exception:
        logger.exception("Failed to read tracker entries — aborting")
        return result

    result["entries"] = len(entries)

    try:
        body = draft_daily_overview(entries)
    except Exception:
        logger.exception("Failed to draft daily overview via LLM")
        return result

    # Slack post — failure here should not block email delivery.
    try:
        slack_ops.post_message(body)
        result["slack_posted"] = True
        logger.info("Posted daily overview to Slack")
    except Exception:
        logger.exception("Failed to post daily overview to Slack")

    # Email — failure here should not block having already posted to Slack.
    try:
        recipients = settings.email_recipients_daily
        if not recipients:
            logger.warning("No daily email recipients configured in config.yaml — skipping email")
        else:
            subject = settings.subject_template_daily.format(
                date=datetime.now().strftime("%Y-%m-%d")
            )
            send_summary_email(to=recipients, subject=subject, body=body)
            result["email_sent"] = True
            logger.info("Sent daily overview email to %s", recipients)
    except Exception:
        logger.exception("Failed to send daily overview email")

    logger.info("Daily overview done: %s", result)
    return result


if __name__ == "__main__":
    run()
