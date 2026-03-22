"""Conversation handler for /edit command."""

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
from medremind.crud import (
    get_active_medications,
    get_medication_with_schedules,
    get_persons,
    replace_schedules,
    update_medication,
)
from medremind.database import get_db
from medremind.scheduler import refresh_jobs

CHOOSE_PERSON, CHOOSE_MED, CHOOSE_FIELD, NEW_VALUE, EDIT_TIMES, CONFIRM_TIMES, MANUAL_TIME = range(7)


def _cancel_row():
    return [InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel")]


def _med_summary(context) -> str:
    ud = context.user_data
    person = ud.get("edit_person_name", "")
    med_name = ud.get("edit_med_name", "")
    dose = ud.get("edit_med_dose", "")
    return f"👤 {person} · 💊 {med_name} {dose}"


async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        persons = get_persons(db)

        if not persons:
            await update.message.reply_text("No persons found. Use /addperson first.")
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(p.name, callback_data=f"editp_{p.id}_{p.name}")]
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
    context.user_data["edit_person_name"] = person_name

    db = get_db()
    try:
        meds = get_active_medications(db, person_id=person_id)

        if not meds:
            await query.edit_message_text(f"No active medications found for {person_name}.")
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(
                f"{med.name} {med.dose}",
                callback_data=f"editm_{med.id}",
            )]
            for med in meds
        ] + [_cancel_row()]
        await query.edit_message_text(
            f"Which medication to edit for {person_name}?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return CHOOSE_MED
    finally:
        db.close()


async def med_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    med_id = int(query.data.split("_")[1])
    context.user_data["edit_med_id"] = med_id

    db = get_db()
    try:
        med = get_medication_with_schedules(db, med_id)
        if not med:
            await query.edit_message_text("Medication not found.")
            return ConversationHandler.END

        context.user_data["edit_med_name"] = med.name
        context.user_data["edit_med_dose"] = med.dose
        times_str = ", ".join(s.time_hhmm for s in med.schedules)
        food_label = FOOD_RULE_LABELS.get(med.food_rule, med.food_rule)

        keyboard = [
            [InlineKeyboardButton("Name", callback_data="editf_name")],
            [InlineKeyboardButton("Dose", callback_data="editf_dose")],
            [InlineKeyboardButton("Food rule", callback_data="editf_food_rule")],
            [InlineKeyboardButton("Times", callback_data="editf_times")],
            _cancel_row(),
        ]
        await query.edit_message_text(
            f"{_med_summary(context)}\n"
            f"🍽 {food_label} · ⏰ {times_str}\n\n"
            f"What do you want to change?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return CHOOSE_FIELD
    finally:
        db.close()


async def field_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    field = query.data.split("_", 1)[1]
    context.user_data["edit_field"] = field

    if field == "name":
        await query.edit_message_text(f"{_med_summary(context)}\n\nNew medication name?")
        return NEW_VALUE

    if field == "dose":
        await query.edit_message_text(f"{_med_summary(context)}\n\nNew dose? (e.g. 500mg, 1 tablet)")
        return NEW_VALUE

    if field == "food_rule":
        keyboard = [
            [InlineKeyboardButton(label, callback_data=f"editfood_{key}")]
            for key, label in FOOD_RULE_OPTIONS.items()
        ] + [_cancel_row()]
        await query.edit_message_text(
            f"{_med_summary(context)}\n\nNew food rule?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return NEW_VALUE

    if field == "times":
        keyboard = [
            [InlineKeyboardButton(str(n), callback_data=f"editnum_{n}") for n in range(1, 5)],
            _cancel_row(),
        ]
        await query.edit_message_text(
            f"{_med_summary(context)}\n\nHow many times per day?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return EDIT_TIMES

    return ConversationHandler.END


async def new_value_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for name or dose changes."""
    text = update.message.text.strip()
    field = context.user_data["edit_field"]

    if field not in ("name", "dose"):
        await update.message.reply_text("Please use the buttons above.")
        return NEW_VALUE

    med_id = context.user_data["edit_med_id"]

    db = get_db()
    try:
        med = update_medication(db, med_id, **{field: text})
        if med:
            context.user_data["edit_med_name"] = med.name
            context.user_data["edit_med_dose"] = med.dose
            await update.message.reply_text(
                f"✅ Updated {field}: {text}\n\n{_med_summary(context)}"
            )
        else:
            await update.message.reply_text("Medication not found.")
    finally:
        db.close()

    return ConversationHandler.END


async def food_rule_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard for food rule change."""
    query = update.callback_query
    await query.answer()

    food_key = query.data.split("_", 1)[1]
    med_id = context.user_data["edit_med_id"]

    db = get_db()
    try:
        med = update_medication(db, med_id, food_rule=food_key)
        if med:
            food_label = FOOD_RULE_LABELS.get(food_key, food_key)
            await query.edit_message_text(
                f"✅ Updated food rule: {food_label}\n\n{_med_summary(context)}"
            )
        else:
            await query.edit_message_text("Medication not found.")
    finally:
        db.close()

    return ConversationHandler.END


async def num_times_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle frequency selection for time editing."""
    query = update.callback_query
    await query.answer()

    n = int(query.data.split("_")[1])
    context.user_data["edit_num_times"] = n

    suggested = SUGGESTED_TIMES[n]
    context.user_data["edit_suggested_times"] = suggested

    keyboard = [
        [
            InlineKeyboardButton("✅ Accept", callback_data="edittimes_accept"),
            InlineKeyboardButton("✏️ Edit", callback_data="edittimes_edit"),
        ],
        _cancel_row(),
    ]
    await query.edit_message_text(
        f"{_med_summary(context)}\n\n"
        f"{n}x per day — Suggested: {', '.join(suggested)}\n"
        f"(Timezone: {settings.timezone})",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CONFIRM_TIMES


async def times_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data.split("_")[1]

    if action == "accept":
        times = context.user_data["edit_suggested_times"]
        return await _save_times(query, context, times)

    # Manual entry
    context.user_data["edit_times"] = []
    await query.edit_message_text(
        f"{_med_summary(context)}\n\n"
        f"Time for dose 1? (HH:MM, 24hr format)\n"
        f"(Timezone: {settings.timezone})"
    )
    return MANUAL_TIME


async def time_slot_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manual time entry for editing times."""
    text = update.message.text.strip()

    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", text):
        await update.message.reply_text("Invalid format. Please use HH:MM (e.g. 08:00)")
        return MANUAL_TIME

    times = context.user_data["edit_times"]

    if text in times:
        await update.message.reply_text(f"{text} is already added. Pick a different time.")
        return MANUAL_TIME

    times.append(text)
    num_times = context.user_data["edit_num_times"]

    if len(times) < num_times:
        slot_num = len(times) + 1
        await update.message.reply_text(f"Time for dose {slot_num}?")
        return MANUAL_TIME

    return await _save_times(update, context, times)


async def _save_times(source, context, times):
    med_id = context.user_data["edit_med_id"]
    db = get_db()
    try:
        med = replace_schedules(db, med_id, times)
        if med:
            refresh_jobs()
            times_str = ", ".join(times)
            message = f"✅ Updated times: {times_str}\n\n{_med_summary(context)}"
            if hasattr(source, "message"):
                await source.message.reply_text(message)
            else:
                await source.edit_message_text(message)
        else:
            msg = "Medication not found."
            if hasattr(source, "message"):
                await source.message.reply_text(msg)
            else:
                await source.edit_message_text(msg)
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


edit_conversation = ConversationHandler(
    entry_points=[CommandHandler("edit", edit_start, filters=chat_filter())],
    states={
        CHOOSE_PERSON: [CallbackQueryHandler(person_chosen, pattern=r"^editp_")],
        CHOOSE_MED: [CallbackQueryHandler(med_chosen, pattern=r"^editm_")],
        CHOOSE_FIELD: [CallbackQueryHandler(field_chosen, pattern=r"^editf_")],
        NEW_VALUE: [
            CallbackQueryHandler(food_rule_chosen, pattern=r"^editfood_"),
            MessageHandler(chat_filter() & ~filters.COMMAND, new_value_entered),
        ],
        EDIT_TIMES: [CallbackQueryHandler(num_times_chosen, pattern=r"^editnum_")],
        CONFIRM_TIMES: [CallbackQueryHandler(times_confirmed, pattern=r"^edittimes_")],
        MANUAL_TIME: [MessageHandler(chat_filter() & ~filters.COMMAND, time_slot_entered)],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_callback, pattern=r"^edit_cancel$"),
        CommandHandler("cancel", cancel, filters=chat_filter()),
    ],
    per_message=False,
)
