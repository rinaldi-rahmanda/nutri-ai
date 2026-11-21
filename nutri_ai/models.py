"""Plain data types shared by every part of the app."""

from dataclasses import dataclass, field
from datetime import datetime

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")


@dataclass
class Nutrients:
    calories: float = 0.0  # kcal
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: float = 0.0
    sugar_g: float = 0.0
    sodium_mg: float = 0.0

    def scaled(self, factor: float) -> "Nutrients":
        return Nutrients(**{k: round(v * factor, 1) for k, v in vars(self).items()})

    def __add__(self, other: "Nutrients") -> "Nutrients":
        return Nutrients(**{k: round(v + getattr(other, k), 1) for k, v in vars(self).items()})


@dataclass
class MealEntry:
    """One food item of one meal. A meal with 3 foods is 3 entries sharing a meal_id."""

    meal_id: str
    eaten_at: datetime  # timezone-aware, in the configured local timezone
    meal_type: str  # one of MEAL_TYPES
    person: str
    food: str
    grams: float
    nutrients: Nutrients = field(default_factory=Nutrients)
    source: str = "estimate"  # "usda" (dataset match) or "estimate" (model's own guess)
    note: str = ""  # e.g. the matched dataset food, or the photo caption


def default_meal_type(when: datetime) -> str:
    """Guess the mealtime from the clock when the user didn't say."""
    hour = when.hour
    if 4 <= hour < 11:
        return "breakfast"
    if 11 <= hour < 15:
        return "lunch"
    if 18 <= hour < 22:
        return "dinner"
    return "snack"
