"""Conversation handler for /resume command."""

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from medremind.constants import chat_filter
from medremind.crud import get_paused_medications, get_persons, resume_medication
from medremind.database import get_db
from medremind.scheduler import add_jobs_for_medication

CHOOSE_PERSON, CHOOSE_MED = range(2)


async def resume_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        persons = get_persons(db)

        if not persons:
            await update.message.reply_text("No persons found. Use /addperson first.")
            return ConversationHandler.END

        lines = ["Who is this for?"]
        person_map = {}
        for i, p in enumerate(persons, 1):
            lines.append(f"{i}. {p.name}")
            person_map[str(i)] = {"id": p.id, "name": p.name}

        context.user_data["resume_person_map"] = person_map
        await update.message.reply_text("\n".join(lines))
        return CHOOSE_PERSON
    finally:
        db.close()


async def person_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    person_map = context.user_data.get("resume_person_map", {})

    if choice not in person_map:
        await update.message.reply_text("Please pick a number from the list.")
        return CHOOSE_PERSON

    person = person_map[choice]
    context.user_data["resume_person_name"] = person["name"]

    db = get_db()
    try:
        meds = get_paused_medications(db, person_id=person["id"])

        if not meds:
            await update.message.reply_text(
                f"No paused medications found for {person['name']}."
            )
            return ConversationHandler.END

        lines = [f"Which medication to resume for {person['name']}?"]
        med_map = {}
        for i, med in enumerate(meds, 1):
            lines.append(f"{i}. {med.name} {med.dose}")
            med_map[str(i)] = med.id

        context.user_data["resume_med_map"] = med_map
        await update.message.reply_text("\n".join(lines))
        return CHOOSE_MED
    finally:
        db.close()


async def med_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    med_map = context.user_data.get("resume_med_map", {})

    if choice not in med_map:
        await update.message.reply_text("Please pick a number from the list.")
        return CHOOSE_MED

    med_id = med_map[choice]
    db = get_db()
    try:
        med = resume_medication(db, med_id)
        if med:
            add_jobs_for_medication(med.id, med.schedules)
            times_str = ", ".join(s.time_hhmm for s in med.schedules)
            await update.message.reply_text(
                f"▶️ Resumed: {context.user_data['resume_person_name']} — {med.name} {med.dose}\n"
                f"Scheduled at: {times_str}\n"
                f"Reminders are active."
            )
        else:
            await update.message.reply_text("Medication not found.")
    finally:
        db.close()

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


resume_conversation = ConversationHandler(
    entry_points=[CommandHandler("resume", resume_start, filters=chat_filter())],
    states={
        CHOOSE_PERSON: [MessageHandler(chat_filter() & ~filters.COMMAND, person_chosen)],
        CHOOSE_MED: [MessageHandler(chat_filter() & ~filters.COMMAND, med_chosen)],
    },
    fallbacks=[CommandHandler("cancel", cancel, filters=chat_filter())],
)
