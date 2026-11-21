import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from nutri_ai import reports
from nutri_ai.analyzer import FoodItem, MealAnalysis
from nutri_ai.config import load_settings
from nutri_ai.models import Nutrients, default_meal_type
from nutri_ai.nutrition import UsdaNutritionLookup, pick_match
from nutri_ai.service import MealService
from nutri_ai.storage import create_store
from nutri_ai.storage.sqlite import SqliteStore

TZ = timezone(timedelta(hours=7))
NOON = datetime(2026, 11, 14, 12, 30, tzinfo=TZ)

RICE = FoodItem(
    name="Steamed rice", usda_query="rice, white, cooked", grams=200,
    calories=260, protein_g=5, carbs_g=57, fat_g=0.5, fiber_g=1, sugar_g=0, sodium_mg=2,
)  # fmt: skip
USDA_RICE = {
    "description": "Rice, white, medium-grain, cooked",
    "foodNutrients": [
        {"nutrientId": 1008, "value": 130},
        {"nutrientId": 1003, "value": 2.38},
        {"nutrientId": 1005, "value": 28.6},
    ],
}
USDA_RICE_FLOUR = {"description": "Rice flour", "foodNutrients": [{"nutrientId": 1008, "value": 366}]}


class FakeAnalyzer:
    def __init__(self, analysis):
        self.analysis = analysis

    async def analyze(self, image=None, media_type="image/jpeg", caption=""):
        return self.analysis


class FakeLookup(UsdaNutritionLookup):
    def __init__(self, foods):
        self.foods = foods

    async def _search(self, query):
        return self.foods


def make_service(analysis, foods, store):
    return MealService(FakeAnalyzer(analysis), FakeLookup(foods), store, default_user="me")


def test_default_meal_type():
    at = lambda h: default_meal_type(NOON.replace(hour=h))
    assert [at(7), at(12), at(16), at(19), at(23)] == ["breakfast", "lunch", "snack", "dinner", "snack"]


def test_pick_match_scales_to_portion_and_rejects_bad_matches():
    nutrients, description = pick_match(RICE, [USDA_RICE_FLOUR, USDA_RICE])
    assert description.startswith("Rice, white")
    assert nutrients.calories == 260 and nutrients.carbs_g == 57.2
    assert pick_match(RICE, [USDA_RICE_FLOUR]) is None  # 732 kcal vs estimate of 260


def test_log_meal_defaults_and_roundtrip(tmp_path):
    store = SqliteStore(str(tmp_path / "meals.db"))
    service = make_service(MealAnalysis(items=[RICE]), [USDA_RICE], store)
    meal = asyncio.run(service.log_meal(NOON, caption="rice"))

    [entry] = asyncio.run(service.entries_for_days(NOON, 1, "ME"))  # person is case-insensitive
    assert entry == meal.entries[0]
    assert (entry.person, entry.meal_type, entry.source) == ("me", "lunch", "usda")

    assert asyncio.run(service.entries_for_days(NOON + timedelta(days=1), 1, "me")) == []
    assert asyncio.run(service.delete_meal(entry.meal_id)) == 1
    assert asyncio.run(service.entries_for_days(NOON, 1, None)) == []


def test_caption_person_and_meal_type_win_and_estimate_fallback(tmp_path):
    store = SqliteStore(str(tmp_path / "meals.db"))
    analysis = MealAnalysis(items=[RICE], person="Sarah", meal_type="dinner")
    meal = asyncio.run(make_service(analysis, [], store).log_meal(NOON))
    entry = meal.entries[0]
    assert (entry.person, entry.meal_type, entry.source) == ("Sarah", "dinner", "estimate")
    assert entry.nutrients.calories == 260
    assert "for Sarah" in reports.logged_meal(meal.entries)


def test_no_food_saves_nothing(tmp_path):
    store = SqliteStore(str(tmp_path / "meals.db"))
    meal = asyncio.run(make_service(MealAnalysis(items=[], comment="No food."), [], store).log_meal(NOON))
    assert meal.entries == [] and store.get_entries(NOON - timedelta(days=1), NOON + timedelta(days=1)) == []


def test_period_summary_averages(tmp_path):
    store = SqliteStore(str(tmp_path / "meals.db"))
    service = make_service(MealAnalysis(items=[RICE]), [USDA_RICE], store)
    for when in (NOON, NOON.replace(hour=19), NOON - timedelta(days=1)):
        asyncio.run(service.log_meal(when))
    entries = asyncio.run(service.entries_for_days(NOON, 7, "me"))
    text = reports.period_summary(entries, "me", 7)
    assert "Sat 14 Nov: 520 kcal" in text and "Fri 13 Nov: 260 kcal" in text
    assert "Daily average (2 logged days): 390 kcal" in text
    assert "Lunch: 260 kcal (2 logged)" in text and "Dinner: 260 kcal (1 logged)" in text


def test_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PROVIDER", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "x.db"))
    assert isinstance(create_store(load_settings()), SqliteStore)
    monkeypatch.setenv("STORAGE_PROVIDER", "nope")
    with pytest.raises(ValueError, match="sheets, sqlite"):
        create_store(load_settings())
