"""
Email operations — SMTP backend.

Replaces the Resend backend. SMTP works with any Gmail (or other provider)
account and can send to any recipient — no domain verification required.

Setup:
  1. Enable 2FA on your Google account.
  2. Go to myaccount.google.com → Security → App Passwords.
  3. Create an App Password for "Mail" → use that 16-char password as SMTP_PASSWORD.
  4. Fill SMTP_* keys in .env (see .env.example).

Recipient lists come from config.yaml / caller — this module sends wherever
it's told. The orchestrators enforce the "recipients from config only" rule.
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.core.config import settings


def send_summary_email(to: list[str], subject: str, body: str) -> str:
    """Send a plain-text summary email via SMTP.

    Args:
        to:      list of recipient email addresses.
        subject: email subject line.
        body:    plain-text email body.

    Returns a status string like "sent:3_recipients".
    Raises RuntimeError (with a clear message) on delivery failure.
    """
    settings.validate_for("smtp")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.email_from_name} <{settings.email_from_address}>"
    msg["To"] = ", ".join(to)
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(settings.email_from_address, to, msg.as_string())
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError(
            "SMTP authentication failed. Check SMTP_USERNAME and SMTP_PASSWORD in .env. "
            "For Gmail, use an App Password (not your account password). "
            f"Original error: {exc}"
        ) from exc
    except smtplib.SMTPException as exc:
        raise RuntimeError(f"SMTP delivery failed: {exc}") from exc

    return f"sent:{len(to)}_recipients"


def send_alert_email(subject: str, body: str) -> str:
    """Convenience wrapper — sends to the configured alert recipients."""
    recipients = settings.email_recipients_alerts
    if not recipients:
        return "skipped:no_alert_recipients_configured"
    return send_summary_email(recipients, subject, body)
