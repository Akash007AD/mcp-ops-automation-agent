"""
Central configuration loader.

Loads environment variables from .env (secrets/tokens) and merges with
config.yaml (non-secret settings: tracker backend, email recipients,
subject templates, schedule timings).

Every other module imports `settings` from here — never reads os.environ
or config.yaml directly.

v2 additions:
  - SMTP email (replaces Resend)
  - Google Calendar
  - Telegram bot
  - Multi-recipient email groups (daily, weekly, alerts, external)
  - GOOGLE_CALENDAR_ID
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

load_dotenv(dotenv_path=ENV_PATH)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path.name} at {path}. "
            f"Copy config.example.yaml to config.yaml and fill it in."
        )
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Settings:
    """Thin wrapper exposing config.yaml + .env as one object."""

    def __init__(self) -> None:
        self._yaml = _load_yaml(CONFIG_PATH)

        # ── Tracker ──────────────────────────────────────────────────────────
        tracker_cfg = self._yaml.get("tracker", {})
        self.tracker_backend: str = tracker_cfg.get("backend", "sheets")

        # Google Sheets
        self.google_service_account_json: str = os.environ.get(
            "GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json"
        )
        self.google_sheet_id: str = os.environ.get("GOOGLE_SHEET_ID", "")

        # Notion (tracker backend OR standalone workspace integration)
        self.notion_api_key: str = os.environ.get("NOTION_API_KEY", "")
        self.notion_database_id: str = os.environ.get("NOTION_DATABASE_ID", "")

        # ── Slack ─────────────────────────────────────────────────────────────
        slack_cfg = self._yaml.get("slack", {})
        self.slack_bot_token: str = os.environ.get("SLACK_BOT_TOKEN", "")
        # Multi-channel intake: list from config.yaml.
        # Falls back to SLACK_REQUESTS_CHANNEL env var for backward compat.
        self.slack_intake_channels: list[str] = slack_cfg.get(
            "intake_channels",
            [os.environ.get("SLACK_REQUESTS_CHANNEL", "requests")],
        )
        # Keep slack_requests_channel as an alias pointing to the first
        # intake channel so existing code that references it doesn't break.
        self.slack_requests_channel: str = (
            self.slack_intake_channels[0] if self.slack_intake_channels else "requests"
        )
        self.slack_updates_channel: str = slack_cfg.get(
            "updates_channel",
            os.environ.get("SLACK_UPDATES_CHANNEL", "team-updates"),
        )

        # ── Email (SMTP) ──────────────────────────────────────────────────────
        email_cfg = self._yaml.get("email", {})
        recipients_cfg = email_cfg.get("recipients", {})

        self.smtp_host: str = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port: int = int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_username: str = os.environ.get("SMTP_USERNAME", "")
        self.smtp_password: str = os.environ.get("SMTP_PASSWORD", "")

        self.email_from_address: str = email_cfg.get(
            "from_address", os.environ.get("EMAIL_FROM_ADDRESS", "")
        )
        self.email_from_name: str = email_cfg.get(
            "from_name", os.environ.get("EMAIL_FROM_NAME", "Team Ops Agent")
        )

        # Recipient groups — all come from config.yaml (not discoverable by agent)
        self.email_recipients_daily: list[str] = recipients_cfg.get("daily", [])
        self.email_recipients_weekly: list[str] = recipients_cfg.get("weekly", [])
        self.email_recipients_alerts: list[str] = recipients_cfg.get("alerts", [])
        self.email_recipients_external: list[str] = recipients_cfg.get("external", [])

        # Subject templates
        subject_tmpl = email_cfg.get("subject_templates", {})
        self.subject_template_daily: str = subject_tmpl.get(
            "daily", "Daily Request Overview — {date}"
        )
        self.subject_template_weekly: str = subject_tmpl.get(
            "weekly", "Weekly Digest — {week_range}"
        )
        self.subject_template_alert: str = subject_tmpl.get(
            "alert", "⚠️ Urgent Alert — {date}"
        )

        # ── Google Calendar ───────────────────────────────────────────────────
        self.google_calendar_id: str = os.environ.get(
            "GOOGLE_CALENDAR_ID", "primary"
        )

        # ── Telegram ──────────────────────────────────────────────────────────
        self.telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id: str = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.telegram_group_id: str = os.environ.get("TELEGRAM_GROUP_ID", "")

        # ── Groq (classification + summarisation LLM) ─────────────────────────
        self.groq_api_key: str = os.environ.get("GROQ_API_KEY", "")
        self.groq_model: str = os.environ.get(
            "GROQ_MODEL", "llama-3.3-70b-versatile"
        )

        # ── Schedule ──────────────────────────────────────────────────────────
        self.daily_summary_time: str = os.environ.get("DAILY_SUMMARY_TIME", "18:00")
        self.weekly_summary_day: str = os.environ.get(
            "WEEKLY_SUMMARY_DAY", "monday"
        ).lower()
        self.weekly_summary_time: str = os.environ.get(
            "WEEKLY_SUMMARY_TIME", "09:00"
        )

    # ─────────────────────────────────────────────────────────────────────────

    def validate_for(self, *required: str) -> None:
        """Raise a clear error if required settings are missing or placeholder.

        Usage: settings.validate_for("slack", "smtp") before running a job
        that needs those integrations. Fails at startup with a clear message
        instead of crashing mid-run with a cryptic API error.
        """
        problems: list[str] = []

        def _missing(value: str) -> bool:
            return not value or any(
                value.startswith(m)
                for m in ("your_", "xoxb-your", "sk-your")
            )

        checks: dict[str, list[tuple[str, str]]] = {
            "slack": [("SLACK_BOT_TOKEN", self.slack_bot_token)],
            "groq": [("GROQ_API_KEY", self.groq_api_key)],
            "smtp": [
                ("SMTP_USERNAME", self.smtp_username),
                ("SMTP_PASSWORD", self.smtp_password),
                ("EMAIL_FROM_ADDRESS", self.email_from_address),
            ],
            "sheets": [("GOOGLE_SHEET_ID", self.google_sheet_id)],
            "notion": [
                ("NOTION_API_KEY", self.notion_api_key),
                ("NOTION_DATABASE_ID", self.notion_database_id),
            ],
            "calendar": [
                ("GOOGLE_SERVICE_ACCOUNT_JSON", self.google_service_account_json),
            ],
            "telegram": [("TELEGRAM_BOT_TOKEN", self.telegram_bot_token)],
        }

        for name in required:
            for env_name, value in checks.get(name, []):
                if _missing(value):
                    problems.append(f"{env_name} is not set in .env")

        if problems:
            raise RuntimeError(
                "Configuration incomplete:\n  - " + "\n  - ".join(problems)
            )


settings = Settings()
