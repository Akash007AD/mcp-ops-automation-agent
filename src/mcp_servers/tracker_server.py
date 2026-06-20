"""
MCP Server: tracker-tools

Wraps the swappable tracker backend (Google Sheets or Notion — see
src/core/tracker.py) as MCP tools, per 02_ARCHITECTURE.md.

Run directly for stdio MCP (e.g. from a Claude Desktop config entry):
    python src/mcp_servers/tracker_server.py
"""

import sys
from pathlib import Path

# Make `from src...` imports work regardless of the working directory this
# is launched from (Claude Desktop launches servers with an arbitrary cwd).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from typing import Optional

from mcp.server.fastmcp import FastMCP

from src.core.tracker import get_tracker

mcp = FastMCP("tracker-tools")


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
    tracker = get_tracker()
    return tracker.add_entry(title, category, source_text, status, urgent)


@mcp.tool()
def list_open_entries(since: Optional[str] = None) -> list[dict]:
    """List tracker entries, optionally filtered to created_at >= since.

    Args:
        since: ISO 8601 timestamp (e.g. "2026-06-19T00:00:00+00:00"). Use
            today's midnight for a daily overview, or 7 days ago for a
            weekly digest. Omit for the full history.
    """
    tracker = get_tracker()
    return tracker.list_open_entries(since)


@mcp.tool()
def update_status(entry_id: str, status: str) -> dict:
    """Mark a tracker entry as resolved or reopen it.

    Args:
        entry_id: the id of the entry to update.
        status: "open" or "resolved".
    """
    tracker = get_tracker()
    return tracker.update_status(entry_id, status)


if __name__ == "__main__":
    mcp.run()
