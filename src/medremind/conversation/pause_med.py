"""Conversation handler for /pause command."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
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

        keyboard = [
            [InlineKeyboardButton(p.name, callback_data=f"pausep_{p.id}_{p.name}")]
            for p in persons
        ]
        await update.message.reply_text(
            "Who is this for?", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CHOOSE_PERSON
    finally:
        db.close()


async def person_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, person_id, person_name = query.data.split("_", 2)
    person_id = int(person_id)
    context.user_data["pause_person_name"] = person_name

    db = get_db()
    try:
        meds = get_active_medications(db, person_id=person_id)

        if not meds:
            await query.edit_message_text(
                f"No active medications found for {person_name}."
            )
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(
                f"{med.name} {med.dose}",
                callback_data=f"pausem_{med.id}",
            )]
            for med in meds
        ]
        await query.edit_message_text(
            f"Which medication to pause for {person_name}?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return CHOOSE_MED
    finally:
        db.close()


async def med_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    med_id = int(query.data.split("_")[1])
    db = get_db()
    try:
        med = pause_medication(db, med_id)
        if med:
            remove_jobs_for_medication(med.id, med.schedules)
            await query.edit_message_text(
                f"⏸ Paused: {context.user_data['pause_person_name']} — {med.name} {med.dose}\n"
                f"Use /resume to reactivate."
            )
        else:
            await query.edit_message_text("Medication not found.")
    finally:
        db.close()

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


pause_conversation = ConversationHandler(
    entry_points=[CommandHandler("pause", pause_start, filters=chat_filter())],
    states={
        CHOOSE_PERSON: [CallbackQueryHandler(person_chosen, pattern=r"^pausep_")],
        CHOOSE_MED: [CallbackQueryHandler(med_chosen, pattern=r"^pausem_")],
    },
    fallbacks=[CommandHandler("cancel", cancel, filters=chat_filter())],
    per_message=False,
)
