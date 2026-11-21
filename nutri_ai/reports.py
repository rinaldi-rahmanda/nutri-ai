"""Turns stored entries into the text the bot replies with. Pure functions, no I/O."""

from collections import defaultdict

from .models import MEAL_TYPES, MealEntry, Nutrients


def total(entries: list[MealEntry]) -> Nutrients:
    result = Nutrients()
    for e in entries:
        result = result + e.nutrients
    return result


def macros(n: Nutrients) -> str:
    return (
        f"{n.calories:.0f} kcal | protein {n.protein_g:.0f} g | "
        f"carbs {n.carbs_g:.0f} g | fat {n.fat_g:.0f} g"
    )


def group_by(entries: list[MealEntry], key) -> dict[str, list[MealEntry]]:
    groups: dict[str, list[MealEntry]] = defaultdict(list)
    for e in entries:
        groups[key(e)].append(e)
    return groups


def logged_meal(entries: list[MealEntry], comment: str = "") -> str:
    first = entries[0]
    lines = [f"Logged {first.meal_type} for {first.person} ({first.eaten_at:%a %d %b, %H:%M})", ""]
    for e in entries:
        marker = "" if e.source == "usda" else " ~"
        lines.append(f"- {e.food}, {e.grams:.0f} g: {e.nutrients.calories:.0f} kcal{marker}")
    lines += ["", "Total: " + macros(total(entries))]
    if any(e.source != "usda" for e in entries):
        lines.append("~ = AI estimate (no dataset match)")
    if comment:
        lines += ["", comment]
    lines += ["", "Wrong? Send /undo to remove it."]
    return "\n".join(lines)


def day_summary(entries: list[MealEntry], person: str) -> str:
    if not entries:
        return f"Nothing logged today for {person}."
    lines = [f"Today for {person}", ""]
    by_meal = group_by(entries, lambda e: e.meal_type)
    for meal_type in MEAL_TYPES:
        if meal_type in by_meal:
            foods = ", ".join(e.food for e in by_meal[meal_type])
            lines.append(f"{meal_type.capitalize()}: {total(by_meal[meal_type]).calories:.0f} kcal ({foods})")
    n = total(entries)
    lines += ["", "Total: " + macros(n), f"Fiber {n.fiber_g:.0f} g | sugar {n.sugar_g:.0f} g | sodium {n.sodium_mg:.0f} mg"]
    return "\n".join(lines)


def period_summary(entries: list[MealEntry], person: str, days: int) -> str:
    if not entries:
        return f"Nothing logged in the last {days} days for {person}."
    by_day = group_by(entries, lambda e: e.eaten_at.strftime("%Y-%m-%d"))
    lines = [f"Last {days} days for {person}", ""]
    for day in sorted(by_day):
        lines.append(f"{by_day[day][0].eaten_at:%a %d %b}: {total(by_day[day]).calories:.0f} kcal")

    # Averages are over days that have at least one entry, so a day you
    # forgot to log doesn't drag the average down.
    logged_days = len(by_day)
    lines += ["", f"Daily average ({logged_days} logged days): " + macros(total(entries).scaled(1 / logged_days))]

    lines += ["", "Average per mealtime:"]
    by_meal = group_by(entries, lambda e: e.meal_type)
    for meal_type in MEAL_TYPES:
        if meal_type in by_meal:
            meals = len({e.meal_id for e in by_meal[meal_type]})
            average = total(by_meal[meal_type]).scaled(1 / meals)
            lines.append(f"{meal_type.capitalize()}: {average.calories:.0f} kcal ({meals} logged)")
    return "\n".join(lines)
