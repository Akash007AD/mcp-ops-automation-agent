"""
Weekly digest job (runs Monday at settings.weekly_summary_time, default 9 AM).

list_open_entries(since=7_days_ago) -> Groq drafts digest ->
post_message() + send_summary_email(to=weekly_recipients).

Mirrors daily_overview.py: failures in one delivery channel (Slack vs email)
do not block the other — both are attempted independently, per
03_BUILD_PLAN.md Day 10.

Can also be run standalone for manual testing:
    python -m src.orchestrators.weekly_digest
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core import slack_ops
from src.core.config import settings
from src.core.email_ops import send_summary_email
from src.core.llm_ops import draft_weekly_digest
from src.core.tracker import get_tracker
from src.utils.logging_setup import get_logger

logger = get_logger("weekly_digest")


def _seven_days_ago_iso() -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    # Snap to midnight so the window is always full days, not a rolling 168 hrs.
    cutoff = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
    return cutoff.isoformat()


def _week_range_label() -> str:
    """Human-readable range for the email subject, e.g. 'Jun 13 - Jun 19'."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=6)
    # strftime '%-d' (no zero-pad) is Linux only; use %d on Windows and strip manually.
    def _fmt(d: object) -> str:
        return f"{d.strftime('%b')} {d.day}"

    return f"{_fmt(start)} - {_fmt(end)}"


def run() -> dict:
    result = {"entries": 0, "slack_posted": False, "email_sent": False}

    tracker = get_tracker()
    since = _seven_days_ago_iso()
    logger.info("Building weekly digest (since=%s)", since)

    try:
        entries = tracker.list_open_entries(since=since)
    except Exception:
        logger.exception("Failed to read tracker entries — aborting")
        return result

    result["entries"] = len(entries)

    try:
        body = draft_weekly_digest(entries)
    except Exception:
        logger.exception("Failed to draft weekly digest via LLM")
        return result

    # Slack post — failure here does not block email delivery.
    try:
        slack_ops.post_message(body)
        result["slack_posted"] = True
        logger.info("Posted weekly digest to Slack")
    except Exception:
        logger.exception("Failed to post weekly digest to Slack")

    # Email — failure here does not affect the already-attempted Slack post.
    try:
        recipients = settings.email_recipients_weekly
        if not recipients:
            logger.warning(
                "No weekly email recipients configured in config.yaml — skipping email"
            )
        else:
            subject = settings.subject_template_weekly.format(
                week_range=_week_range_label()
            )
            send_summary_email(to=recipients, subject=subject, body=body)
            result["email_sent"] = True
            logger.info("Sent weekly digest email to %s", recipients)
    except Exception:
        logger.exception("Failed to send weekly digest email")

    logger.info("Weekly digest done: %s", result)
    return result


if __name__ == "__main__":
    run()
