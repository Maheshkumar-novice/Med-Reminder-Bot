"""Shared constants and helpers."""

from telegram.ext import filters

from medremind.config import settings

FOOD_RULE_LABELS = {
    "before_food": "Before food",
    "after_food": "After food",
    "with_food": "With food",
    "empty_stomach": "Empty stomach",
    "any": "Any time",
}


def chat_filter():
    """Filter that only accepts messages from the configured group chat."""
    return filters.Chat(chat_id=settings.telegram_group_chat_id)
