"""
Scheduler — wires the three jobs onto their trigger schedule and runs
until interrupted (Ctrl+C or process signal).

Schedule:
  - Hourly intake:   every hour, on the hour
  - Daily overview:  daily at settings.daily_summary_time (default 18:00)
  - Weekly digest:   every Monday at settings.weekly_summary_time (default 09:00)

Run:
    python scheduler.py

Per 03_BUILD_PLAN.md Day 10: each job is wrapped in a top-level try/except
so a crash in one job never kills the scheduler loop. Failures are logged
with full tracebacks; the next scheduled run still fires normally.

Timezone note: `schedule` uses local system time. If you deploy to a server
in a different timezone, set the TZ environment variable before running, or
replace the `schedule` calls with a timezone-aware library like APScheduler.
"""

from __future__ import annotations

import time

import schedule

from src.core import slack_ops
from src.core.config import settings
from src.utils.logging_setup import get_logger

logger = get_logger("scheduler")


def _run_hourly_intake() -> None:
    try:
        from src.orchestrators.hourly_intake import run
        result = run()
        logger.info("hourly_intake finished: %s", result)
    except Exception:
        logger.exception("Unhandled exception in hourly_intake — will retry next hour")


def _run_daily_overview() -> None:
    try:
        from src.orchestrators.daily_overview import run
        result = run()
        logger.info("daily_overview finished: %s", result)
    except Exception:
        logger.exception("Unhandled exception in daily_overview — will retry tomorrow")


def _run_weekly_digest() -> None:
    try:
        from src.orchestrators.weekly_digest import run
        result = run()
        logger.info("weekly_digest finished: %s", result)
    except Exception:
        logger.exception("Unhandled exception in weekly_digest — will retry next Monday")


def main() -> None:
    # ── Startup checks — fail fast with a clear message ──────────────────
    logger.info("Running startup checks...")
    try:
        slack_ops.check_bot_membership()
        logger.info("Slack channel membership: OK")
    except RuntimeError as exc:
        logger.error("Startup check failed:\n%s", exc)
        raise SystemExit(1)

    # ── Register jobs ─────────────────────────────────────────────────────
    daily_time = settings.daily_summary_time        # e.g. "18:00"
    weekly_day = settings.weekly_summary_day        # e.g. "monday"
    weekly_time = settings.weekly_summary_time      # e.g. "09:00"

    # Hourly intake — fires once per hour at :00
    schedule.every().hour.at(":00").do(_run_hourly_intake)

    # Daily overview — fires once per day at the configured time
    schedule.every().day.at(daily_time).do(_run_daily_overview)

    # Weekly digest — fires once on the configured weekday at the configured time
    day_scheduler = getattr(schedule.every(), weekly_day)  # e.g. schedule.every().monday
    day_scheduler.at(weekly_time).do(_run_weekly_digest)

    logger.info(
        "Scheduler started — hourly intake every :00, daily overview at %s, "
        "weekly digest every %s at %s",
        daily_time,
        weekly_day,
        weekly_time,
    )

    # Run intake immediately on startup so there's no silent wait until :00.
    logger.info("Running initial hourly intake on startup...")
    _run_hourly_intake()

    while True:
        schedule.run_pending()
        time.sleep(30)  # check every 30 s — fine-grained enough for :00 alignment


if __name__ == "__main__":
    main()
