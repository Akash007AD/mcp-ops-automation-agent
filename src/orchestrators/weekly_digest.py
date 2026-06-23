"""
Weekly digest job (runs Monday at settings.weekly_summary_time, default 9 AM).

list_open_entries(since=7_days_ago) -> Groq drafts digest ->
post_message() + send_summary_email() + telegram_send_message()

All three delivery channels are attempted independently.

Can also be run standalone for manual testing:
    python -m src.orchestrators.weekly_digest
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core import slack_ops, telegram_ops
from src.core.config import settings
from src.core.email_ops import send_summary_email
from src.core.llm_ops import draft_weekly_digest
from src.core.tracker import get_tracker
from src.utils.logging_setup import get_logger

logger = get_logger("weekly_digest")


def _seven_days_ago_iso() -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    cutoff = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
    return cutoff.isoformat()


def _week_range_label() -> str:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=6)
    def _fmt(d) -> str:
        return f"{d.strftime('%b')} {d.day}"
    return f"{_fmt(start)} - {_fmt(end)}"


def run() -> dict:
    result = {
        "entries": 0,
        "slack_posted": False,
        "email_sent": False,
        "telegram_sent": False,
    }

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

    # ── Slack ─────────────────────────────────────────────────────────────────
    try:
        slack_ops.post_message(body)
        result["slack_posted"] = True
        logger.info("Posted weekly digest to Slack")
    except Exception:
        logger.exception("Failed to post weekly digest to Slack")

    # ── Email (SMTP — multi-recipient) ────────────────────────────────────────
    try:
        recipients = settings.email_recipients_weekly
        if not recipients:
            logger.warning("No weekly email recipients in config.yaml — skipping email")
        else:
            week_range = _week_range_label()
            subject = settings.subject_template_weekly.format(week_range=week_range)
            send_summary_email(to=recipients, subject=subject, body=body)
            result["email_sent"] = True
            logger.info("Sent weekly digest email to %s", recipients)
    except Exception:
        logger.exception("Failed to send weekly digest email")

    # ── Telegram ──────────────────────────────────────────────────────────────
    try:
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            logger.info("Telegram not configured — skipping")
        else:
            tg_text = telegram_ops.format_summary_for_telegram(
                f"📊 Weekly Digest — {_week_range_label()}", body
            )
            telegram_ops.send_message(tg_text)
            result["telegram_sent"] = True
            logger.info("Sent weekly digest to Telegram")
    except Exception:
        logger.exception("Failed to send weekly digest to Telegram")

    logger.info("Weekly digest done: %s", result)
    return result


if __name__ == "__main__":
    run()
