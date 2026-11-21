"""The core flow, independent of the chat app:

    photo/caption -> analyzer (what + how much) -> nutrition lookup -> storage

The Telegram bot is a thin layer over this class, so another chat front end
(WhatsApp, a web form) can reuse it unchanged.
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .analyzer import MealAnalyzer
from .models import MealEntry, default_meal_type
from .nutrition import UsdaNutritionLookup
from .storage import MealStore


@dataclass
class LoggedMeal:
    entries: list[MealEntry]  # empty when no food was found
    comment: str


class MealService:
    def __init__(
        self,
        analyzer: MealAnalyzer,
        nutrition: UsdaNutritionLookup,
        store: MealStore,
        default_user: str,
    ):
        self.analyzer = analyzer
        self.nutrition = nutrition
        self.store = store
        self.default_user = default_user

    async def log_meal(
        self,
        eaten_at: datetime,
        image: Optional[bytes] = None,
        media_type: str = "image/jpeg",
        caption: str = "",
    ) -> LoggedMeal:
        analysis = await self.analyzer.analyze(image, media_type, caption)
        if not analysis.items:
            return LoggedMeal([], analysis.comment)

        meal_id = "m-" + uuid.uuid4().hex[:10]
        person = (analysis.person or self.default_user).strip()
        meal_type = analysis.meal_type or default_meal_type(eaten_at)
        looked_up = await asyncio.gather(*(self.nutrition.lookup(i) for i in analysis.items))

        entries = [
            MealEntry(
                meal_id=meal_id,
                eaten_at=eaten_at,
                meal_type=meal_type,
                person=person,
                food=item.name,
                grams=round(item.grams),
                nutrients=nutrients,
                source=source,
                note=note,
            )
            for item, (nutrients, source, note) in zip(analysis.items, looked_up)
        ]
        # Storage libraries are blocking; run them off the event loop.
        await asyncio.to_thread(self.store.add_entries, entries)
        return LoggedMeal(entries, analysis.comment)

    async def entries_for_days(
        self, now: datetime, days: int, person: Optional[str]
    ) -> list[MealEntry]:
        """Entries for the last `days` calendar days, today included."""
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = start_of_today - timedelta(days=days - 1)
        end = start_of_today + timedelta(days=1)
        return await asyncio.to_thread(self.store.get_entries, start, end, person)

    async def delete_meal(self, meal_id: str) -> int:
        return await asyncio.to_thread(self.store.delete_meal, meal_id)
