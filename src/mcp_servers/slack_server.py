"""
MCP Server: slack-tools

Wraps the Slack Web API (src/core/slack_ops.py) and channel management
(src/utils/channel_manager.py) as MCP tools.

Exposed tools:
  - read_messages       — fetch messages from a channel
  - post_message        — post a message to a channel
  - list_channels       — list channels the bot is a member of
  - create_channel      — create + register a new intake channel
  - remove_channel_tool — unregister + archive a channel
  - list_intake_channels — list channels registered in config.yaml
  - sync_channels       — sync config.yaml membership with Slack

Run directly for stdio MCP (e.g. from Claude Desktop config):
    python src/mcp_servers/slack_server.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from typing import Optional

from mcp.server.fastmcp import FastMCP

from src.core import slack_ops
from src.utils.channel_manager import register_mcp_tools

mcp = FastMCP("slack-tools")


@mcp.tool()
def read_messages(
    channel: Optional[str] = None, since_timestamp: Optional[str] = None
) -> list[dict]:
    """Fetch new messages from a Slack channel.

    Args:
        channel: channel name (e.g. "new-channel") or ID. Defaults to the
            configured requests channel.
        since_timestamp: Slack 'ts' cursor — only messages after this are
            returned. Omit to get the most recent 100 messages.
    """
    return slack_ops.read_messages(channel, since_timestamp)


@mcp.tool()
def post_message(text: str, channel: Optional[str] = None) -> dict:
    """Post a message to a Slack channel.

    Args:
        text: the message body to post.
        channel: channel name or ID. Defaults to the configured updates channel.
    """
    return slack_ops.post_message(text, channel)


@mcp.tool()
def list_channels() -> list[dict]:
    """List all Slack channels the bot is currently a member of."""
    return slack_ops.list_channels()


# Register channel management tools (create, remove, list, sync)
register_mcp_tools(mcp)


if __name__ == "__main__":
    mcp.run()
