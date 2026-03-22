"""Telegram bot handlers and setup."""

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from medremind.config import settings
from medremind.constants import FOOD_RULE_LABELS, chat_filter
from medremind.conversation.add_med import add_conversation
from medremind.conversation.add_person import addperson_conversation
from medremind.conversation.delete_med import delete_conversation
from medremind.conversation.pause_med import pause_conversation
from medremind.conversation.remove_person import removeperson_conversation
from medremind.conversation.resume_med import resume_conversation
from medremind.crud import get_persons, list_medications
from medremind.database import get_db

logger = logging.getLogger(__name__)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list command — show all medications grouped by person."""
    db = get_db()
    try:
        meds = list_medications(db)

        if not meds:
            await update.message.reply_text("No medications found. Use /add to create one.")
            return

        # Group by person
        by_person: dict[str, list] = {}
        for med in meds:
            name = med.person.name
            by_person.setdefault(name, []).append(med)

        lines = []
        for person_name, person_meds in by_person.items():
            lines.append(f"👤 {person_name}")
            for med in person_meds:
                status = " [PAUSED]" if not med.active else ""
                food_label = FOOD_RULE_LABELS.get(med.food_rule, med.food_rule)
                times = ", ".join(s.time_hhmm for s in med.schedules)
                end_info = ""
                if med.end_date:
                    end_info = f" (until {med.end_date})"
                lines.append(
                    f"  💊 {med.name} {med.dose}{status}\n"
                    f"     {food_label} · {times}{end_info}"
                )
            lines.append("")

        await update.message.reply_text("\n".join(lines).strip())
    finally:
        db.close()


async def cmd_listpersons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /listpersons command."""
    db = get_db()
    try:
        persons = get_persons(db)

        if not persons:
            await update.message.reply_text("No persons found. Use /addperson to add one.")
            return

        lines = ["👥 Persons"]
        for p in persons:
            lines.append(f"  • {p.name}")

        await update.message.reply_text("\n".join(lines))
    finally:
        db.close()


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await update.message.reply_text(
        "📋 MedRemind Commands\n\n"
        "/add — Add a new medication\n"
        "/list — List all medications\n"
        "/pause — Pause a medication\n"
        "/resume — Resume a paused medication\n"
        "/delete — Permanently delete a medication\n"
        "/addperson — Add a new person\n"
        "/listpersons — List all persons\n"
        "/removeperson — Remove a person\n"
        "/help — Show this help message"
    )


PostHook = Callable[[Application], Coroutine[Any, Any, None]]


def create_bot_app(
    post_init: PostHook | None = None,
    post_shutdown: PostHook | None = None,
) -> Application:
    """Create and configure the Telegram bot application."""
    builder = Application.builder().token(settings.telegram_bot_token.get_secret_value())
    if post_init:
        builder = builder.post_init(post_init)
    if post_shutdown:
        builder = builder.post_shutdown(post_shutdown)
    app = builder.build()

    # Conversation handlers (order matters — add before simple handlers)
    app.add_handler(add_conversation)
    app.add_handler(addperson_conversation)
    app.add_handler(removeperson_conversation)
    app.add_handler(pause_conversation)
    app.add_handler(resume_conversation)
    app.add_handler(delete_conversation)

    # Simple command handlers
    app.add_handler(CommandHandler("list", cmd_list, filters=chat_filter()))
    app.add_handler(CommandHandler("listpersons", cmd_listpersons, filters=chat_filter()))
    app.add_handler(CommandHandler("help", cmd_help, filters=chat_filter()))
    app.add_handler(CommandHandler("start", cmd_help, filters=chat_filter()))

    return app
