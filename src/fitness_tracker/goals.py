"""Overall recurring targets; legacy profile fields remain compatible daily/weekly averages."""

import calendar
import math
from datetime import date, timedelta


def calendar_window(goal, reference):
    if goal["unit"] == "month":
        ordinal = reference.year * 12 + reference.month - goal["period"]
        start = date(ordinal // 12, ordinal % 12 + 1, 1)
        end = date(
            reference.year, reference.month, calendar.monthrange(reference.year, reference.month)[1]
        )
    elif goal["unit"] == "week":
        end = reference + timedelta(days=6 - reference.weekday())
        start = end - timedelta(days=goal["period"] * 7 - 1)
    else:
        end = reference
        start = end - timedelta(days=goal["period"] - 1)
    return start, end


def goal_days(goal, reference=None):
    start, end = calendar_window(goal, reference or date.today())
    return (end - start).days + 1


def legacy_goals(profile):
    return {
        "workout": {"amount": profile["weekly_goal"], "period": 1, "unit": "week"},
        "protein": {"amount": profile["protein_goal"], "period": 1, "unit": "day"},
        "creatine": {"amount": profile["creatine_goal"], "period": 1, "unit": "day"},
    }


def numeric(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Enter a valid {label}.") from None
    if isinstance(value, bool) or not math.isfinite(result):
        raise ValueError(f"Enter a valid {label}.")
    return result


def validate_goals(raw):
    if not isinstance(raw, dict) or set(raw) != {"workout", "protein", "creatine"}:
        raise ValueError("Set overall gym, protein and creatine goals.")
    result = {}
    for key, label in (("workout", "gym days"), ("protein", "protein"), ("creatine", "creatine")):
        goal = raw[key]
        if not isinstance(goal, dict) or goal.get("unit") not in ("day", "week", "month"):
            raise ValueError("Choose days, weeks or calendar months for each goal.")
        unit = goal["unit"]
        period = numeric(goal.get("period"), "timeframe")
        if period != int(period) or not 1 <= period <= {"day": 365, "week": 52, "month": 120}[unit]:
            raise ValueError("Use 1–365 days, 1–52 weeks or 1–120 calendar months.")
        days = int(period) * {"day": 1, "week": 7, "month": 31}[unit]
        amount = numeric(goal.get("amount"), label + " target")
        maximum = days * {"workout": 1, "protein": 500, "creatine": 20}[key]
        if not (0 if key == "creatine" else 0.01) <= amount <= maximum:
            raise ValueError(f"Enter a {label} target within 0–{maximum} for this timeframe.")
        if key == "workout" and (amount < 1 or amount != int(amount)):
            raise ValueError("Gym days must be a positive whole number.")
        result[key] = {"amount": amount, "period": int(period), "unit": unit}
    return result


def with_goals(profile, goals=None):
    result = dict(profile)
    result["goals"] = validate_goals(goals if goals is not None else legacy_goals(profile))
    for key, legacy, factor in (
        ("workout", "weekly_goal", 7),
        ("protein", "protein_goal", 1),
        ("creatine", "creatine_goal", 1),
    ):
        goal = result["goals"][key]
        days = goal_days(goal)
        result[legacy] = goal["amount"] / days * factor
    return result
