from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("cadenza")

_scheduler: BackgroundScheduler | None = None
_app = None


def setup_scheduler(app):
    """Initialize and start the background scheduler."""
    global _scheduler, _app
    _app = app

    _scheduler = BackgroundScheduler(daemon=True)

    # Load schedule from settings
    with app.app_context():
        from cadenza.routes.settings import get_setting
        cron_expr = get_setting("sync_schedule", "0 1 * * *")

    try:
        trigger = CronTrigger.from_crontab(cron_expr)
        _scheduler.add_job(
            _scheduled_sync,
            trigger=trigger,
            id="daily_sync",
            replace_existing=True,
        )
        logger.info("Scheduler started with schedule: %s", cron_expr)
    except ValueError as e:
        logger.error("Invalid cron expression '%s': %s. Using default '0 1 * * *'", cron_expr, e)
        _scheduler.add_job(
            _scheduled_sync,
            trigger=CronTrigger.from_crontab("0 1 * * *"),
            id="daily_sync",
            replace_existing=True,
        )

    _scheduler.start()


def update_schedule(cron_expr: str) -> None:
    """Update the sync schedule without restarting the app."""
    global _scheduler
    if _scheduler is None:
        return

    try:
        trigger = CronTrigger.from_crontab(cron_expr)
        _scheduler.reschedule_job("daily_sync", trigger=trigger)
        logger.info("Schedule updated to: %s", cron_expr)
    except (ValueError, KeyError) as e:
        logger.error("Failed to update schedule: %s", e)


def _scheduled_sync():
    """Called by APScheduler to run the daily sync."""
    if _app is None:
        return

    with _app.app_context():
        from cadenza.services.sync import get_sync_service
        sync_service = get_sync_service()

        if sync_service.is_running:
            logger.info("Scheduled sync skipped: already running")
            return

        logger.info("Starting scheduled sync")
        sync_service.start_all_sync()
