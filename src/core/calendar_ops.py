"""
Google Calendar operations — create and list events.

Uses the same service account credentials as the Google Sheets tracker
(service_account.json). The service account needs to be shared on each
calendar it should access, OR you use domain-wide delegation for G-Suite.

For a personal Google Calendar:
  1. Open calendar.google.com → Settings → [your calendar] → Share.
  2. Share with your service account email (found in service_account.json
     as "client_email") and give it "Make changes to events" permission.

Requires:
  GOOGLE_SERVICE_ACCOUNT_JSON=service_account.json  (already in .env)
  GOOGLE_CALENDAR_ID=primary                        (or a specific calendar ID)

Install: pip install google-api-python-client google-auth
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from src.core.config import settings

_service = None


def _get_service():
    global _service
    if _service is None:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        scopes = ["https://www.googleapis.com/auth/calendar"]
        creds = Credentials.from_service_account_file(
            settings.google_service_account_json, scopes=scopes
        )
        _service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return _service


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_time_max() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


def _parse_event(event: dict) -> dict:
    """Simplify a Google Calendar event object."""
    start = event.get("start", {})
    end = event.get("end", {})
    return {
        "id": event.get("id", ""),
        "summary": event.get("summary", ""),
        "description": event.get("description", ""),
        "start": start.get("dateTime") or start.get("date", ""),
        "end": end.get("dateTime") or end.get("date", ""),
        "html_link": event.get("htmlLink", ""),
        "attendees": [
            a.get("email", "") for a in event.get("attendees", [])
        ],
        "status": event.get("status", ""),
    }


def create_event(
    summary: str,
    start_datetime: str,
    end_datetime: str,
    description: Optional[str] = None,
    attendees: Optional[list[str]] = None,
    calendar_id: Optional[str] = None,
) -> dict:
    """Create a Google Calendar event.

    Args:
        summary:        event title.
        start_datetime: ISO 8601 string with timezone, e.g. "2026-06-25T10:00:00+05:30".
        end_datetime:   ISO 8601 string for event end.
        description:    optional event body / agenda.
        attendees:      optional list of attendee email addresses.
        calendar_id:    target calendar (defaults to GOOGLE_CALENDAR_ID from .env,
                        falls back to "primary").

    Returns a simplified event dict: {"id", "summary", "html_link", "start", "end"}.
    """
    service = _get_service()
    cal_id = calendar_id or settings.google_calendar_id

    body: dict = {
        "summary": summary,
        "start": {"dateTime": start_datetime},
        "end": {"dateTime": end_datetime},
    }
    if description:
        body["description"] = description
    if attendees:
        body["attendees"] = [{"email": e} for e in attendees]

    event = service.events().insert(calendarId=cal_id, body=body).execute()
    return _parse_event(event)


def list_events(
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    max_results: int = 20,
    calendar_id: Optional[str] = None,
) -> list[dict]:
    """List upcoming events from a Google Calendar.

    Args:
        time_min:    ISO 8601 lower bound (default: now).
        time_max:    ISO 8601 upper bound (default: 7 days from now).
        max_results: max number of events to return (default 20).
        calendar_id: which calendar to query (default: GOOGLE_CALENDAR_ID).

    Returns a list of simplified event dicts.
    """
    service = _get_service()
    cal_id = calendar_id or settings.google_calendar_id

    result = (
        service.events()
        .list(
            calendarId=cal_id,
            timeMin=time_min or _now_iso(),
            timeMax=time_max or _default_time_max(),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return [_parse_event(e) for e in result.get("items", [])]


def delete_event(event_id: str, calendar_id: Optional[str] = None) -> str:
    """Delete a calendar event by ID. Returns "deleted:<event_id>"."""
    service = _get_service()
    cal_id = calendar_id or settings.google_calendar_id
    service.events().delete(calendarId=cal_id, eventId=event_id).execute()
    return f"deleted:{event_id}"
