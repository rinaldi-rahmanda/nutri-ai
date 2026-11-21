"""All settings come from environment variables (see .env.example)."""

import os
from dataclasses import dataclass
from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    allowed_chat_ids: frozenset[int]  # empty = anyone can use the bot
    default_user: str
    timezone: tzinfo

    claude_model: str
    usda_api_key: str

    storage_provider: str  # "sheets" or "sqlite" (see storage/factory.py)
    google_sheet_id: str
    google_credentials_file: str
    sqlite_path: str


def load_settings() -> Settings:
    load_dotenv()
    env = os.environ.get
    tz_name = env("TIMEZONE", "")
    return Settings(
        telegram_bot_token=env("TELEGRAM_BOT_TOKEN", ""),
        allowed_chat_ids=frozenset(
            int(x) for x in env("ALLOWED_CHAT_IDS", "").replace(" ", "").split(",") if x
        ),
        default_user=env("DEFAULT_USER", "me"),
        # No TIMEZONE set -> use this machine's local timezone.
        timezone=ZoneInfo(tz_name) if tz_name else datetime.now().astimezone().tzinfo,
        claude_model=env("CLAUDE_MODEL", "claude-opus-5-5"),
        usda_api_key=env("USDA_API_KEY", "DEMO_KEY"),
        storage_provider=env("STORAGE_PROVIDER", "sheets").lower(),
        google_sheet_id=env("GOOGLE_SHEET_ID", ""),
        google_credentials_file=env("GOOGLE_CREDENTIALS_FILE", "google-credentials.json"),
        sqlite_path=env("SQLITE_PATH", "meals.db"),
    )
