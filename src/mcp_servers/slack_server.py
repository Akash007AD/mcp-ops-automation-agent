"""
MCP Server: slack-tools

Wraps the Slack Web API (src/core/slack_ops.py) as MCP tools, per
02_ARCHITECTURE.md. Read-only on Slack except for posting the agent's own
messages — see the safety boundary documented there.

Run directly for stdio MCP (e.g. from a Claude Desktop config entry):
    python src/mcp_servers/slack_server.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from typing import Optional

from mcp.server.fastmcp import FastMCP

from src.core import slack_ops

mcp = FastMCP("slack-tools")


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
        channel: channel name or ID. Defaults to the configured updates
            channel.
    """
    return slack_ops.post_message(text, channel)


if __name__ == "__main__":
    mcp.run()
