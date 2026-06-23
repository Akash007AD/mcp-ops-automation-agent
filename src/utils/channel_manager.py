"""
Channel Manager — create, register, archive, and list Slack channels.

This utility keeps Slack and config.yaml in sync automatically.
Any channel created via this module is immediately:
  1. Created in Slack
  2. Joined by the bot
  3. Registered in config.yaml → slack.intake_channels

Usage (CLI):
    python -m src.utils.channel_manager create  <channel-name>
    python -m src.utils.channel_manager remove  <channel-name>
    python -m src.utils.channel_manager list
    python -m src.utils.channel_manager sync

Usage (Python):
    from src.utils.channel_manager import create_and_register, remove_channel, list_registered
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── project root bootstrap ────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import settings
from src.utils.logging_setup import get_logger

logger = get_logger("channel_manager")

CONFIG_PATH = PROJECT_ROOT / "config.yaml"


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_client() -> WebClient:
    return WebClient(token=settings.slack_bot_token)


def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _resolve_channel_id(client: WebClient, name: str) -> str | None:
    """Return channel ID for a given name, or None if not found."""
    name = name.lstrip("#")
    cursor = None
    while True:
        resp = client.conversations_list(
            types="public_channel,private_channel",
            cursor=cursor,
            limit=200,
            exclude_archived=False,
        )
        for ch in resp["channels"]:
            if ch["name"] == name:
                return ch["id"]
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            return None


# ── public API ────────────────────────────────────────────────────────────────

def create_and_register(channel_name: str) -> dict:
    """Create a Slack channel, join it, and register it in config.yaml.

    Args:
        channel_name: bare name, no # prefix (e.g. "feature-requests").

    Returns:
        {"channel": name, "id": slack_id, "action": "created"|"already_exists"}
    """
    channel_name = channel_name.lstrip("#").lower().replace(" ", "-")
    client = _get_client()

    # 1. Create in Slack (or detect existing)
    action = "created"
    try:
        resp = client.conversations_create(name=channel_name)
        ch_id = resp["channel"]["id"]
        logger.info("Created Slack channel #%s (%s)", channel_name, ch_id)
    except SlackApiError as e:
        if e.response["error"] == "name_taken":
            ch_id = _resolve_channel_id(client, channel_name)
            action = "already_exists"
            logger.info("Channel #%s already exists (%s)", channel_name, ch_id)
        else:
            raise

    # 2. Join the channel
    try:
        client.conversations_join(channel=ch_id)
        logger.info("Bot joined #%s", channel_name)
    except SlackApiError as e:
        logger.warning("Could not join #%s: %s", channel_name, e.response["error"])

    # 3. Register in config.yaml
    cfg = _load_config()
    cfg.setdefault("slack", {}).setdefault("intake_channels", [])
    if channel_name not in cfg["slack"]["intake_channels"]:
        cfg["slack"]["intake_channels"].append(channel_name)
        _save_config(cfg)
        logger.info("Registered #%s in config.yaml", channel_name)
    else:
        logger.info("#%s already in config.yaml — skipping", channel_name)

    return {"channel": channel_name, "id": ch_id, "action": action}


def remove_channel(channel_name: str, archive: bool = True) -> dict:
    """Remove a channel from config.yaml and optionally archive it in Slack.

    Args:
        channel_name: bare name, no # prefix.
        archive:      if True, also archives the Slack channel (default True).

    Returns:
        {"channel": name, "unregistered": bool, "archived": bool}
    """
    channel_name = channel_name.lstrip("#").lower()
    client = _get_client()

    # 1. Unregister from config.yaml
    cfg = _load_config()
    channels: list = cfg.get("slack", {}).get("intake_channels", [])
    unregistered = channel_name in channels
    if unregistered:
        channels.remove(channel_name)
        cfg["slack"]["intake_channels"] = channels
        _save_config(cfg)
        logger.info("Unregistered #%s from config.yaml", channel_name)
    else:
        logger.warning("#%s was not in config.yaml", channel_name)

    # 2. Archive in Slack
    archived = False
    if archive:
        ch_id = _resolve_channel_id(client, channel_name)
        if ch_id:
            try:
                client.conversations_archive(channel=ch_id)
                archived = True
                logger.info("Archived Slack channel #%s (%s)", channel_name, ch_id)
            except SlackApiError as e:
                logger.warning("Could not archive #%s: %s", channel_name, e.response["error"])
        else:
            logger.warning("Channel #%s not found in Slack — skipping archive", channel_name)

    return {"channel": channel_name, "unregistered": unregistered, "archived": archived}


def list_registered() -> list[str]:
    """Return all channels currently registered in config.yaml."""
    cfg = _load_config()
    return cfg.get("slack", {}).get("intake_channels", [])


def sync_config_with_slack() -> dict:
    """Verify every config.yaml channel exists in Slack and bot is a member.

    Channels missing from Slack are flagged.
    Channels the bot is not in are auto-joined.

    Returns:
        {"ok": [...], "missing": [...], "joined": [...]}
    """
    client = _get_client()
    registered = list_registered()
    ok, missing, joined = [], [], []

    for name in registered:
        ch_id = _resolve_channel_id(client, name)
        if not ch_id:
            missing.append(name)
            logger.warning("#%s is in config.yaml but not found in Slack", name)
            continue
        try:
            client.conversations_join(channel=ch_id)
            joined.append(name)
            logger.info("Auto-joined #%s", name)
        except SlackApiError as e:
            if e.response["error"] == "already_in_channel":
                ok.append(name)
            else:
                logger.warning("Could not join #%s: %s", name, e.response["error"])

    return {"ok": ok, "missing": missing, "joined": joined}


# ── MCP tool registration ─────────────────────────────────────────────────────

def register_mcp_tools(mcp) -> None:
    """Register channel management tools onto a FastMCP instance.

    Called from slack_server.py to expose these tools via MCP.
    """

    @mcp.tool()
    def create_channel(channel_name: str) -> dict:
        """Create a new Slack channel, join it, and register it for intake.

        Args:
            channel_name: bare channel name without # (e.g. "feature-requests").
        """
        return create_and_register(channel_name)

    @mcp.tool()
    def remove_channel_tool(channel_name: str, archive: bool = True) -> dict:
        """Remove a channel from intake and optionally archive it in Slack.

        Args:
            channel_name: bare channel name without #.
            archive: whether to archive the Slack channel (default True).
        """
        return remove_channel(channel_name, archive)

    @mcp.tool()
    def list_intake_channels() -> list[str]:
        """List all channels currently registered for intake in config.yaml."""
        return list_registered()

    @mcp.tool()
    def sync_channels() -> dict:
        """Sync config.yaml channels with Slack — auto-join any the bot missed."""
        return sync_config_with_slack()


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="channel_manager",
        description="Manage Slack intake channels — keeps Slack + config.yaml in sync.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="Create a channel and register it.")
    p_create.add_argument("name", help="Channel name (no # prefix)")

    p_remove = sub.add_parser("remove", help="Unregister a channel and archive it.")
    p_remove.add_argument("name", help="Channel name (no # prefix)")
    p_remove.add_argument("--no-archive", action="store_true", help="Skip Slack archive")

    sub.add_parser("list", help="List registered intake channels.")
    sub.add_parser("sync", help="Sync config.yaml channels with Slack membership.")

    args = parser.parse_args()

    if args.cmd == "create":
        result = create_and_register(args.name)
        print(f"✅ #{result['channel']} ({result['id']}) — {result['action']}")

    elif args.cmd == "remove":
        result = remove_channel(args.name, archive=not args.no_archive)
        print(f"✅ #{result['channel']} — unregistered={result['unregistered']}, archived={result['archived']}")

    elif args.cmd == "list":
        channels = list_registered()
        if channels:
            print("Registered intake channels:")
            for ch in channels:
                print(f"  • #{ch}")
        else:
            print("No channels registered in config.yaml")

    elif args.cmd == "sync":
        result = sync_config_with_slack()
        print(f"✅ ok={result['ok']} | joined={result['joined']} | missing={result['missing']}")


if __name__ == "__main__":
    _cli()
