"""
MCP Server: email-tools

Wraps Resend (src/core/email_ops.py) as an MCP tool, per
02_ARCHITECTURE.md. Recipients always come from config.yaml — this tool
does not accept arbitrary recipient discovery.

Run directly for stdio MCP (e.g. from a Claude Desktop config entry):
    python src/mcp_servers/email_server.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server.fastmcp import FastMCP

from src.core import email_ops

mcp = FastMCP("email-tools")


@mcp.tool()
def send_summary_email(to: list[str], subject: str, body: str) -> str:
    """Send a plain-text summary email.

    Args:
        to: recipient email addresses.
        subject: email subject line.
        body: plain-text email body.

    Returns the provider's message id on success.
    """
    return email_ops.send_summary_email(to, subject, body)


if __name__ == "__main__":
    mcp.run()
