"""
MCP Server: mcp-automation (unified)

Single FastMCP process exposing ALL tools — Slack, tracker, email, Notion,
Google Calendar, and Telegram — under one server entry in claude_desktop_config.json.

Replace the three separate server entries with this one:

  "mcp-automation": {
    "command": "python",
    "args": ["D:/MCP_Automation/src/mcp_servers/unified_server.py"]
  }

Tool namespaces (all flat, names are unique):
  Slack      : read_messages, post_message, list_channels
  Tracker    : add_entry, list_open_entries, update_status
  Email      : send_summary_email
  Notion     : notion_create_page, notion_query_database, notion_update_page
  Calendar   : calendar_create_event, calendar_list_events
  Telegram   : telegram_send_message, telegram_send_to_group

Run directly for stdio MCP:
    python src/mcp_servers/unified_server.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server.fastmcp import FastMCP

from src.core import slack_ops, email_ops, notion_ops, calendar_ops, telegram_ops
from src.core.tracker import get_tracker

mcp = FastMCP("mcp-automation")

# ══════════════════════════════════════════════════════════════════════════════
# SLACK TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def read_messages(
    channel: Optional[str] = None, since_timestamp: Optional[str] = None
) -> list[dict]:
    """Fetch new messages from a Slack channel.

    Args:
        channel: channel name (e.g. "requests") or ID. Defaults to the
            configured requests channel.
        since_timestamp: Slack 'ts' cursor — only messages after this are
            returned. Omit to get the most recent 100 messages.
    """
    return slack_ops.read_messages(channel, since_timestamp)


@mcp.tool()
def post_message(text: str, channel: Optional[str] = None) -> dict:
    """Post a message to a Slack channel (used for summary/status posts only).

    Args:
        text: the message body to post.
        channel: channel name or ID. Defaults to the configured updates channel.
    """
    return slack_ops.post_message(text, channel)


@mcp.tool()
def list_channels() -> list[dict]:
    """List all Slack channels the bot is a member of.

    Returns a list of {"id", "name", "is_private"} dicts — useful for
    discovering which channels are available before reading or posting.
    """
    return slack_ops.list_channels()


# ══════════════════════════════════════════════════════════════════════════════
# TRACKER TOOLS  (Google Sheets or Notion backend — set in config.yaml)
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def add_entry(
    title: str,
    category: str,
    source_text: str,
    status: str = "open",
    urgent: bool = False,
) -> dict:
    """Log a new request to the tracker.

    Args:
        title: short summary of the request (max ~8 words).
        category: one of "bug", "feature", "question", "noise".
        source_text: the original raw message text.
        status: "open" or "resolved". Defaults to "open".
        urgent: whether this needs immediate attention.
    """
    return get_tracker().add_entry(title, category, source_text, status, urgent)


@mcp.tool()
def list_open_entries(since: Optional[str] = None) -> list[dict]:
    """List tracker entries, optionally filtered to created_at >= since.

    Args:
        since: ISO 8601 timestamp (e.g. "2026-06-19T00:00:00+00:00"). Use
            today's midnight for a daily overview, or 7 days ago for a
            weekly digest. Omit for the full history.
    """
    return get_tracker().list_open_entries(since)


@mcp.tool()
def update_status(entry_id: str, status: str) -> dict:
    """Mark a tracker entry as resolved or reopen it.

    Args:
        entry_id: the id of the entry to update.
        status: "open" or "resolved".
    """
    return get_tracker().update_status(entry_id, status)


# ══════════════════════════════════════════════════════════════════════════════
# EMAIL TOOLS  (SMTP — works with any email, any number of recipients)
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def send_summary_email(to: list[str], subject: str, body: str) -> str:
    """Send a plain-text summary email via SMTP.

    Args:
        to: list of recipient email addresses.
        subject: email subject line.
        body: plain-text email body.

    Returns a status string on success.
    """
    return email_ops.send_summary_email(to, subject, body)


# ══════════════════════════════════════════════════════════════════════════════
# NOTION TOOLS  (standalone Notion workspace operations, separate from tracker)
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def notion_create_page(
    database_id: str,
    title: str,
    properties: Optional[dict] = None,
    content: Optional[str] = None,
) -> dict:
    """Create a new page in a Notion database.

    Args:
        database_id: the Notion database ID to add the page to.
        title: page title (mapped to the database's Title property).
        properties: optional dict of additional Notion property payloads
            (e.g. {"Status": {"select": {"name": "In Progress"}}}).
        content: optional plain-text body content added as a paragraph block.

    Returns the created page's id and url.
    """
    return notion_ops.create_page(database_id, title, properties, content)


@mcp.tool()
def notion_query_database(
    database_id: str,
    filter_payload: Optional[dict] = None,
    limit: int = 50,
) -> list[dict]:
    """Query pages from any Notion database.

    Args:
        database_id: the Notion database ID to query.
        filter_payload: optional Notion filter object
            (e.g. {"property": "Status", "select": {"equals": "open"}}).
        limit: max number of pages to return (default 50, max 100).

    Returns a list of simplified page dicts: {id, title, url, properties}.
    """
    return notion_ops.query_database(database_id, filter_payload, limit)


@mcp.tool()
def notion_update_page(page_id: str, properties: dict) -> dict:
    """Update properties on an existing Notion page.

    Args:
        page_id: the ID of the Notion page to update.
        properties: Notion property payloads to update
            (e.g. {"Status": {"select": {"name": "resolved"}}}).

    Returns the updated page's id and url.
    """
    return notion_ops.update_page(page_id, properties)


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE CALENDAR TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def calendar_create_event(
    summary: str,
    start_datetime: str,
    end_datetime: str,
    description: Optional[str] = None,
    attendees: Optional[list[str]] = None,
    calendar_id: str = "primary",
) -> dict:
    """Create a Google Calendar event.

    Args:
        summary: event title.
        start_datetime: ISO 8601 datetime string (e.g. "2026-06-25T10:00:00+05:30").
        end_datetime: ISO 8601 datetime string for event end.
        description: optional event description / agenda.
        attendees: optional list of attendee email addresses.
        calendar_id: calendar to add the event to (default "primary").

    Returns {"id", "summary", "html_link", "start", "end"}.
    """
    return calendar_ops.create_event(
        summary, start_datetime, end_datetime, description, attendees, calendar_id
    )


@mcp.tool()
def calendar_list_events(
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    max_results: int = 20,
    calendar_id: str = "primary",
) -> list[dict]:
    """List upcoming Google Calendar events.

    Args:
        time_min: ISO 8601 lower bound (default: now).
        time_max: ISO 8601 upper bound (default: 7 days from now).
        max_results: max number of events to return (default 20).
        calendar_id: which calendar to query (default "primary").

    Returns a list of {"id", "summary", "start", "end", "description"} dicts.
    """
    return calendar_ops.list_events(time_min, time_max, max_results, calendar_id)


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def telegram_send_message(text: str, chat_id: Optional[str] = None) -> dict:
    """Send a Telegram message to the configured personal chat or a specific chat.

    Args:
        text: message text (supports Telegram MarkdownV2 if parse_mode is set).
        chat_id: Telegram chat ID or @username. Defaults to the configured
            TELEGRAM_CHAT_ID from .env (your personal chat with the bot).

    Returns {"message_id", "chat_id"} on success.
    """
    return telegram_ops.send_message(text, chat_id)


@mcp.tool()
def telegram_send_to_group(text: str) -> dict:
    """Send a Telegram message to the configured group/channel.

    Args:
        text: message text.

    Returns {"message_id", "chat_id"} on success.
    """
    return telegram_ops.send_to_group(text)


if __name__ == "__main__":
    mcp.run()
