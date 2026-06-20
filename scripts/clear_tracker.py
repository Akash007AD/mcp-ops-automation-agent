"""
One-off admin script: clears all rows from the active tracker (Sheets or
Notion) except the header, so you can re-run seed_test_messages.py against
a clean slate.

DESTRUCTIVE — wipes every row in the configured tracker. Requires typing
"yes" to confirm before it touches anything.

Run (from the D:\MCP_Automation root):
    python scripts/clear_tracker.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import settings
from src.core.tracker import SHEETS_HEADER, get_tracker


def main() -> None:
    tracker = get_tracker()
    backend = settings.tracker_backend

    confirm = input(
        f"This will permanently delete ALL rows from the '{backend}' tracker. "
        f"Type 'yes' to continue: "
    )
    if confirm.strip().lower() != "yes":
        print("Aborted — no changes made.")
        return

    if backend == "sheets":
        # SheetsTracker doesn't expose a public clear() — this is a deliberate
        # one-off admin script, so reaching into the private _sheet attribute
        # is acceptable here (don't do this in application code).
        tracker._sheet.clear()
        tracker._sheet.update("A1", [SHEETS_HEADER])
        print("Cleared all rows from the Google Sheet. Header row restored.")
    elif backend == "notion":
        entries = tracker.list_open_entries()
        for e in entries:
            tracker._client.pages.update(page_id=e["id"], archived=True)
        print(f"Archived {len(entries)} pages from the Notion database.")
    else:
        print(f"Unknown backend '{backend}' — nothing done.")


if __name__ == "__main__":
    main()
