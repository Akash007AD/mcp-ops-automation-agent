"""
Quick sanity check for the tightened urgency rule in CLASSIFICATION_PROMPT
(see llm_ops.py). Re-classifies the 5 bug messages from the seed set
in isolation — no Slack posts, no tracker writes — so you can confirm the
prompt change actually changed behaviour before trusting it in a real run.

Run (from the D:\MCP_Automation root):
    python scripts/check_urgency.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.llm_ops import classify_message

BUG_MESSAGES = [
    ("the dashboard chart is showing $0 for everyone even though Sarah has actual revenue logged", False),
    ("URGENT — login page is throwing a 500 error for half our users right now, nobody can get in", True),
    ("export to CSV button does nothing when you click it on Safari", False),
    ("notifications are arriving like 10 minutes late, used to be instant", False),
    ("the search bar crashes the page if you type an emoji", False),
    ("CRITICAL — payment processing is down, we're losing live transactions right now, need eyes on this asap", True),
    ("client called in furious, their dashboard has been blank for 2 days and nobody followed up — need this fixed today", True),
]


def main() -> None:
    print(f"{'expected':<10} {'got':<10} message")
    print("-" * 90)
    mismatches = 0
    for text, expected_urgent in BUG_MESSAGES:
        result = classify_message(text)
        got_urgent = bool(result.get("urgent", False))
        flag = "  " if got_urgent == expected_urgent else "<-- MISMATCH"
        if got_urgent != expected_urgent:
            mismatches += 1
        print(f"{str(expected_urgent):<10} {str(got_urgent):<10} {text[:55]}... {flag}")

    print(f"\n{len(BUG_MESSAGES) - mismatches}/{len(BUG_MESSAGES)} matched expectations.")


if __name__ == "__main__":
    main()
