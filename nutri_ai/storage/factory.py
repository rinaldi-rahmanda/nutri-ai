"""Builds the MealStore selected by STORAGE_PROVIDER.

To add a provider (Postgres, Supabase, Airtable, ...):
  1. Write a MealStore subclass in this folder.
  2. Add one builder line to PROVIDERS below.
  3. Set STORAGE_PROVIDER to its name.
"""

from typing import Callable

from ..config import Settings
from .base import MealStore


def _sheets(s: Settings) -> MealStore:
    from .google_sheets import GoogleSheetsStore  # imported lazily: needs gspread + credentials

    return GoogleSheetsStore(s.google_sheet_id, s.google_credentials_file)


def _sqlite(s: Settings) -> MealStore:
    from .sqlite import SqliteStore

    return SqliteStore(s.sqlite_path)


PROVIDERS: dict[str, Callable[[Settings], MealStore]] = {
    "sheets": _sheets,
    "sqlite": _sqlite,
}


def create_store(settings: Settings) -> MealStore:
    try:
        builder = PROVIDERS[settings.storage_provider]
    except KeyError:
        raise ValueError(
            f"Unknown STORAGE_PROVIDER {settings.storage_provider!r}. "
            f"Choose one of: {', '.join(PROVIDERS)}"
        ) from None
    return builder(settings)
