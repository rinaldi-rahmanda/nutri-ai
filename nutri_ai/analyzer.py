"""Step 1: look at the photo (and/or caption) and work out what was eaten.

Claude identifies each food, estimates the portion in grams, and gives its own
rough nutrition estimate. The estimate is only a fallback: nutrition.py replaces
it with dataset values whenever the dataset has a sensible match.
"""

import base64
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel

SYSTEM_PROMPT = """\
You are the food-recognition step of a personal nutrition tracker. The user sends \
a photo of a meal, a text description of one, or both. Your output is parsed by \
code and logged to a spreadsheet, so accuracy of the numbers matters more than prose.

List every distinct food and drink that was eaten. Split composite plates into \
their parts when the parts are visible (rice, chicken, vegetables as three items), \
but keep a true mixed dish (fried rice, curry, a sandwich) as one item. Estimate \
each portion's weight in grams as served, using plates, cutlery and hands in the \
photo for scale. When the caption states an amount, trust it over the photo.

For each item also give:
- usda_query: a short generic English search phrase in the style of the USDA \
FoodData Central database, e.g. "rice, white, cooked" or "chicken breast, grilled". \
For regional dishes the database is unlikely to have, use the closest generic \
description.
- Your own best estimate of the nutrients for the whole portion (not per 100 g). \
It is used when the database has no good match.

The caption may also say who ate the meal ("for Sarah", "Budi's lunch") and which \
mealtime it was. Set person and meal_type only when the caption actually says so; \
otherwise leave them null and the app applies its defaults. Do not guess the \
mealtime from the food.

If the message contains no food at all, return an empty items list and explain \
briefly in comment. Otherwise keep comment to one short sentence, or empty.
"""


class FoodItem(BaseModel):
    name: str
    usda_query: str
    grams: float
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    sugar_g: float
    sodium_mg: float


class MealAnalysis(BaseModel):
    items: list[FoodItem]
    person: Optional[str] = None
    meal_type: Optional[Literal["breakfast", "lunch", "dinner", "snack"]] = None
    comment: str = ""


class AnalysisError(Exception):
    """The model could not produce a usable analysis. The message is safe to show the user."""


class MealAnalyzer:
    def __init__(self, model: str, client: Optional[anthropic.AsyncAnthropic] = None):
        self.model = model
        # Reads ANTHROPIC_API_KEY from the environment.
        self.client = client or anthropic.AsyncAnthropic()
        # If the model's safety filter declines a request, let the API retry it
        # on a fallback model instead of failing. Haiku has no server-side
        # fallback, so it must not send the parameter.
        self.fallback_options: dict = {}
        if not model.startswith("claude-haiku"):
            self.fallback_options = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}

    async def analyze(
        self,
        image: Optional[bytes] = None,
        media_type: str = "image/jpeg",
        caption: str = "",
    ) -> MealAnalysis:
        content: list[dict] = []
        if image:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.standard_b64encode(image).decode("utf-8"),
                    },
                }
            )
        content.append({"type": "text", "text": f"Caption: {caption}" if caption else "(no caption)"})

        try:
            response = await self.client.beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
                output_format=MealAnalysis,
                **self.fallback_options,
            )
        except anthropic.RateLimitError as e:
            raise AnalysisError("The AI service is rate-limited right now. Try again in a minute.") from e
        except anthropic.APIStatusError as e:
            raise AnalysisError(f"The AI service returned an error ({e.status_code}): {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise AnalysisError("Could not reach the AI service. Check the network and try again.") from e

        if response.stop_reason == "refusal":
            raise AnalysisError("The AI declined to analyze that message.")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise AnalysisError("The AI's answer was cut off. Try again with a simpler photo.")
        return response.parsed_output
