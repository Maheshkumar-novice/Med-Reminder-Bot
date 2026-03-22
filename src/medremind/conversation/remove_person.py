"""Conversation handler for /removeperson command."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
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

        keyboard = [
            [InlineKeyboardButton(p.name, callback_data=f"rmp_{p.id}_{p.name}")]
            for p in persons
        ]
        await update.message.reply_text(
            "Which person to remove?", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CHOOSE_PERSON
    finally:
        db.close()


async def person_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, person_id, person_name = query.data.split("_", 2)
    context.user_data["remove_person_id"] = int(person_id)
    context.user_data["remove_person_name"] = person_name

    await query.edit_message_text(
        f"This will deactivate {person_name} and pause all their medications.\n\n"
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
        CHOOSE_PERSON: [CallbackQueryHandler(person_chosen, pattern=r"^rmp_")],
        CONFIRM: [MessageHandler(chat_filter() & ~filters.COMMAND, confirm_remove)],
    },
    fallbacks=[CommandHandler("cancel", cancel, filters=chat_filter())],
    per_message=False,
)
