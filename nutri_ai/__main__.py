"""Entry point: `uv run python -m nutri_ai`"""

import logging
import os
import sys

from .analyzer import MealAnalyzer
from .config import load_settings
from .nutrition import UsdaNutritionLookup
from .service import MealService
from .storage import create_store
from .telegram_bot import build_application


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO lines include the bot token

    settings = load_settings()
    if not settings.telegram_bot_token:
        sys.exit("TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")

    service = MealService(
        analyzer=MealAnalyzer(settings.claude_model),
        nutrition=UsdaNutritionLookup(settings.usda_api_key),
        store=create_store(settings),
        default_user=settings.default_user,
    )
    logging.info("Storage: %s. Bot is running, press Ctrl+C to stop.", settings.storage_provider)
    build_application(settings, service).run_polling()


if __name__ == "__main__":
    main()
