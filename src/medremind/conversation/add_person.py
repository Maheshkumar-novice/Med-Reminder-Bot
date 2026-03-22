"""Conversation handler for /addperson command."""

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from medremind.constants import chat_filter
from medremind.crud import add_person
from medremind.database import get_db

NAME = 0


async def addperson_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("What is the person's name?")
    return NAME


async def name_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Name cannot be empty. Try again.")
        return NAME

    db = get_db()
    try:
        person = add_person(db, name)
        if person:
            await update.message.reply_text(f"✅ Added {person.name}.")
        else:
            await update.message.reply_text(f"A person named \"{name}\" already exists.")
    finally:
        db.close()

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


addperson_conversation = ConversationHandler(
    entry_points=[CommandHandler("addperson", addperson_start, filters=chat_filter())],
    states={
        NAME: [MessageHandler(chat_filter() & ~filters.COMMAND, name_entered)],
    },
    fallbacks=[CommandHandler("cancel", cancel, filters=chat_filter())],
)
