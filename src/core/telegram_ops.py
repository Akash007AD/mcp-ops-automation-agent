"""
Telegram operations — send messages via the Telegram Bot API.

Setup (one-time, ~3 minutes):
  1. Open Telegram → search @BotFather → /newbot → follow prompts.
     Copy the bot token → TELEGRAM_BOT_TOKEN in .env.
  2. Personal chat ID:
       a. Start a conversation with your new bot (send it /start).
       b. Visit https://api.telegram.org/bot<TOKEN>/getUpdates
          Look for "chat":{"id": <NUMBER>} in the result.
       c. Set TELEGRAM_CHAT_ID=<NUMBER> in .env.
  3. Group chat ID (optional):
       a. Add your bot to the group.
       b. Send a message in the group, then check getUpdates again.
          Group IDs are negative numbers, e.g. -1001234567890.
       c. Set TELEGRAM_GROUP_ID=<NUMBER> in .env.

Supports plain text and HTML formatting (parse_mode="HTML").

Install: pip install httpx
"""

from __future__ import annotations

from typing import Optional

import httpx

from src.core.config import settings

_BASE = "https://api.telegram.org/bot{token}/{method}"


def _api(method: str, payload: dict) -> dict:
    token = settings.telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    url = _BASE.format(token=token, method=method)
    resp = httpx.post(url, json=payload, timeout=20)
    data = resp.json()

    if not data.get("ok"):
        raise RuntimeError(
            f"Telegram API error [{method}]: {data.get('description', 'unknown error')}"
        )
    return data["result"]


def send_message(
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
) -> dict:
    """Send a Telegram message to a chat.

    Args:
        text:       message text. Supports HTML tags when parse_mode="HTML"
                    (<b>bold</b>, <i>italic</i>, <code>code</code>).
        chat_id:    Telegram chat ID or @username. Defaults to
                    TELEGRAM_CHAT_ID from .env (your personal chat).
        parse_mode: "HTML" (default) or "Markdown" or "" for plain text.

    Returns {"message_id", "chat_id"}.
    """
    target = str(chat_id or settings.telegram_chat_id)
    if not target:
        raise RuntimeError(
            "No chat_id provided and TELEGRAM_CHAT_ID is not set in .env"
        )

    payload: dict = {"chat_id": target, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode

    result = _api("sendMessage", payload)
    return {
        "message_id": result["message_id"],
        "chat_id": result["chat"]["id"],
    }


def send_to_group(text: str, parse_mode: str = "HTML") -> dict:
    """Send a message to the configured Telegram group/channel.

    Args:
        text:       message text.
        parse_mode: "HTML" (default) or "Markdown" or "".

    Returns {"message_id", "chat_id"}.
    """
    group_id = settings.telegram_group_id
    if not group_id:
        raise RuntimeError("TELEGRAM_GROUP_ID is not set in .env")
    return send_message(text, chat_id=group_id, parse_mode=parse_mode)


def send_alert(text: str) -> dict:
    """Convenience wrapper — sends a plain-text alert to personal chat."""
    return send_message(text, parse_mode="")


def format_summary_for_telegram(title: str, body: str) -> str:
    """Format a summary message with basic HTML for Telegram."""
    safe_body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"<b>{title}</b>\n\n{safe_body}"
