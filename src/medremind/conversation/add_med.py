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

from medremind.constants import FOOD_RULE_LABELS, chat_filter
from medremind.crud import add_medication, get_persons
from medremind.database import get_db
from medremind.scheduler import add_jobs_for_medication

PERSON, MED_NAME, DOSE, FOOD_RULE, NUM_TIMES, TIME_SLOT = range(6)

FOOD_RULE_OPTIONS = {
    "before_food": "Before food",
    "after_food": "After food",
    "with_food": "With food",
    "empty_stomach": "Empty stomach",
    "any": "Any time",
}


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
        ]
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
    await update.message.reply_text("Dose? (e.g. 500mg, 1 tablet)")
    return DOSE


async def dose_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["dose"] = update.message.text.strip()

    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"food_{key}")]
        for key, label in FOOD_RULE_OPTIONS.items()
    ]
    await update.message.reply_text(
        "Food rule?", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return FOOD_RULE


async def food_rule_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    food_key = query.data.split("_", 1)[1]
    context.user_data["food_rule"] = food_key

    keyboard = [
        [InlineKeyboardButton(str(n), callback_data=f"numtimes_{n}") for n in range(1, 5)]
    ]
    await query.edit_message_text(
        f"{FOOD_RULE_OPTIONS[food_key]}\n\nHow many times per day?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return NUM_TIMES


async def num_times_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    n = int(query.data.split("_")[1])
    context.user_data["num_times"] = n
    context.user_data["times"] = []

    await query.edit_message_text(f"{n}x per day\n\nTime for dose 1? (HH:MM, 24hr format)")
    return TIME_SLOT


async def time_slot_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", text):
        await update.message.reply_text(
            "Invalid format. Please use HH:MM (e.g. 08:00)"
        )
        return TIME_SLOT

    times = context.user_data["times"]
    times.append(text)

    num_times = context.user_data["num_times"]

    if len(times) < num_times:
        slot_num = len(times) + 1
        await update.message.reply_text(f"Time for dose {slot_num}?")
        return TIME_SLOT

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
        add_jobs_for_medication(med.id, med.schedules)

        food_label = FOOD_RULE_LABELS.get(med.food_rule, med.food_rule)
        times_str = ", ".join(times)
        person_name = context.user_data["person_name"]

        await update.message.reply_text(
            f"✅ Added successfully!\n\n"
            f"💊 {person_name} — {med.name} {med.dose}\n"
            f"{food_label} · {times_str}\n\n"
            f"Reminders are active."
        )
    finally:
        db.close()

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
        TIME_SLOT: [MessageHandler(chat_filter() & ~filters.COMMAND, time_slot_entered)],
    },
    fallbacks=[CommandHandler("cancel", cancel, filters=chat_filter())],
    per_message=False,
)
