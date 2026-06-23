"""
Hourly intake job.

read_messages() -> classify each with Groq -> add_entry() for each.
Urgent items additionally trigger a Telegram alert so nothing slips through.

Can also be run standalone for manual testing:
    python -m src.orchestrators.hourly_intake
"""

from __future__ import annotations

from src.core import slack_ops, state, telegram_ops
from src.core.config import settings
from src.core.llm_ops import classify_message
from src.core.tracker import get_tracker
from src.utils.logging_setup import get_logger

logger = get_logger("hourly_intake")

STATE_KEY = "last_processed_ts"


def _send_urgent_alert(title: str, source_text: str) -> None:
    """Fire a Telegram alert for an urgent item (best-effort, never raises)."""
    try:
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            return
        msg = (
            f"🔴 <b>Urgent request logged</b>\n\n"
            f"<b>{title}</b>\n\n"
            f"<i>{source_text[:300]}</i>"
        )
        telegram_ops.send_message(msg)
    except Exception:
        logger.exception("Failed to send urgent Telegram alert")


def run() -> dict:
    """Returns {"fetched": n, "logged": n, "errors": n, "urgent": n}."""
    summary = {"fetched": 0, "logged": 0, "errors": 0, "urgent": 0}

    last_ts = state.get(STATE_KEY)
    logger.info("Starting hourly intake (since_timestamp=%s)", last_ts)

    try:
        messages = slack_ops.read_messages(since_timestamp=last_ts)
    except Exception:
        logger.exception("Failed to read Slack messages — aborting this run")
        summary["errors"] += 1
        return summary

    summary["fetched"] = len(messages)
    if not messages:
        logger.info("No new messages since last run.")
        return summary

    tracker = get_tracker()
    newest_ts = last_ts

    for msg in messages:
        text = msg["text"].strip()
        if not text:
            continue
        try:
            classification = classify_message(text)
            entry = tracker.add_entry(
                title=classification["title"],
                category=classification["category"],
                source_text=text,
                status="open",
                urgent=classification.get("urgent", False),
            )
            summary["logged"] += 1

            is_urgent = classification.get("urgent", False)
            logger.info(
                "Logged [%s] %s%s",
                classification["category"],
                classification["title"],
                " (URGENT)" if is_urgent else "",
            )

            if is_urgent:
                summary["urgent"] += 1
                _send_urgent_alert(classification["title"], text)

        except Exception:
            logger.exception(
                "Failed to classify/log message ts=%s — skipping", msg["ts"]
            )
            summary["errors"] += 1
        finally:
            if newest_ts is None or msg["ts"] > newest_ts:
                newest_ts = msg["ts"]

    if newest_ts:
        state.set(STATE_KEY, newest_ts)

    logger.info("Hourly intake done: %s", summary)
    return summary


if __name__ == "__main__":
    run()
