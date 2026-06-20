"""
Email operations — Resend backend (chosen for its simpler SDK, see
06_EMAIL_CONFIG.md). Recipient lists are NOT discoverable or settable by
the agent itself — they only ever come from config.yaml, per the
02_ARCHITECTURE.md trust boundary ("the agent cannot add or discover new
recipients on its own").
"""

from __future__ import annotations

from src.core.config import settings


def send_summary_email(to: list[str], subject: str, body: str) -> str:
    """Send a plain-text summary email via Resend.

    Args:
        to: recipient list (must come from config.yaml, never user input).
        subject: email subject line.
        body: plain-text email body.

    Returns the Resend message id.
    """
    import resend

    settings.validate_for("resend")
    resend.api_key = settings.resend_api_key

    from_field = f"{settings.email_from_name} <{settings.email_from_address}>"

    response = resend.Emails.send(
        {
            "from": from_field,
            "to": to,
            "subject": subject,
            "text": body,
        }
    )
    return response["id"]
