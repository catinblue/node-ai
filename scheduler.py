"""
AI News Digest — Scheduler

Run this alongside Streamlit to auto-fetch and categorize articles on a schedule.
Usage: python scheduler.py
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from fetcher import fetch_all
from categorizer import categorize_articles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Schedule Configuration ────────────────────────────────
# TODO: Fill in your preferred schedule here.
#
# Return a list of dicts, each with cron fields:
#   hour, minute, timezone
#
# Examples:
#   Single morning run at 8:00 Paris time:
#     [{"hour": 8, "minute": 0, "timezone": "Europe/Paris"}]
#
#   Morning + evening:
#     [
#         {"hour": 8,  "minute": 0, "timezone": "Europe/Paris"},
#         {"hour": 19, "minute": 0, "timezone": "Europe/Paris"},
#     ]
#
#   Every 6 hours:
#     [{"hour": "*/6", "minute": 0, "timezone": "UTC"}]

def get_schedule_config():
    return [
        {"hour": 7,  "minute": 30, "timezone": "Europe/Paris"},
        {"hour": 18, "minute": 30, "timezone": "Europe/Paris"},
    ]


# ── Job ───────────────────────────────────────────────────

def run_digest():
    """Fetch all sources then categorize today's articles."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info("Starting scheduled digest run for %s", today)

    try:
        count = fetch_all()
        log.info("Fetched %d new articles", count)
    except Exception:
        log.exception("Fetch failed")
        return

    try:
        stories = categorize_articles(today)
        log.info("Created %d stories", stories)
    except Exception:
        log.exception("Categorization failed")


# ── Main ──────────────────────────────────────────────────

def main():
    schedules = get_schedule_config()
    if not schedules:
        log.error("No schedules configured! Edit get_schedule_config() in scheduler.py")
        return

    scheduler = BlockingScheduler()

    for i, cfg in enumerate(schedules):
        trigger = CronTrigger(
            hour=cfg["hour"],
            minute=cfg.get("minute", 0),
            timezone=cfg.get("timezone", "UTC"),
        )
        scheduler.add_job(run_digest, trigger, id=f"digest_{i}", name=f"Digest run #{i}")
        log.info("Scheduled run #%d: hour=%s minute=%s tz=%s",
                 i, cfg["hour"], cfg.get("minute", 0), cfg.get("timezone", "UTC"))

    log.info("Scheduler started. Press Ctrl+C to stop.")

    # Run once immediately on startup so you don't wait for the first cron tick
    run_digest()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
