"""Application configuration loaded from environment variables."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: SecretStr
    telegram_group_chat_id: int
    database_url: str = "sqlite:///./medremind.db"
    timezone: str = "Asia/Kolkata"
    persons: list[str] = []

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
