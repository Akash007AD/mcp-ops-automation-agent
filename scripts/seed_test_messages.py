"""
Seed script — sends the 20 test messages from the demo plan through the
real pipeline so you get a populated daily/weekly summary without typing
each message into Slack by hand.

WHY THIS EXISTS (read before running):
slack_ops.read_messages() deliberately filters out any message with a
bot_id, so the agent never re-ingests its own summary posts (see the
safety boundary in 02_ARCHITECTURE.md). That's correct for production,
but it means if this script posts the seed messages using the bot token,
the normal hourly_intake job will NOT pick them up — Slack has no way to
post as a "regular user" without a separate user OAuth token.

So this script does two things for each message, to get you both a
demo-ready Slack channel AND populated tracker data:
  1. Posts the message text to Slack (so the channel LOOKS seeded for
     screen-recording the demo).
  2. Runs it through the exact same classify_message() + tracker.add_entry()
     calls that hourly_intake.py uses internally — so the tracker, daily
     overview, and weekly digest all see real, varied data.

Step 2 exercises everything except slack_ops.read_messages() itself
(classification, tracker writes, urgent flagging). Slack reading is
already confirmed working from your earlier "Slack channel membership: OK"
run — this just can't simultaneously prove that AND simulate 20 distinct
human senders with a single bot token.

Run (from the D:\MCP_Automation root):
    python scripts/seed_test_messages.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core import slack_ops
from src.core.llm_ops import classify_message
from src.core.tracker import get_tracker
from src.utils.logging_setup import get_logger

logger = get_logger("seed_test_messages")

MESSAGES: list[str] = [
    # Bugs
    "the dashboard chart is showing $0 for everyone even though Sarah has actual revenue logged",
    "URGENT — login page is throwing a 500 error for half our users right now, nobody can get in",
    "export to CSV button does nothing when you click it on Safari",
    "notifications are arriving like 10 minutes late, used to be instant",
    "the search bar crashes the page if you type an emoji",
    # Features
    "can we add dark mode to the dashboard? several people have asked",
    "would be great to have a \"duplicate project\" button instead of recreating from scratch every time",
    "can we get Slack notifications when someone assigns me a task",
    "it'd help a lot if we could filter the reports table by date range",
    "feature idea: bulk-export all invoices as a single zip instead of one at a time",
    # Questions
    "hey does anyone know if we still support the old API v1 endpoints or did we sunset those",
    "quick q — where do I update my billing address in the admin panel?",
    "is there a doc anywhere explaining how the onboarding flow works for new clients?",
    "who do I ping if a client wants a custom contract term added?",
    "does the free tier cap at 3 seats or 5? want to confirm before I quote a client",
    # Noise
    "lol did anyone see the office Slack emoji someone made of the CEO",
    "happy friday everyone 🎉",
    "anyone want to grab lunch around 1?",
    # Urgent / mixed
    "CRITICAL — payment processing is down, we're losing live transactions right now, need eyes on this asap",
    "client called in furious, their dashboard has been blank for 2 days and nobody followed up — need this fixed today",
]


def main() -> None:
    tracker = get_tracker()
    posted, logged, skipped, errors = 0, 0, 0, 0

    # Duplicate guard: skip any message whose exact text is already logged,
    # so re-running this script after a partial run (or by accident) doesn't
    # pile up repeat rows in the tracker.
    existing_texts = {e["source_text"] for e in tracker.list_open_entries()}

    for i, text in enumerate(MESSAGES, start=1):
        print(f"[{i}/{len(MESSAGES)}] {text[:60]}...")

        if text in existing_texts:
            print("    -> already logged, skipping")
            skipped += 1
            continue

        # 1. Post to Slack for visual/demo purposes.
        try:
            slack_ops.post_message(text, channel=slack_ops.settings.slack_requests_channel)
            posted += 1
        except Exception:
            logger.exception("Failed to post message %d to Slack", i)
            errors += 1

        # 2. Run through the real classify + log pipeline.
        try:
            classification = classify_message(text)
            tracker.add_entry(
                title=classification["title"],
                category=classification["category"],
                source_text=text,
                status="open",
                urgent=classification.get("urgent", False),
            )
            logged += 1
            print(
                f"    -> [{classification['category']}] {classification['title']}"
                f"{' (URGENT)' if classification.get('urgent') else ''}"
            )
        except Exception:
            logger.exception("Failed to classify/log message %d", i)
            errors += 1

        time.sleep(1.5)  # gentle pacing — avoids hammering Slack/Groq rate limits

    print(f"\nDone. posted={posted} logged={logged} skipped={skipped} errors={errors}")
    print("Now run: python -m src.orchestrators.daily_overview")


if __name__ == "__main__":
    main()
