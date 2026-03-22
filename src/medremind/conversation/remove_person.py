"""Conversation handler for /removeperson command."""

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from medremind.constants import chat_filter
from medremind.crud import deactivate_person, get_active_medications, get_persons
from medremind.database import get_db
from medremind.scheduler import remove_jobs_for_medication

CHOOSE_PERSON, CONFIRM = range(2)


async def remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        persons = get_persons(db)

        if not persons:
            await update.message.reply_text("No persons found.")
            return ConversationHandler.END

        lines = ["Which person to remove?"]
        person_map = {}
        for i, p in enumerate(persons, 1):
            lines.append(f"{i}. {p.name}")
            person_map[str(i)] = {"id": p.id, "name": p.name}

        context.user_data["remove_person_map"] = person_map
        await update.message.reply_text("\n".join(lines))
        return CHOOSE_PERSON
    finally:
        db.close()


async def person_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    person_map = context.user_data.get("remove_person_map", {})

    if choice not in person_map:
        await update.message.reply_text("Please pick a number from the list.")
        return CHOOSE_PERSON

    person = person_map[choice]
    context.user_data["remove_person_id"] = person["id"]
    context.user_data["remove_person_name"] = person["name"]

    await update.message.reply_text(
        f"This will deactivate {person['name']} and pause all their medications.\n\n"
        f"Type YES to confirm."
    )
    return CONFIRM


async def confirm_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text != "YES":
        await update.message.reply_text("Cancelled.")
        return ConversationHandler.END

    person_id = context.user_data["remove_person_id"]
    person_name = context.user_data["remove_person_name"]

    db = get_db()
    try:
        # Remove scheduler jobs for all active meds before deactivating
        meds = get_active_medications(db, person_id=person_id)
        for med in meds:
            remove_jobs_for_medication(med.id, med.schedules)

        person = deactivate_person(db, person_id)
        if person:
            await update.message.reply_text(
                f"🗑 Removed {person_name}. All their medications have been paused."
            )
        else:
            await update.message.reply_text("Person not found.")
    finally:
        db.close()

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


removeperson_conversation = ConversationHandler(
    entry_points=[CommandHandler("removeperson", remove_start, filters=chat_filter())],
    states={
        CHOOSE_PERSON: [MessageHandler(chat_filter() & ~filters.COMMAND, person_chosen)],
        CONFIRM: [MessageHandler(chat_filter() & ~filters.COMMAND, confirm_remove)],
    },
    fallbacks=[CommandHandler("cancel", cancel, filters=chat_filter())],
)
