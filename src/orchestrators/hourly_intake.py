"""
Hourly intake job.

read_messages() -> classify each with Groq -> add_entry() for each.
This is the "someone scrolls Slack" replacement — runs every hour via
scheduler.py (or cron), per 02_ARCHITECTURE.md trigger schedule.

Can also be run standalone for manual testing:
    python -m src.orchestrators.hourly_intake
"""

from __future__ import annotations

from src.core import slack_ops, state
from src.core.llm_ops import classify_message
from src.core.tracker import get_tracker
from src.utils.logging_setup import get_logger

logger = get_logger("hourly_intake")

STATE_KEY = "last_processed_ts"


def run() -> dict:
    """Returns a small summary dict: {"fetched": n, "logged": n, "errors": n}."""
    summary = {"fetched": 0, "logged": 0, "errors": 0}

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
            tracker.add_entry(
                title=classification["title"],
                category=classification["category"],
                source_text=text,
                status="open",
                urgent=classification.get("urgent", False),
            )
            summary["logged"] += 1
            logger.info(
                "Logged [%s] %s%s",
                classification["category"],
                classification["title"],
                " (URGENT)" if classification.get("urgent") else "",
            )
        except Exception:
            logger.exception("Failed to classify/log message ts=%s — skipping", msg["ts"])
            summary["errors"] += 1
        finally:
            # Advance the cursor even on a per-message failure so a single
            # bad message can't permanently block the queue.
            if newest_ts is None or msg["ts"] > newest_ts:
                newest_ts = msg["ts"]

    if newest_ts:
        state.set(STATE_KEY, newest_ts)

    logger.info("Hourly intake done: %s", summary)
    return summary


if __name__ == "__main__":
    run()
