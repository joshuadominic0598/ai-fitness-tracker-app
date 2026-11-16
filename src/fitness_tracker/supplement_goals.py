"""Supplement targets and comparable quantities, without prescribing doses."""

from .goals import numeric

MEASURES = (
    "days",
    "doses",
    "g",
    "mg",
    "mcg",
    "ml",
    "capsule",
    "tablet",
    "softgel",
    "serving",
    "scoop",
    "drop",
    "IU",
)
MASS = {"g": 1, "mg": 0.001, "mcg": 0.000001}


def canonical_unit(value):
    value = value.strip().casefold().replace("μ", "u").replace("µ", "u")
    aliases = {
        "grams": "g",
        "gram": "g",
        "milligrams": "mg",
        "milligram": "mg",
        "ug": "mcg",
        "microgram": "mcg",
        "micrograms": "mcg",
        "milliliter": "ml",
        "milliliters": "ml",
        "iu": "IU",
    }
    return aliases.get(
        value,
        value[:-1]
        if value in ("capsules", "tablets", "softgels", "servings", "scoops", "drops")
        else value,
    )


def default_goal():
    # A frequency target preserves the old once-per-day routine, never invents a dose.
    return {"amount": 1, "measure": "days", "period": 1, "unit": "day"}


def validate_supplement_goals(raw, options):
    if not isinstance(raw, dict) or len(raw) > 100:
        raise ValueError("Enter a goal for each selected supplement.")
    known = {name.casefold(): name for name in options}
    result = {}
    for name, goal in raw.items():
        if not isinstance(name, str) or name.casefold() not in known:
            raise ValueError("Choose a supplement from your selection list.")
        name = known[name.casefold()]
        if name == "Creatine":
            raise ValueError("Creatine has its own dedicated goal.")
        if name in result or not isinstance(goal, dict):
            raise ValueError("Enter one valid goal per supplement.")
        measure = canonical_unit(str(goal.get("measure", "")))
        if measure not in MEASURES:
            raise ValueError("Choose a supported supplement goal unit.")
        unit = goal.get("unit")
        period = numeric(goal.get("period"), "supplement timeframe")
        amount = numeric(goal.get("amount"), "supplement target")
        if (
            unit not in ("day", "week", "month")
            or period != int(period)
            or not 1 <= period <= {"day": 365, "week": 52, "month": 120}.get(unit, 0)
        ):
            raise ValueError("Use 1–365 days, 1–52 weeks or 1–120 calendar months.")
        days = int(period) * {"day": 1, "week": 7, "month": 31}[unit]
        if not 0 < amount <= 100000 * days:
            raise ValueError("Enter a positive supplement target.")
        if measure in ("days", "doses") and amount != int(amount):
            raise ValueError("Days taken and doses must use whole numbers.")
        if measure == "days" and amount > days:
            raise ValueError("Days taken cannot exceed the number of days in the timeframe.")
        result[name] = {"amount": amount, "measure": measure, "period": int(period), "unit": unit}
    return result


def hydrate_supplement_goals(profile):
    result = validate_supplement_goals(profile.get("supplement_goals", {}), profile["supplements"])
    for name in profile["consistency_supplements"]:
        if name != "Creatine":
            result.setdefault(name, default_goal())
    return result


def quantity(entry, measure):
    if entry["amount"] <= 0:
        return None
    if measure in ("days", "doses"):
        return 1
    source = canonical_unit(entry["unit"])
    if source == measure:
        return entry["amount"]
    if source in MASS and measure in MASS:
        return entry["amount"] * MASS[source] / MASS[measure]
    return None


def is_creatine(entry):
    """Recognize dedicated entries and legacy records without rewriting journal data."""
    return entry.get("kind") == "creatine" or (
        entry.get("kind") == "supplement"
        and str(entry.get("name", "")).strip().casefold() == "creatine"
    )


def daily_values(entries, name, goal):
    values = {}
    for entry in entries:
        if not (
            is_creatine(entry)
            if name.casefold() == "creatine"
            else entry["kind"] == "supplement"
            and not is_creatine(entry)
            and entry["name"].casefold() == name.casefold()
        ):
            continue
        value = quantity(entry, goal["measure"])
        if value is not None:
            values[entry["date"]] = (
                1 if goal["measure"] == "days" else values.get(entry["date"], 0) + value
            )
    return values
