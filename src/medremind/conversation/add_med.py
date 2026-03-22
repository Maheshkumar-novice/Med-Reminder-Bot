"""Conversation handler for /add command."""

import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from medremind.config import settings
from medremind.constants import FOOD_RULE_LABELS, FOOD_RULE_OPTIONS, SUGGESTED_TIMES, chat_filter
from medremind.crud import add_medication, get_persons
from medremind.database import get_db
from medremind.scheduler import refresh_jobs

PERSON, MED_NAME, DOSE, FOOD_RULE, NUM_TIMES, CONFIRM_TIMES, TIME_SLOT = range(7)


def _format_times(times: list[str]) -> str:
    return ", ".join(times)


def _cancel_row():
    return [InlineKeyboardButton("❌ Cancel", callback_data="add_cancel")]


def _summary(context) -> str:
    """Build a summary of selections so far."""
    ud = context.user_data
    parts = []
    if "person_name" in ud:
        parts.append(f"👤 {ud['person_name']}")
    if "med_name" in ud:
        parts.append(f"💊 {ud['med_name']}")
    if "dose" in ud:
        parts.append(f"💉 {ud['dose']}")
    if "food_rule" in ud:
        parts.append(f"🍽 {FOOD_RULE_LABELS.get(ud['food_rule'], ud['food_rule'])}")
    return " · ".join(parts)


async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        persons = get_persons(db)

        if not persons:
            await update.message.reply_text("No persons found. Use /addperson first.")
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(p.name, callback_data=f"person_{p.id}_{p.name}")]
            for p in persons
        ] + [_cancel_row()]
        await update.message.reply_text(
            "Who is this for?", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return PERSON
    finally:
        db.close()


async def person_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, person_id, person_name = query.data.split("_", 2)
    context.user_data["person_id"] = int(person_id)
    context.user_data["person_name"] = person_name

    await query.edit_message_text(f"👤 {person_name}\n\nMedication name?")
    return MED_NAME


async def med_name_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["med_name"] = update.message.text.strip()
    await update.message.reply_text(
        f"{_summary(context)}\n\nDose? (e.g. 500mg, 1 tablet)"
    )
    return DOSE


async def dose_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["dose"] = update.message.text.strip()

    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"food_{key}")]
        for key, label in FOOD_RULE_OPTIONS.items()
    ] + [_cancel_row()]
    await update.message.reply_text(
        f"{_summary(context)}\n\nFood rule?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return FOOD_RULE


async def food_rule_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    food_key = query.data.split("_", 1)[1]
    context.user_data["food_rule"] = food_key

    keyboard = [
        [InlineKeyboardButton(str(n), callback_data=f"numtimes_{n}") for n in range(1, 5)],
        _cancel_row(),
    ]
    await query.edit_message_text(
        f"{_summary(context)}\n\nHow many times per day?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return NUM_TIMES


async def num_times_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    n = int(query.data.split("_")[1])
    context.user_data["num_times"] = n

    suggested = SUGGESTED_TIMES[n]
    context.user_data["suggested_times"] = suggested

    keyboard = [
        [
            InlineKeyboardButton("✅ Accept", callback_data="times_accept"),
            InlineKeyboardButton("✏️ Edit", callback_data="times_edit"),
        ],
        _cancel_row(),
    ]
    await query.edit_message_text(
        f"{_summary(context)}\n\n"
        f"{n}x per day — Suggested: {_format_times(suggested)}\n"
        f"(Timezone: {settings.timezone})",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CONFIRM_TIMES


async def times_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data.split("_")[1]

    if action == "accept":
        times = context.user_data["suggested_times"]
        await query.edit_message_text(f"{_summary(context)} · ⏰ {_format_times(times)}")
        return await _save_medication(query, context, times)

    # Edit — start manual time entry
    context.user_data["times"] = []
    await query.edit_message_text(
        f"{_summary(context)}\n\n"
        f"Time for dose 1? (HH:MM, 24hr format)\n"
        f"(Timezone: {settings.timezone})"
    )
    return TIME_SLOT


async def time_slot_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", text):
        await update.message.reply_text(
            "Invalid format. Please use HH:MM (e.g. 08:00)"
        )
        return TIME_SLOT

    times = context.user_data["times"]

    if text in times:
        await update.message.reply_text(
            f"{text} is already added. Pick a different time."
        )
        return TIME_SLOT

    times.append(text)

    num_times = context.user_data["num_times"]

    if len(times) < num_times:
        slot_num = len(times) + 1
        await update.message.reply_text(f"Time for dose {slot_num}?")
        return TIME_SLOT

    return await _save_medication(update, context, times)


async def _save_medication(source, context, times):
    """Save medication to DB and schedule jobs. Source is query or update."""
    db = get_db()
    try:
        med = add_medication(
            db=db,
            person_id=context.user_data["person_id"],
            name=context.user_data["med_name"],
            dose=context.user_data["dose"],
            food_rule=context.user_data["food_rule"],
            times=times,
        )
        refresh_jobs()

        food_label = FOOD_RULE_LABELS.get(med.food_rule, med.food_rule)
        times_str = _format_times(times)
        person_name = context.user_data["person_name"]

        message = (
            f"✅ Added successfully!\n\n"
            f"💊 {person_name} — {med.name} {med.dose}\n"
            f"{food_label} · {times_str}\n"
            f"Timezone: {settings.timezone}\n\n"
            f"Reminders are active."
        )

        # source can be a CallbackQuery or an Update
        if hasattr(source, "message"):
            await source.message.reply_text(message)
        else:
            await source.edit_message_text(message)
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


add_conversation = ConversationHandler(
    entry_points=[CommandHandler("add", add_start, filters=chat_filter())],
    states={
        PERSON: [CallbackQueryHandler(person_chosen, pattern=r"^person_")],
        MED_NAME: [MessageHandler(chat_filter() & ~filters.COMMAND, med_name_entered)],
        DOSE: [MessageHandler(chat_filter() & ~filters.COMMAND, dose_entered)],
        FOOD_RULE: [CallbackQueryHandler(food_rule_chosen, pattern=r"^food_")],
        NUM_TIMES: [CallbackQueryHandler(num_times_chosen, pattern=r"^numtimes_")],
        CONFIRM_TIMES: [CallbackQueryHandler(times_confirmed, pattern=r"^times_")],
        TIME_SLOT: [MessageHandler(chat_filter() & ~filters.COMMAND, time_slot_entered)],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_callback, pattern=r"^add_cancel$"),
        CommandHandler("cancel", cancel, filters=chat_filter()),
    ],
    per_message=False,
)
