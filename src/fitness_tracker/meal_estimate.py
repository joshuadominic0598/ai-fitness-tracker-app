"""Small whole-meal estimates: no ingredient ledger or arithmetic contract."""

import math

from .store import valid_date

MEAL_GUIDANCE = """Meal: estimate the WHOLE meal or described day's food freely from your nutrition knowledge. Return action meal for requested logging, proposal {date,description,protein,low,high,calories}. description is 1–2 short sentences saying what the person ate. protein is the main estimated TOTAL grams, low/high are a realistic protein range containing it, and calories is estimated TOTAL kcal including oils, sauces and drinks. Use supplied portions and labels when available. When quantities are unsure, assume plausible portions and widen the range; a party meal, feeling full, mixed dishes or multiple meals is enough to estimate. Do not demand exact weights or block an estimate over uncertain portions. Ask only if no food is described at all. Do not return ingredient lists, per-food estimates, calculations or arithmetic expressions. For several meals on one day, make one combined food entry covering them all: estimate their combined intake, not an average meal. Include rice, breads, noodles and cooking fats as well as the protein foods in total kcal. Calories are estimated from all the food, not just from protein. Clearly describe it as an estimate. For a correction, use the previous meal description and totals as context and update the requested food or quantity. For an edited full message, use that new message as the complete source. An estimate alone does not authorize logging; use answer unless logging was requested. Approval is still required to save."""


def normalize_meal_estimate(raw, selected_date):
    """Keep totals only and repair range formatting without rejecting a useful estimate."""
    if not isinstance(raw, dict):
        raise ValueError("The meal estimate needs protein and kcal totals.")
    if raw.get("confirmed_totals"):
        raise ValueError("Only manual approval can confirm adjusted totals.")

    def amount(key):
        value = raw.get(key)
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            raise ValueError("The meal " + key + " needs a number.")
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError("The meal " + key + " needs a number.") from None
        if not math.isfinite(value) or value < 0:
            raise ValueError("The meal " + key + " needs a nonnegative estimate.")
        return round(min(value, 10000 if key == "calories" else 500), 2)

    protein, calories = amount("protein"), amount("calories")
    if protein is None or calories is None:
        raise ValueError(
            "Estimate both total protein grams and total calories in kcal for this food."
        )
    low, high = amount("low"), amount("high")
    low = round(protein * 0.75, 2) if low is None else low
    high = round(min(500, max(protein * 1.25, protein + 2)), 2) if high is None else high
    low, high = sorted((low, high))
    if low == high and protein > 0:
        low, high = (
            round(max(0, min(low, protein) * 0.75), 2),
            round(min(500, max(high, protein) * 1.25), 2),
        )
    if not low <= protein <= high or (low != high and protein in (low, high)):
        protein = round((low + high) / 2, 2)
    description = raw.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("Briefly describe the food in the meal estimate.")
    try:
        day = valid_date(raw.get("date"))
    except (ValueError, TypeError):
        day = valid_date(selected_date)
    return {
        "date": day,
        "description": description.strip()[:2000],
        "protein": protein,
        "calories": calories,
        "low": low,
        "high": high,
        "source": "ai",
    }
