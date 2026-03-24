"""Conversation handler for /delete command."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from medremind.constants import chat_filter
from medremind.crud import (
    delete_medication,
    get_medication_with_schedules,
    get_medications_for_person,
    get_persons,
)
from medremind.database import get_db
from medremind.scheduler import refresh_jobs

CHOOSE_PERSON, CHOOSE_MED, CONFIRM = range(3)


def _cancel_row():
    return [InlineKeyboardButton("❌ Cancel", callback_data="del_cancel")]


async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        persons = get_persons(db)

        if not persons:
            await update.message.reply_text("No persons found. Use /addperson first.")
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(p.name, callback_data=f"delp_{p.id}_{p.name}")]
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
    context.user_data["delete_person_name"] = person_name

    db = get_db()
    try:
        meds = get_medications_for_person(db, person_id)

        if not meds:
            await query.edit_message_text(
                f"No medications found for {person_name}."
            )
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(
                f"{med.name} {med.dose}{' [PAUSED]' if not med.active else ''}",
                callback_data=f"delm_{med.id}",
            )]
            for med in meds
        ] + [_cancel_row()]
        await query.edit_message_text(
            f"Which medication to delete for {person_name}?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return CHOOSE_MED
    finally:
        db.close()


async def med_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    med_id = int(query.data.split("_")[1])
    context.user_data["delete_med_id"] = med_id

    db = get_db()
    try:
        med = get_medication_with_schedules(db, med_id)
        if med:
            context.user_data["delete_med_name"] = (
                f"{context.user_data['delete_person_name']} — {med.name} {med.dose}"
            )
        else:
            context.user_data["delete_med_name"] = "Unknown"
    finally:
        db.close()

    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, delete", callback_data="delconfirm_yes"),
            InlineKeyboardButton("❌ No", callback_data="delconfirm_no"),
        ]
    ]
    await query.edit_message_text(
        f"Permanently delete {context.user_data['delete_med_name']}?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CONFIRM


async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    confirmed = query.data.split("_")[1] == "yes"

    if not confirmed:
        await query.edit_message_text("Deletion cancelled.")
        return ConversationHandler.END

    med_id = context.user_data["delete_med_id"]
    db = get_db()
    try:
        if delete_medication(db, med_id):
            refresh_jobs()
            await query.edit_message_text(
                f"🗑 Deleted: {context.user_data['delete_med_name']}"
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


delete_conversation = ConversationHandler(
    entry_points=[CommandHandler("delete", delete_start, filters=chat_filter())],
    states={
        CHOOSE_PERSON: [CallbackQueryHandler(person_chosen, pattern=r"^delp_")],
        CHOOSE_MED: [CallbackQueryHandler(med_chosen, pattern=r"^delm_")],
        CONFIRM: [CallbackQueryHandler(confirm_delete, pattern=r"^delconfirm_")],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_callback, pattern=r"^del_cancel$"),
        CommandHandler("cancel", cancel, filters=chat_filter()),
    ],
    per_message=False,
)
