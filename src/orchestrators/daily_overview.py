"""
Daily overview job (runs at settings.daily_summary_time, default 6 PM).

list_open_entries(since=today_midnight) -> Groq drafts summary ->
post_message() + send_summary_email() + telegram_send_message()

All three delivery channels are attempted independently — failure in one
does not block the others.

Can also be run standalone for manual testing:
    python -m src.orchestrators.daily_overview
"""

from __future__ import annotations

from datetime import datetime, time, timezone

from src.core import slack_ops, telegram_ops
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
    result = {
        "entries": 0,
        "slack_posted": False,
        "email_sent": False,
        "telegram_sent": False,
    }

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

    # ── Slack ─────────────────────────────────────────────────────────────────
    try:
        slack_ops.post_message(body)
        result["slack_posted"] = True
        logger.info("Posted daily overview to Slack")
    except Exception:
        logger.exception("Failed to post daily overview to Slack")

    # ── Email (SMTP — multi-recipient) ────────────────────────────────────────
    try:
        recipients = settings.email_recipients_daily
        if not recipients:
            logger.warning("No daily email recipients in config.yaml — skipping email")
        else:
            subject = settings.subject_template_daily.format(
                date=datetime.now().strftime("%Y-%m-%d")
            )
            send_summary_email(to=recipients, subject=subject, body=body)
            result["email_sent"] = True
            logger.info("Sent daily overview email to %s", recipients)
    except Exception:
        logger.exception("Failed to send daily overview email")

    # ── Telegram ──────────────────────────────────────────────────────────────
    try:
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            logger.info("Telegram not configured — skipping")
        else:
            date_label = datetime.now().strftime("%Y-%m-%d")
            tg_text = telegram_ops.format_summary_for_telegram(
                f"📋 Daily Overview — {date_label}", body
            )
            telegram_ops.send_message(tg_text)
            result["telegram_sent"] = True
            logger.info("Sent daily overview to Telegram")
    except Exception:
        logger.exception("Failed to send daily overview to Telegram")

    logger.info("Daily overview done: %s", result)
    return result


if __name__ == "__main__":
    run()
