"""
Slack operations — thin wrapper around the Slack Web API.

Per 02_ARCHITECTURE.md safety boundary: this module is read-only on Slack
except for posting the agent's own summary/status messages. It never edits
or deletes other users' messages, and never auto-replies to a requester
directly (parked for v2, see 04_IDEAS_AND_NOTES.md).
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
    """Accepts a channel ID (C0123...) or a bare/with-# name and resolves
    it to a channel ID, since conversations.history requires an ID."""
    if channel.startswith("C") and channel.isupper():
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
    """Verify the bot is a member of both configured channels at startup.

    Raises RuntimeError with a clear fix message if either channel is
    missing — so the problem surfaces immediately at launch instead of as a
    cryptic 'not_in_channel' error mid-run.

    Call this once from scheduler.py before entering the run loop.
    """
    client = _get_client()
    channels_to_check = {
        "requests  (SLACK_REQUESTS_CHANNEL)": settings.slack_requests_channel,
        "updates   (SLACK_UPDATES_CHANNEL)": settings.slack_updates_channel,
    }
    problems: list[str] = []

    for label, channel in channels_to_check.items():
        try:
            channel_id = _resolve_channel_id(client, channel)
        except ValueError:
            problems.append(
                f"  - Channel '{channel}' not found. Check SLACK_REQUESTS_CHANNEL / "
                f"SLACK_UPDATES_CHANNEL in .env match real channel names."
            )
            continue

        # conversations_members is the reliable membership check.
        cursor = None
        bot_id = client.auth_test()["user_id"]
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
                f"  - Bot is NOT in #{channel} ({label}). "
                f"Run: /invite @<your-bot-name> in that channel."
            )

    if problems:
        raise RuntimeError(
            "Slack channel membership check failed:\n" + "\n".join(problems)
        )


def read_messages(channel: Optional[str] = None, since_timestamp: Optional[str] = None) -> list[dict]:
    """Fetch new messages from a channel.

    Args:
        channel: channel name or ID. Defaults to settings.slack_requests_channel.
        since_timestamp: Slack 'ts' cursor (epoch seconds, as string) — only
            messages strictly after this are returned. None = last 100 messages.

    Returns a list of {"ts", "user", "text"} dicts, oldest first, with bot
    messages and message subtypes (joins, edits, etc.) filtered out so the
    classifier only sees genuine user requests.
    """
    client = _get_client()
    channel = channel or settings.slack_requests_channel
    channel_id = _resolve_channel_id(client, channel)

    kwargs = {"channel": channel_id, "limit": 100}
    if since_timestamp:
        kwargs["oldest"] = since_timestamp

    resp = client.conversations_history(**kwargs)
    messages = [
        {"ts": m["ts"], "user": m.get("user", "unknown"), "text": m.get("text", "")}
        for m in resp["messages"]
        if "subtype" not in m 
    ]
    messages.reverse()  # Slack returns newest-first; we want chronological order
    return messages


def post_message(text: str, channel: Optional[str] = None) -> dict:
    """Post a message (summary or alert) to a Slack channel.

    Args:
        text: message body.
        channel: channel name or ID. Defaults to settings.slack_updates_channel.

    Returns {"ts": ..., "channel": ...} on success.
    """
    client = _get_client()
    channel = channel or settings.slack_updates_channel
    channel_id = _resolve_channel_id(client, channel)

    resp = client.chat_postMessage(channel=channel_id, text=text)
    return {"ts": resp["ts"], "channel": resp["channel"]}
