"""
Central configuration loader.

Loads environment variables from .env (secrets, tokens, IDs) and merges
them with config.yaml (non-secret settings: tracker backend choice, email
recipients, subject templates, schedule timings).

Every other module should import `settings` from here instead of reading
os.environ or config.yaml directly — keeps configuration in one place.
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
            f"Missing {path.name} at {path}. Copy config.example.yaml to "
            f"config.yaml and fill it in."
        )
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Settings:
    """Thin wrapper exposing config.yaml + .env as one object."""

    def __init__(self) -> None:
        self._yaml = _load_yaml(CONFIG_PATH)

        # ── Tracker ──────────────────────────────────────────────
        tracker_cfg = self._yaml.get("tracker", {})
        self.tracker_backend: str = tracker_cfg.get("backend", "sheets")

        # Google Sheets
        self.google_service_account_json: str = os.environ.get(
            "GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json"
        )
        self.google_sheet_id: str = os.environ.get("GOOGLE_SHEET_ID", "")

        # Notion
        self.notion_api_key: str = os.environ.get("NOTION_API_KEY", "")
        self.notion_database_id: str = os.environ.get("NOTION_DATABASE_ID", "")

        # ── Slack ────────────────────────────────────────────────
        self.slack_bot_token: str = os.environ.get("SLACK_BOT_TOKEN", "")
        self.slack_requests_channel: str = os.environ.get(
            "SLACK_REQUESTS_CHANNEL", "requests"
        )
        self.slack_updates_channel: str = os.environ.get(
            "SLACK_UPDATES_CHANNEL", "team-updates"
        )

        # ── Email (Resend) ───────────────────────────────────────
        email_cfg = self._yaml.get("email", {})
        self.resend_api_key: str = os.environ.get("RESEND_API_KEY", "")
        self.email_from_address: str = email_cfg.get(
            "from_address", os.environ.get("EMAIL_FROM_ADDRESS", "")
        )
        self.email_from_name: str = email_cfg.get(
            "from_name", os.environ.get("EMAIL_FROM_NAME", "Team Ops Agent")
        )
        self.email_recipients_daily: list[str] = (
            email_cfg.get("recipients", {}).get("daily", [])
        )
        self.email_recipients_weekly: list[str] = (
            email_cfg.get("recipients", {}).get("weekly", [])
        )
        self.subject_template_daily: str = email_cfg.get(
            "subject_templates", {}
        ).get("daily", "Daily Request Overview — {date}")
        self.subject_template_weekly: str = email_cfg.get(
            "subject_templates", {}
        ).get("weekly", "Weekly Digest — {week_range}")

        # ── Groq (classification + summarisation LLM) ───────────
        self.groq_api_key: str = os.environ.get("GROQ_API_KEY", "")
        self.groq_model: str = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

        # ── Schedule ─────────────────────────────────────────────
        self.daily_summary_time: str = os.environ.get("DAILY_SUMMARY_TIME", "18:00")
        self.weekly_summary_day: str = os.environ.get(
            "WEEKLY_SUMMARY_DAY", "monday"
        ).lower()
        self.weekly_summary_time: str = os.environ.get(
            "WEEKLY_SUMMARY_TIME", "09:00"
        )

    def validate_for(self, *required: str) -> None:
        """Raise a clear error if required settings are missing/placeholder.

        Usage: settings.validate_for("slack", "groq") before running a job
        that needs those integrations, so failures are obvious at startup
        instead of as a cryptic API error mid-run.
        """
        placeholder_markers = ("your_", "xoxb-your", "")
        problems: list[str] = []

        def _is_placeholder(value: str) -> bool:
            return any(value.startswith(m) for m in placeholder_markers if m) or value == ""

        checks = {
            "slack": [("SLACK_BOT_TOKEN", self.slack_bot_token)],
            "groq": [("GROQ_API_KEY", self.groq_api_key)],
            "resend": [("RESEND_API_KEY", self.resend_api_key)],
            "sheets": [
                ("GOOGLE_SHEET_ID", self.google_sheet_id),
            ],
            "notion": [
                ("NOTION_API_KEY", self.notion_api_key),
                ("NOTION_DATABASE_ID", self.notion_database_id),
            ],
        }

        for name in required:
            for env_name, value in checks.get(name, []):
                if _is_placeholder(value):
                    problems.append(f"{env_name} is not set in .env")

        if problems:
            raise RuntimeError(
                "Configuration incomplete:\n  - " + "\n  - ".join(problems)
            )


settings = Settings()
