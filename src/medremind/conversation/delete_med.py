"""Conversation handler for /delete command."""

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from medremind.constants import chat_filter
from medremind.crud import (
    delete_medication,
    get_medication_with_schedules,
    list_medications,
)
from medremind.database import get_db
from medremind.scheduler import remove_jobs_for_medication

CHOOSE_MED, CONFIRM = range(2)


async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        meds = list_medications(db)

        if not meds:
            await update.message.reply_text("No medications found.")
            return ConversationHandler.END

        lines = ["Which medication to delete?"]
        med_map = {}
        for i, med in enumerate(meds, 1):
            status = " [PAUSED]" if not med.active else ""
            lines.append(f"{i}. {med.person.name} — {med.name} {med.dose}{status}")
            med_map[str(i)] = med.id

        context.user_data["delete_med_map"] = med_map
        await update.message.reply_text("\n".join(lines))
        return CHOOSE_MED
    finally:
        db.close()


async def med_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    med_map = context.user_data.get("delete_med_map", {})

    if choice not in med_map:
        await update.message.reply_text("Please pick a number from the list.")
        return CHOOSE_MED

    context.user_data["delete_med_id"] = med_map[choice]

    db = get_db()
    try:
        med = get_medication_with_schedules(db, med_map[choice])
        if med:
            context.user_data["delete_med_name"] = (
                f"{med.person.name} — {med.name} {med.dose}"
            )
        else:
            context.user_data["delete_med_name"] = "Unknown"
    finally:
        db.close()

    await update.message.reply_text(
        f"Are you sure you want to permanently delete "
        f"{context.user_data['delete_med_name']}?\n\n"
        f"Type YES to confirm."
    )
    return CONFIRM


async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text != "YES":
        await update.message.reply_text("Deletion cancelled.")
        return ConversationHandler.END

    med_id = context.user_data["delete_med_id"]
    db = get_db()
    try:
        med = get_medication_with_schedules(db, med_id)
        if med:
            remove_jobs_for_medication(med.id, med.schedules)
            delete_medication(db, med_id)
            await update.message.reply_text(
                f"🗑 Deleted: {context.user_data['delete_med_name']}"
            )
        else:
            await update.message.reply_text("Medication not found.")
    finally:
        db.close()

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


delete_conversation = ConversationHandler(
    entry_points=[CommandHandler("delete", delete_start, filters=chat_filter())],
    states={
        CHOOSE_MED: [MessageHandler(chat_filter() & ~filters.COMMAND, med_chosen)],
        CONFIRM: [MessageHandler(chat_filter() & ~filters.COMMAND, confirm_delete)],
    },
    fallbacks=[CommandHandler("cancel", cancel, filters=chat_filter())],
)
