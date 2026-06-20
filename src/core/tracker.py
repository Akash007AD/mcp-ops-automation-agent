"""
Tracker abstraction — the agent's "single tracker database" boundary.

Two backends implement the same interface (Google Sheets, Notion). The rest
of the system (MCP tracker server, orchestrators) only ever talks to
`get_tracker()` and the `TrackerBackend` interface — never to gspread or
notion_client directly. This is what makes the tracker swappable per
02_ARCHITECTURE.md: "the tracker is a swappable component behind the same
tool interface."
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from src.core.config import settings

VALID_CATEGORIES = {"bug", "feature", "question", "noise"}
VALID_STATUSES = {"open", "resolved"}


class TrackerBackend(ABC):
    """Common interface every tracker implementation must satisfy."""

    @abstractmethod
    def add_entry(
        self,
        title: str,
        category: str,
        source_text: str,
        status: str = "open",
        urgent: bool = False,
    ) -> dict:
        """Log a new request. Returns the created entry as a dict."""
        raise NotImplementedError

    @abstractmethod
    def list_open_entries(self, since: Optional[str] = None) -> list[dict]:
        """List entries, optionally filtered to created_at >= since (ISO 8601).

        Despite the name, this returns ALL entries created since the cutoff
        (open and resolved) so daily/weekly summaries can report resolution
        rate, not just the open backlog. Pass since=None for the full table.
        """
        raise NotImplementedError

    @abstractmethod
    def update_status(self, entry_id: str, status: str) -> dict:
        """Mark an entry resolved/open. Returns the updated entry."""
        raise NotImplementedError


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_category(category: str) -> str:
    category = category.lower().strip()
    if category not in VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category '{category}'. Must be one of {sorted(VALID_CATEGORIES)}"
        )
    return category


def _validate_status(status: str) -> str:
    status = status.lower().strip()
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of {sorted(VALID_STATUSES)}"
        )
    return status


# ──────────────────────────────────────────────────────────────────────────
# Google Sheets backend
# ──────────────────────────────────────────────────────────────────────────

SHEETS_HEADER = ["id", "title", "category", "source_text", "status", "urgent", "created_at"]


class SheetsTracker(TrackerBackend):
    """Tracker backed by a Google Sheet (via gspread + a service account).

    Sheet layout (row 1 = header):
    id | title | category | source_text | status | urgent | created_at
    """

    def __init__(self) -> None:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        creds = Credentials.from_service_account_file(
            settings.google_service_account_json, scopes=scopes
        )
        client = gspread.authorize(creds)
        self._sheet = client.open_by_key(settings.google_sheet_id).sheet1
        self._ensure_header()

    def _ensure_header(self) -> None:
        first_row = self._sheet.row_values(1)
        if first_row != SHEETS_HEADER:
            self._sheet.update("A1", [SHEETS_HEADER])

    @staticmethod
    def _row_to_entry(row: list[str]) -> dict:
        row = (row + [""] * len(SHEETS_HEADER))[: len(SHEETS_HEADER)]
        return {
            "id": row[0],
            "title": row[1],
            "category": row[2],
            "source_text": row[3],
            "status": row[4],
            "urgent": row[5].strip().lower() == "true",
            "created_at": row[6],
        }

    def add_entry(
        self,
        title: str,
        category: str,
        source_text: str,
        status: str = "open",
        urgent: bool = False,
    ) -> dict:
        category = _validate_category(category)
        status = _validate_status(status)
        entry = {
            "id": _new_id(),
            "title": title.strip(),
            "category": category,
            "source_text": source_text,
            "status": status,
            "urgent": urgent,
            "created_at": _now_iso(),
        }
        self._sheet.append_row(
            [
                entry["id"],
                entry["title"],
                entry["category"],
                entry["source_text"],
                entry["status"],
                str(entry["urgent"]),
                entry["created_at"],
            ]
        )
        return entry

    def list_open_entries(self, since: Optional[str] = None) -> list[dict]:
        rows = self._sheet.get_all_values()[1:]  # skip header
        entries = [self._row_to_entry(r) for r in rows if any(r)]
        if since:
            entries = [e for e in entries if e["created_at"] >= since]
        return entries

    def update_status(self, entry_id: str, status: str) -> dict:
        status = _validate_status(status)
        cell = self._sheet.find(entry_id, in_column=1)
        if cell is None:
            raise ValueError(f"No entry with id '{entry_id}' found")
        status_col = SHEETS_HEADER.index("status") + 1
        self._sheet.update_cell(cell.row, status_col, status)
        row = self._sheet.row_values(cell.row)
        return self._row_to_entry(row)


# ──────────────────────────────────────────────────────────────────────────
# Notion backend
# ──────────────────────────────────────────────────────────────────────────


class NotionTracker(TrackerBackend):
    """Tracker backed by a Notion database.

    Expected database properties:
      Title        (title)
      Category     (select: bug / feature / question / noise)
      Source Text  (rich_text)
      Status       (select: open / resolved)
      Urgent       (checkbox)
      Created At   (date) — in addition to Notion's built-in created_time,
                    we store this ourselves so `since` filtering is exact
                    and timezone-explicit.
    """

    def __init__(self) -> None:
        from notion_client import Client

        self._client = Client(auth=settings.notion_api_key)
        self._database_id = settings.notion_database_id

    @staticmethod
    def _page_to_entry(page: dict) -> dict:
        props = page["properties"]

        def _title(p):
            arr = p.get("title", [])
            return arr[0]["plain_text"] if arr else ""

        def _rich_text(p):
            arr = p.get("rich_text", [])
            return arr[0]["plain_text"] if arr else ""

        def _select(p):
            sel = p.get("select")
            return sel["name"] if sel else ""

        def _checkbox(p):
            return bool(p.get("checkbox", False))

        def _date(p):
            d = p.get("date")
            return d["start"] if d else ""

        return {
            "id": page["id"],
            "title": _title(props.get("Title", {})),
            "category": _select(props.get("Category", {})),
            "source_text": _rich_text(props.get("Source Text", {})),
            "status": _select(props.get("Status", {})),
            "urgent": _checkbox(props.get("Urgent", {})),
            "created_at": _date(props.get("Created At", {})),
        }

    def add_entry(
        self,
        title: str,
        category: str,
        source_text: str,
        status: str = "open",
        urgent: bool = False,
    ) -> dict:
        category = _validate_category(category)
        status = _validate_status(status)
        created_at = _now_iso()

        page = self._client.pages.create(
            parent={"database_id": self._database_id},
            properties={
                "Title": {"title": [{"text": {"content": title.strip()}}]},
                "Category": {"select": {"name": category}},
                "Source Text": {"rich_text": [{"text": {"content": source_text[:2000]}}]},
                "Status": {"select": {"name": status}},
                "Urgent": {"checkbox": urgent},
                "Created At": {"date": {"start": created_at}},
            },
        )
        return self._page_to_entry(page)

    def list_open_entries(self, since: Optional[str] = None) -> list[dict]:
        filter_payload = None
        if since:
            filter_payload = {
                "property": "Created At",
                "date": {"on_or_after": since},
            }

        results: list[dict] = []
        cursor = None
        while True:
            kwargs = {"database_id": self._database_id, "page_size": 100}
            if filter_payload:
                kwargs["filter"] = filter_payload
            if cursor:
                kwargs["start_cursor"] = cursor
            resp = self._client.databases.query(**kwargs)
            results.extend(self._page_to_entry(p) for p in resp["results"])
            if not resp.get("has_more"):
                break
            cursor = resp["next_cursor"]
        return results

    def update_status(self, entry_id: str, status: str) -> dict:
        status = _validate_status(status)
        page = self._client.pages.update(
            page_id=entry_id,
            properties={"Status": {"select": {"name": status}}},
        )
        return self._page_to_entry(page)


# ──────────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────────

_tracker_instance: Optional[TrackerBackend] = None


def get_tracker() -> TrackerBackend:
    """Returns the configured tracker backend (singleton, lazily built).

    Backend choice comes from config.yaml -> tracker.backend ("sheets" or
    "notion"). Swapping backends is a one-line config change; no other code
    in the project needs to change.
    """
    global _tracker_instance
    if _tracker_instance is not None:
        return _tracker_instance

    backend = settings.tracker_backend
    if backend == "sheets":
        settings.validate_for("sheets")
        _tracker_instance = SheetsTracker()
    elif backend == "notion":
        settings.validate_for("notion")
        _tracker_instance = NotionTracker()
    else:
        raise ValueError(
            f"Unknown tracker backend '{backend}' in config.yaml "
            f"(expected 'sheets' or 'notion')"
        )
    return _tracker_instance
