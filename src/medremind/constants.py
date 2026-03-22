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

FOOD_RULE_OPTIONS = FOOD_RULE_LABELS

SUGGESTED_TIMES = {
    1: ["08:00"],
    2: ["08:00", "20:00"],
    3: ["08:00", "14:00", "20:00"],
    4: ["08:00", "12:00", "16:00", "20:00"],
}

EDITABLE_MED_FIELDS = {"name", "dose", "food_rule"}


def chat_filter():
    """Filter that only accepts messages from the configured group chat."""
    return filters.Chat(chat_id=settings.telegram_group_chat_id)
