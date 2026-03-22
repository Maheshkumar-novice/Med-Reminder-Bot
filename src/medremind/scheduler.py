"""APScheduler setup and job management."""

import logging
from datetime import date, datetime, timedelta

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from medremind.config import settings
from medremind.constants import FOOD_RULE_LABELS
from medremind.crud import get_active_schedules, pause_medication
from medremind.database import Schedule, get_db

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=pytz.timezone(settings.timezone))

# Will be set during bot startup
_bot_app = None


def set_bot_app(app):
    """Store the telegram bot application for sending messages."""
    global _bot_app
    _bot_app = app


def _format_time_12hr(hhmm: str) -> str:
    """Convert 'HH:MM' to 'H:MM AM/PM'."""
    h, m = map(int, hhmm.split(":"))
    period = "AM" if h < 12 else "PM"
    display_h = h % 12 or 12
    return f"{display_h}:{m:02d} {period}"


async def send_reminder(schedule_id: int):
    """Send a reminder message for a specific schedule entry."""
    db = get_db()
    try:
        schedule = (
            db.query(Schedule).filter(Schedule.id == schedule_id).first()
        )
        if not schedule or not schedule.active:
            return

        med = schedule.medication
        if not med or not med.active:
            return

        # Check end date using configured timezone
        today = datetime.now(pytz.timezone(settings.timezone)).date()
        if med.end_date and today > med.end_date:
            logger.info(
                "Medication %s has passed end date, auto-pausing", med.id
            )
            pause_medication(db, med.id)
            for s in med.schedules:
                job_id = f"med_{med.id}_slot_{s.id}"
                if scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)
            return

        person_name = med.person.name
        food_label = FOOD_RULE_LABELS.get(med.food_rule, med.food_rule)
        time_label = _format_time_12hr(schedule.time_hhmm)

        message = f"💊 {person_name} · {med.name} {med.dose}\n{food_label} · {time_label}"

        if _bot_app:
            try:
                await _bot_app.bot.send_message(
                    chat_id=settings.telegram_group_chat_id,
                    text=message,
                )
            except Exception:
                logger.exception("Failed to send reminder, retrying in 30s")
                retry_time = datetime.now(
                    pytz.timezone(settings.timezone)
                ) + timedelta(seconds=30)
                scheduler.add_job(
                    send_reminder,
                    trigger=DateTrigger(run_date=retry_time),
                    args=[schedule_id],
                    id=f"retry_{schedule_id}",
                    replace_existing=True,
                )
    finally:
        db.close()


def add_jobs_for_medication(med_id: int, schedules: list[Schedule]):
    """Add cron jobs for each schedule entry of a medication."""
    tz = pytz.timezone(settings.timezone)
    for s in schedules:
        h, m = map(int, s.time_hhmm.split(":"))
        job_id = f"med_{med_id}_slot_{s.id}"
        scheduler.add_job(
            send_reminder,
            trigger=CronTrigger(hour=h, minute=m, timezone=tz),
            args=[s.id],
            id=job_id,
            replace_existing=True,
        )
        logger.info("Scheduled job %s at %s", job_id, s.time_hhmm)


def remove_jobs_for_medication(med_id: int, schedules: list[Schedule]):
    """Remove all cron jobs for a medication."""
    for s in schedules:
        job_id = f"med_{med_id}_slot_{s.id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info("Removed job %s", job_id)


def load_all_jobs():
    """Load all active schedules from DB and add cron jobs."""
    db = get_db()
    try:
        active_schedules = get_active_schedules(db)
        for s in active_schedules:
            add_jobs_for_medication(s.medication_id, [s])
        logger.info("Loaded %d active schedule jobs", len(active_schedules))
    finally:
        db.close()
