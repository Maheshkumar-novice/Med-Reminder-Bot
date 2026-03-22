"""Application entrypoint — starts bot and scheduler."""

import logging
import warnings

from telegram import BotCommand
from telegram.warnings import PTBUserWarning

warnings.filterwarnings("ignore", category=PTBUserWarning, message=".*per_message.*")

from medremind.bot import create_bot_app
from medremind.database import init_db
from medremind.scheduler import refresh_jobs, scheduler, set_bot_app

BOT_COMMANDS = [
    BotCommand("add", "Add a new medication"),
    BotCommand("list", "List all medications"),
    BotCommand("pause", "Pause a medication"),
    BotCommand("resume", "Resume a paused medication"),
    BotCommand("edit", "Edit an existing medication"),
    BotCommand("delete", "Delete a medication"),
    BotCommand("today", "Remaining reminders for today"),
    BotCommand("addperson", "Add a new person"),
    BotCommand("listpersons", "List all persons"),
    BotCommand("removeperson", "Remove a person"),
    BotCommand("help", "Show all commands"),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _post_init(app):
    """Called after Application.initialize() — start scheduler inside the event loop."""
    scheduler.start()
    refresh_jobs()
    set_bot_app(app)
    await app.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Scheduler started, bot commands registered")


async def _post_shutdown(app):
    """Called after Application.shutdown() — clean up scheduler."""
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")


def cli():
    """CLI entrypoint for the medremind command."""
    init_db()
    logger.info("Database initialized")

    app = create_bot_app(post_init=_post_init, post_shutdown=_post_shutdown)

    logger.info("Starting Telegram bot polling")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    cli()
