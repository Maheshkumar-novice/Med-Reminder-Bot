"""Conversation handler for /add command."""

import re

from telegram import Update
from telegram.ext import (
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

# Conversation states
PERSON, MED_NAME, DOSE, FOOD_RULE, NUM_TIMES, TIME_SLOT = range(6)

FOOD_RULE_OPTIONS = {
    "1": "before_food",
    "2": "after_food",
    "3": "with_food",
    "4": "empty_stomach",
    "5": "any",
}


async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        persons = get_persons(db)
    finally:
        db.close()

    lines = ["Who is this for?"]
    for i, p in enumerate(persons, 1):
        lines.append(f"{i}. {p.name}")

    context.user_data["persons"] = {str(i): p.id for i, p in enumerate(persons, 1)}
    context.user_data["person_names"] = {str(i): p.name for i, p in enumerate(persons, 1)}

    await update.message.reply_text("\n".join(lines))
    return PERSON


async def person_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    persons = context.user_data.get("persons", {})

    if choice not in persons:
        await update.message.reply_text("Please pick a number from the list.")
        return PERSON

    context.user_data["person_id"] = persons[choice]
    context.user_data["person_name"] = context.user_data["person_names"][choice]

    await update.message.reply_text("Medication name?")
    return MED_NAME


async def med_name_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["med_name"] = update.message.text.strip()
    await update.message.reply_text("Dose? (e.g. 500mg, 1 tablet)")
    return DOSE


async def dose_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["dose"] = update.message.text.strip()
    await update.message.reply_text(
        "Food rule?\n"
        "1. Before food\n"
        "2. After food\n"
        "3. With food\n"
        "4. Empty stomach\n"
        "5. Any time"
    )
    return FOOD_RULE


async def food_rule_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    if choice not in FOOD_RULE_OPTIONS:
        await update.message.reply_text("Please pick a number from the list.")
        return FOOD_RULE

    context.user_data["food_rule"] = FOOD_RULE_OPTIONS[choice]
    await update.message.reply_text("How many times per day?")
    return NUM_TIMES


async def num_times_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        n = int(text)
        if n < 1 or n > 4:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Please enter a number between 1 and 4.")
        return NUM_TIMES

    context.user_data["num_times"] = n
    context.user_data["times"] = []
    await update.message.reply_text("Time for dose 1? (HH:MM, 24hr format)")
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

    # All times collected — save to DB
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
        # Schedule jobs
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
        PERSON: [MessageHandler(chat_filter() & ~filters.COMMAND, person_chosen)],
        MED_NAME: [MessageHandler(chat_filter() & ~filters.COMMAND, med_name_entered)],
        DOSE: [MessageHandler(chat_filter() & ~filters.COMMAND, dose_entered)],
        FOOD_RULE: [MessageHandler(chat_filter() & ~filters.COMMAND, food_rule_chosen)],
        NUM_TIMES: [MessageHandler(chat_filter() & ~filters.COMMAND, num_times_entered)],
        TIME_SLOT: [MessageHandler(chat_filter() & ~filters.COMMAND, time_slot_entered)],
    },
    fallbacks=[CommandHandler("cancel", cancel, filters=chat_filter())],
)
