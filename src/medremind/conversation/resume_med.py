"""Conversation handler for /resume command."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from medremind.constants import chat_filter
from medremind.crud import get_paused_medications, get_persons, resume_medication
from medremind.database import get_db
from medremind.scheduler import add_jobs_for_medication

CHOOSE_PERSON, CHOOSE_MED = range(2)


def _cancel_row():
    return [InlineKeyboardButton("❌ Cancel", callback_data="resume_cancel")]


async def resume_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        persons = get_persons(db)

        if not persons:
            await update.message.reply_text("No persons found. Use /addperson first.")
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(p.name, callback_data=f"resp_{p.id}_{p.name}")]
            for p in persons
        ] + [_cancel_row()]
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
    context.user_data["resume_person_name"] = person_name

    db = get_db()
    try:
        meds = get_paused_medications(db, person_id=person_id)

        if not meds:
            await query.edit_message_text(
                f"No paused medications found for {person_name}."
            )
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(
                f"{med.name} {med.dose}",
                callback_data=f"resm_{med.id}",
            )]
            for med in meds
        ] + [_cancel_row()]
        await query.edit_message_text(
            f"Which medication to resume for {person_name}?",
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
        med = resume_medication(db, med_id)
        if med:
            add_jobs_for_medication(med.id, med.schedules)
            times_str = ", ".join(s.time_hhmm for s in med.schedules)
            await query.edit_message_text(
                f"▶️ Resumed: {context.user_data['resume_person_name']} — {med.name} {med.dose}\n"
                f"Scheduled at: {times_str}\n"
                f"Reminders are active."
            )
        else:
            await query.edit_message_text("Medication not found.")
    finally:
        db.close()

    return ConversationHandler.END


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Cancelled.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


resume_conversation = ConversationHandler(
    entry_points=[CommandHandler("resume", resume_start, filters=chat_filter())],
    states={
        CHOOSE_PERSON: [CallbackQueryHandler(person_chosen, pattern=r"^resp_")],
        CHOOSE_MED: [CallbackQueryHandler(med_chosen, pattern=r"^resm_")],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_callback, pattern=r"^resume_cancel$"),
        CommandHandler("cancel", cancel, filters=chat_filter()),
    ],
    per_message=False,
)
