"""Conversation handler for /pause command."""

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from medremind.constants import chat_filter
from medremind.crud import get_active_medications, get_persons, pause_medication
from medremind.database import get_db
from medremind.scheduler import remove_jobs_for_medication

CHOOSE_PERSON, CHOOSE_MED = range(2)


async def pause_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        context.user_data["pause_person_map"] = person_map
        await update.message.reply_text("\n".join(lines))
        return CHOOSE_PERSON
    finally:
        db.close()


async def person_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    person_map = context.user_data.get("pause_person_map", {})

    if choice not in person_map:
        await update.message.reply_text("Please pick a number from the list.")
        return CHOOSE_PERSON

    person = person_map[choice]
    context.user_data["pause_person_name"] = person["name"]

    db = get_db()
    try:
        meds = get_active_medications(db, person_id=person["id"])

        if not meds:
            await update.message.reply_text(
                f"No active medications found for {person['name']}."
            )
            return ConversationHandler.END

        lines = [f"Which medication to pause for {person['name']}?"]
        med_map = {}
        for i, med in enumerate(meds, 1):
            lines.append(f"{i}. {med.name} {med.dose}")
            med_map[str(i)] = med.id

        context.user_data["pause_med_map"] = med_map
        await update.message.reply_text("\n".join(lines))
        return CHOOSE_MED
    finally:
        db.close()


async def med_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    med_map = context.user_data.get("pause_med_map", {})

    if choice not in med_map:
        await update.message.reply_text("Please pick a number from the list.")
        return CHOOSE_MED

    med_id = med_map[choice]
    db = get_db()
    try:
        med = pause_medication(db, med_id)
        if med:
            remove_jobs_for_medication(med.id, med.schedules)
            await update.message.reply_text(
                f"⏸ Paused: {context.user_data['pause_person_name']} — {med.name} {med.dose}\n"
                f"Use /resume to reactivate."
            )
        else:
            await update.message.reply_text("Medication not found.")
    finally:
        db.close()

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


pause_conversation = ConversationHandler(
    entry_points=[CommandHandler("pause", pause_start, filters=chat_filter())],
    states={
        CHOOSE_PERSON: [MessageHandler(chat_filter() & ~filters.COMMAND, person_chosen)],
        CHOOSE_MED: [MessageHandler(chat_filter() & ~filters.COMMAND, med_chosen)],
    },
    fallbacks=[CommandHandler("cancel", cancel, filters=chat_filter())],
)
