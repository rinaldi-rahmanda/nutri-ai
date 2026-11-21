"""Step 2: turn a recognized food + grams into nutrition numbers.

Looks the food up in USDA FoodData Central (free API, https://fdc.nal.usda.gov)
and scales the per-100 g values to the portion. If the dataset has no believable
match, the model's own estimate is kept and the entry is marked "estimate".

To use a different dataset, write another class with the same `lookup` method.
"""

import logging
from typing import Optional

import httpx

from .analyzer import FoodItem
from .models import Nutrients

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"

# USDA nutrient ids -> our field. Energy has three ids because newer
# "Foundation" foods report Atwater energy (2047/2048) instead of 1008.
NUTRIENT_IDS = {
    1008: "calories",
    2047: "calories",
    2048: "calories",
    1003: "protein_g",
    1005: "carbs_g",
    1004: "fat_g",
    1079: "fiber_g",
    2000: "sugar_g",
    1093: "sodium_mg",
}

# A dataset match is trusted only if its calories for the portion are within
# this factor of the model's estimate. This rejects wrong matches such as
# "fried rice" -> "rice flour".
MAX_DISAGREEMENT = 2.0


def model_estimate(item: FoodItem) -> Nutrients:
    return Nutrients(
        calories=item.calories,
        protein_g=item.protein_g,
        carbs_g=item.carbs_g,
        fat_g=item.fat_g,
        fiber_g=item.fiber_g,
        sugar_g=item.sugar_g,
        sodium_mg=item.sodium_mg,
    )


def per_100g(food: dict) -> Nutrients:
    """Read one USDA search result into Nutrients per 100 g."""
    values: dict[str, float] = {}
    for n in food.get("foodNutrients", []):
        key = NUTRIENT_IDS.get(n.get("nutrientId"))
        if key and key not in values and n.get("value") is not None:
            values[key] = float(n["value"])
    return Nutrients(**values)


def pick_match(item: FoodItem, foods: list[dict]) -> Optional[tuple[Nutrients, str]]:
    """Choose the search result that best agrees with the model's calorie estimate."""
    best = None
    for food in foods:
        portion = per_100g(food).scaled(item.grams / 100)
        if portion.calories <= 0 or item.calories <= 0:
            continue
        ratio = max(portion.calories, item.calories) / min(portion.calories, item.calories)
        if ratio <= MAX_DISAGREEMENT and (best is None or ratio < best[0]):
            best = (ratio, portion, food.get("description", ""))
    return (best[1], best[2]) if best else None


class UsdaNutritionLookup:
    def __init__(self, api_key: str, http: Optional[httpx.AsyncClient] = None):
        self.api_key = api_key
        self.http = http or httpx.AsyncClient(timeout=15)
        self._cache: dict[str, list[dict]] = {}

    async def _search(self, query: str) -> list[dict]:
        if query not in self._cache:
            response = await self.http.get(
                SEARCH_URL,
                params={
                    "api_key": self.api_key,
                    "query": query,
                    # Generic foods only; skips the huge branded-products set.
                    "dataType": "Foundation,SR Legacy",
                    "pageSize": 5,
                },
            )
            response.raise_for_status()
            self._cache[query] = response.json().get("foods", [])
        return self._cache[query]

    async def lookup(self, item: FoodItem) -> tuple[Nutrients, str, str]:
        """Returns (nutrients for the portion, source, note)."""
        try:
            match = pick_match(item, await self._search(item.usda_query))
        except (httpx.HTTPError, ValueError) as e:
            log.warning("USDA lookup failed for %r: %s", item.usda_query, e)
            match = None
        if match:
            return match[0], "usda", match[1]
        return model_estimate(item), "estimate", ""
