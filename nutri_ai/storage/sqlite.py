"""SQLite provider: a local file, no account needed. Handy for trying the bot out."""

import sqlite3
from datetime import datetime
from typing import Optional

from ..models import MealEntry
from .base import COLUMNS, NUTRIENT_COLUMNS, MealStore, entry_to_row, matches, row_to_entry


class SqliteStore(MealStore):
    def __init__(self, path: str):
        # The bot calls the store from worker threads, one call at a time.
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        numeric = {"grams", *NUTRIENT_COLUMNS}
        columns = ", ".join(f"{c} {'REAL' if c in numeric else 'TEXT'}" for c in COLUMNS)
        self.db.execute(f"CREATE TABLE IF NOT EXISTS meals ({columns})")
        self.db.commit()

    def add_entries(self, entries: list[MealEntry]) -> None:
        placeholders = ", ".join("?" for _ in COLUMNS)
        self.db.executemany(
            f"INSERT INTO meals VALUES ({placeholders})", [entry_to_row(e) for e in entries]
        )
        self.db.commit()

    def get_entries(
        self, start: datetime, end: datetime, person: Optional[str] = None
    ) -> list[MealEntry]:
        rows = self.db.execute("SELECT * FROM meals ORDER BY timestamp").fetchall()
        entries = [row_to_entry(dict(r)) for r in rows]
        return [e for e in entries if matches(e, start, end, person)]

    def delete_meal(self, meal_id: str) -> int:
        cursor = self.db.execute("DELETE FROM meals WHERE meal_id = ?", (meal_id,))
        self.db.commit()
        return cursor.rowcount
