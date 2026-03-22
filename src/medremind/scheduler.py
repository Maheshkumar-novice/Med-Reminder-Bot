"""APScheduler setup and job management."""

import logging
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from medremind.config import settings
from medremind.constants import FOOD_RULE_LABELS
from medremind.crud import get_active_schedules, pause_medication
from medremind.database import Medication, get_db

SNOOZE_MINUTES = 15

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=pytz.timezone(settings.timezone))

_bot_app = None

JOB_PREFIX = "slot_"


def set_bot_app(app):
    """Store the telegram bot application for sending messages."""
    global _bot_app
    _bot_app = app


def format_time_12hr(hhmm: str) -> str:
    """Convert 'HH:MM' to 'H:MM AM/PM'."""
    h, m = map(int, hhmm.split(":"))
    period = "AM" if h < 12 else "PM"
    display_h = h % 12 or 12
    return f"{display_h}:{m:02d} {period}"


def _job_id(time_hhmm: str) -> str:
    return f"{JOB_PREFIX}{time_hhmm.replace(':', '_')}"


def _time_from_job_id(job_id: str) -> str:
    return job_id[len(JOB_PREFIX):].replace("_", ":")


async def send_grouped_reminder(time_hhmm: str):
    """Send grouped reminder messages for all active meds at this time."""
    db = get_db()
    try:
        schedules = get_active_schedules(db)
        matching = [s for s in schedules if s.time_hhmm == time_hhmm]

        if not matching:
            return

        tz = pytz.timezone(settings.timezone)
        today = datetime.now(tz).date()
        time_label = format_time_12hr(time_hhmm)

        # Check end dates and filter
        active = []
        for s in matching:
            med = s.medication
            if med.end_date and today > med.end_date:
                logger.info("Medication %s passed end date, auto-pausing", med.id)
                pause_medication(db, med.id)
                continue
            active.append(s)

        if not active:
            refresh_jobs()
            return

        # Group by person
        by_person: dict[str, list[Medication]] = {}
        for s in active:
            person_name = s.medication.person.name
            by_person.setdefault(person_name, []).append(s.medication)

        for person_name, meds in by_person.items():
            if len(meds) == 1:
                med = meds[0]
                food_label = FOOD_RULE_LABELS.get(med.food_rule, med.food_rule)
                message = (
                    f"💊 {person_name} · {med.name} {med.dose}\n"
                    f"{food_label} · {time_label}"
                )
            else:
                lines = [f"💊 {person_name} — {time_label}\n"]
                for med in meds:
                    food_label = FOOD_RULE_LABELS.get(med.food_rule, med.food_rule)
                    lines.append(f"  • {med.name} {med.dose} ({food_label})")
                message = "\n".join(lines)

            if _bot_app:
                snooze_data = f"snooze_{time_hhmm}_{person_name}"
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        f"🔁 Remind in {SNOOZE_MINUTES} min",
                        callback_data=snooze_data,
                    )]
                ])
                try:
                    await _bot_app.bot.send_message(
                        chat_id=settings.telegram_group_chat_id,
                        text=message,
                        reply_markup=keyboard,
                    )
                except Exception:
                    logger.exception("Failed to send reminder, retrying in 30s")
                    retry_time = datetime.now(tz) + timedelta(seconds=30)
                    scheduler.add_job(
                        send_grouped_reminder,
                        trigger=DateTrigger(run_date=retry_time),
                        args=[time_hhmm],
                        id=f"retry_{time_hhmm.replace(':', '_')}",
                        replace_existing=True,
                    )
    finally:
        db.close()


async def send_person_reminder(time_hhmm: str, person_name: str):
    """Send a reminder for a specific person at a specific time (used by snooze)."""
    db = get_db()
    try:
        schedules = get_active_schedules(db)
        matching = [
            s for s in schedules
            if s.time_hhmm == time_hhmm and s.medication.person.name == person_name
        ]

        if not matching:
            return

        time_label = format_time_12hr(time_hhmm)
        meds = [s.medication for s in matching]

        if len(meds) == 1:
            med = meds[0]
            food_label = FOOD_RULE_LABELS.get(med.food_rule, med.food_rule)
            message = (
                f"🔁 {person_name} · {med.name} {med.dose}\n"
                f"{food_label} · {time_label}"
            )
        else:
            lines = [f"🔁 {person_name} — {time_label}\n"]
            for med in meds:
                food_label = FOOD_RULE_LABELS.get(med.food_rule, med.food_rule)
                lines.append(f"  • {med.name} {med.dose} ({food_label})")
            message = "\n".join(lines)

        if _bot_app:
            snooze_data = f"snooze_{time_hhmm}_{person_name}"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    f"🔁 Remind in {SNOOZE_MINUTES} min",
                    callback_data=snooze_data,
                )]
            ])
            await _bot_app.bot.send_message(
                chat_id=settings.telegram_group_chat_id,
                text=message,
                reply_markup=keyboard,
            )
    finally:
        db.close()


def schedule_snooze(time_hhmm: str, person_name: str):
    """Schedule a one-time reminder for a specific person after SNOOZE_MINUTES."""
    tz = pytz.timezone(settings.timezone)
    run_at = datetime.now(tz) + timedelta(minutes=SNOOZE_MINUTES)
    job_id = f"snooze_{time_hhmm.replace(':', '_')}_{person_name}"
    scheduler.add_job(
        send_person_reminder,
        trigger=DateTrigger(run_date=run_at),
        args=[time_hhmm, person_name],
        id=job_id,
        replace_existing=True,
    )
    logger.info("Snoozed %s for %s — will fire at %s", time_hhmm, person_name, run_at)


def refresh_jobs():
    """Sync cron jobs with current active schedule times."""
    db = get_db()
    try:
        schedules = get_active_schedules(db)
        needed_times = {s.time_hhmm for s in schedules}

        # Find existing time-slot jobs
        existing_times = set()
        for job in scheduler.get_jobs():
            if job.id.startswith(JOB_PREFIX):
                t = _time_from_job_id(job.id)
                if t not in needed_times:
                    scheduler.remove_job(job.id)
                    logger.info("Removed job for %s", t)
                else:
                    existing_times.add(t)

        # Add new jobs
        tz = pytz.timezone(settings.timezone)
        for t in needed_times - existing_times:
            h, m = map(int, t.split(":"))
            scheduler.add_job(
                send_grouped_reminder,
                trigger=CronTrigger(hour=h, minute=m, timezone=tz),
                args=[t],
                id=_job_id(t),
                replace_existing=True,
            )
            logger.info("Scheduled job for %s", t)

        logger.info(
            "Jobs refreshed: %d active time slots", len(needed_times)
        )
    finally:
        db.close()
