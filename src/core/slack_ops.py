"""
Slack operations — thin wrapper around the Slack Web API.

Per 02_ARCHITECTURE.md safety boundary: this module is read-only on Slack
except for posting the agent's own summary/status messages. It never edits
or deletes other users' messages, and never auto-replies to a requester
directly.

Changes from v1:
  - read_messages() now filters bot messages (bot_id present).
  - list_channels() added — returns all channels the bot is a member of.
  - post_message() / read_messages() both accept any channel, not just
    the two hardcoded in config.
"""

from __future__ import annotations

from typing import Optional

from src.core.config import settings

_client = None


def _get_client():
    global _client
    if _client is None:
        from slack_sdk import WebClient

        settings.validate_for("slack")
        _client = WebClient(token=settings.slack_bot_token)
    return _client


def _resolve_channel_id(client, channel: str) -> str:
    """Accept a channel ID (C0123...) or name and resolve to an ID."""
    if channel.startswith("C") and len(channel) >= 9:
        return channel

    name = channel.lstrip("#")
    cursor = None
    while True:
        resp = client.conversations_list(
            types="public_channel,private_channel", cursor=cursor, limit=200
        )
        for ch in resp["channels"]:
            if ch["name"] == name:
                return ch["id"]
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    raise ValueError(f"Could not find Slack channel '{channel}'")


def check_bot_membership() -> None:
    """Verify the bot is a member of all configured channels at startup.

    Checks every channel in slack.intake_channels (config.yaml) plus the
    updates_channel. Raises RuntimeError listing all missing channels so
    the problem is obvious at launch instead of mid-run.
    """
    client = _get_client()
    bot_id = client.auth_test()["user_id"]

    # Build the full set of channels to verify: all intake + updates.
    all_channels = list(settings.slack_intake_channels)
    if settings.slack_updates_channel not in all_channels:
        all_channels.append(settings.slack_updates_channel)

    problems: list[str] = []

    for channel in all_channels:
        try:
            channel_id = _resolve_channel_id(client, channel)
        except ValueError:
            problems.append(
                f"  - Channel '{channel}' not found. "
                f"Check slack.intake_channels / slack.updates_channel in config.yaml."
            )
            continue

        cursor = None
        found = False
        while not found:
            resp = client.conversations_members(channel=channel_id, cursor=cursor, limit=200)
            if bot_id in resp["members"]:
                found = True
                break
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        if not found:
            problems.append(
                f"  - Bot is NOT in #{channel}. "
                f"Run /invite @<your-bot-name> in that channel."
            )

    if problems:
        raise RuntimeError(
            "Slack channel membership check failed:\n" + "\n".join(problems)
        )


def list_channels() -> list[dict]:
    """Return all Slack channels the bot is a member of.

    Returns a list of {"id", "name", "is_private"} dicts.
    Useful for discovering available channels before reading or posting.
    """
    client = _get_client()
    cursor = None
    channels: list[dict] = []

    while True:
        resp = client.conversations_list(
            types="public_channel,private_channel",
            cursor=cursor,
            limit=200,
            exclude_archived=True,
        )
        for ch in resp["channels"]:
            if ch.get("is_member"):
                channels.append({
                    "id": ch["id"],
                    "name": ch["name"],
                    "is_private": ch.get("is_private", False),
                })
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    return channels


def read_messages(
    channel: Optional[str] = None,
    since_timestamp: Optional[str] = None,
) -> list[dict]:
    """Fetch new human messages from a channel.

    Filters out:
      - Bot messages (bot_id present in the message).
      - Message subtypes (channel joins, edits, etc.).

    Args:
        channel:         channel name or ID. Defaults to SLACK_REQUESTS_CHANNEL.
        since_timestamp: Slack 'ts' cursor — only messages after this are
                         returned. None = last 100 messages.

    Returns a list of {"ts", "user", "text"} dicts, oldest first.
    """
    client = _get_client()
    channel = channel or settings.slack_requests_channel
    channel_id = _resolve_channel_id(client, channel)

    kwargs: dict = {"channel": channel_id, "limit": 100}
    if since_timestamp:
        kwargs["oldest"] = since_timestamp

    resp = client.conversations_history(**kwargs)
    messages = [
        {"ts": m["ts"], "user": m.get("user", "unknown"), "text": m.get("text", "")}
        for m in resp["messages"]
        if "subtype" not in m and "bot_id" not in m  # filter bots + system messages
    ]
    messages.reverse()  # Slack returns newest-first; return chronological
    return messages


def post_message(text: str, channel: Optional[str] = None) -> dict:
    """Post a message to a Slack channel.

    Args:
        text:    message body.
        channel: channel name or ID. Defaults to SLACK_UPDATES_CHANNEL.

    Returns {"ts", "channel"} on success.
    """
    client = _get_client()
    channel = channel or settings.slack_updates_channel
    channel_id = _resolve_channel_id(client, channel)

    resp = client.chat_postMessage(channel=channel_id, text=text)
    return {"ts": resp["ts"], "channel": resp["channel"]}


def read_messages_all_intake_channels(
    since_timestamp: Optional[str] = None,
) -> list[dict]:
    """Read messages from ALL channels listed in slack.intake_channels (config.yaml).

    Each message is tagged with a "channel" key so the intake job knows
    where it came from. Failures on individual channels are logged and
    skipped — a dead channel doesn't block the rest.

    Args:
        since_timestamp: Slack 'ts' cursor applied to every channel.
                         Pass a per-channel cursor from state.py for
                         accurate deduplication (see hourly_intake.py).

    Returns a combined list of {"ts", "user", "text", "channel"} dicts,
    sorted oldest-first across all channels.
    """
    from src.utils.logging_setup import get_logger
    logger = get_logger("slack_ops")

    all_messages: list[dict] = []

    for channel in settings.slack_intake_channels:
        try:
            msgs = read_messages(channel=channel, since_timestamp=since_timestamp)
            for m in msgs:
                m["channel"] = channel
            all_messages.extend(msgs)
            logger.debug("Read %d messages from #%s", len(msgs), channel)
        except Exception:
            logger.exception(
                "Failed to read channel '#%s' — skipping this channel this run",
                channel,
            )

    # Re-sort: each channel's messages came back oldest-first independently,
    # but across channels the ts values may interleave.
    all_messages.sort(key=lambda m: m["ts"])
    return all_messages
