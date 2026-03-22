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
from medremind.crud import get_active_medications, pause_medication
from medremind.database import get_db
from medremind.scheduler import remove_jobs_for_medication

CHOOSE_MED = 0


async def pause_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        meds = get_active_medications(db)

        if not meds:
            await update.message.reply_text("No active medications found.")
            return ConversationHandler.END

        lines = ["Which medication to pause?"]
        med_map = {}
        for i, med in enumerate(meds, 1):
            lines.append(f"{i}. {med.person.name} — {med.name} {med.dose}")
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
                f"⏸ Paused: {med.person.name} — {med.name} {med.dose}\n"
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
        CHOOSE_MED: [MessageHandler(chat_filter() & ~filters.COMMAND, med_chosen)],
    },
    fallbacks=[CommandHandler("cancel", cancel, filters=chat_filter())],
)
