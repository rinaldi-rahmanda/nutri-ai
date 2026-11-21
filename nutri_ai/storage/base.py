"""The storage interface. Every database provider implements these three methods.

The rest of the app only ever talks to `MealStore`, so swapping Google Sheets
for another database means writing one new subclass and registering it in
factory.py. Nothing else changes.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from ..models import MealEntry, Nutrients

# Column order used by the row-based providers (Sheets, SQLite).
COLUMNS = [
    "meal_id", "timestamp", "date", "time", "meal_type", "person", "food", "grams",
    "calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "sodium_mg",
    "source", "note",
]  # fmt: skip
NUTRIENT_COLUMNS = COLUMNS[8:15]


class MealStore(ABC):
    @abstractmethod
    def add_entries(self, entries: list[MealEntry]) -> None:
        """Save the food items of one meal."""

    @abstractmethod
    def get_entries(
        self, start: datetime, end: datetime, person: Optional[str] = None
    ) -> list[MealEntry]:
        """Entries with start <= eaten_at < end, optionally for one person (case-insensitive)."""

    @abstractmethod
    def delete_meal(self, meal_id: str) -> int:
        """Delete every entry of a meal. Returns how many were deleted."""


def entry_to_row(e: MealEntry) -> list:
    return [
        e.meal_id,
        e.eaten_at.isoformat(timespec="seconds"),
        e.eaten_at.strftime("%Y-%m-%d"),
        e.eaten_at.strftime("%H:%M"),
        e.meal_type,
        e.person,
        e.food,
        e.grams,
        *[getattr(e.nutrients, c) for c in NUTRIENT_COLUMNS],
        e.source,
        e.note,
    ]


def row_to_entry(row: dict) -> MealEntry:
    def num(key: str) -> float:
        try:
            return float(row.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    return MealEntry(
        meal_id=str(row["meal_id"]),
        eaten_at=datetime.fromisoformat(str(row["timestamp"])),
        meal_type=str(row["meal_type"]),
        person=str(row["person"]),
        food=str(row["food"]),
        grams=num("grams"),
        nutrients=Nutrients(**{c: num(c) for c in NUTRIENT_COLUMNS}),
        source=str(row.get("source", "")),
        note=str(row.get("note", "")),
    )


def matches(e: MealEntry, start: datetime, end: datetime, person: Optional[str]) -> bool:
    if not start <= e.eaten_at < end:
        return False
    return person is None or e.person.lower() == person.lower()
