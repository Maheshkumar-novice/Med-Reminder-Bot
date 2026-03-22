"""Application entrypoint — starts bot and scheduler."""

import logging

from medremind.bot import create_bot_app
from medremind.database import init_db
from medremind.scheduler import load_all_jobs, scheduler, set_bot_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _post_init(app):
    """Called after Application.initialize() — start scheduler inside the event loop."""
    scheduler.start()
    load_all_jobs()
    set_bot_app(app)
    logger.info("Scheduler started")


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
