"""Separate cardio logs and personal weekly intensity-equivalent targets."""

import re

from .goals import numeric

# Moderate-equivalent minutes follow the CDC 2:1 rule; not a calorie conversion.
HIGH_WEIGHT = 2
ACTIVITIES = {
    "Your usual activities": ["Badminton", "Swimming", "Pickleball", "Cycling", "Running"],
    "Sports & games": [
        "Tennis",
        "Table tennis",
        "Squash",
        "Racquetball",
        "Basketball",
        "Football / soccer",
        "Futsal",
        "Volleyball",
        "Beach volleyball",
        "Hockey",
        "Rugby",
        "Handball",
        "Ultimate frisbee",
        "Cricket",
        "Boxing",
        "Kickboxing",
        "Martial arts",
        "Wrestling",
        "Skating",
        "Ice skating",
        "Cross-country skiing",
        "Skiing",
        "Snowboarding",
    ],
    "Aerobic exercise & outdoors": [
        "Jogging",
        "Trail running",
        "Treadmill",
        "Stationary cycling",
        "Spin class",
        "Mountain biking",
        "Rowing",
        "Rowing machine",
        "Elliptical",
        "Stair climber",
        "Jump rope",
        "Aerobics",
        "Dance",
        "Zumba",
        "HIIT",
        "Circuit training",
        "Step aerobics",
        "Aqua aerobics",
        "Water polo",
        "Brisk walking",
        "Hiking",
        "Kayaking",
        "Canoeing",
        "Paddleboarding",
        "Other cardio",
    ],
}
ACTIVITY_NAMES = {name.casefold(): name for group in ACTIVITIES.values() for name in group}
ACTIVITY_PATTERN = r"cardio|swam|swim|cycled|cycle|jog|aerobic|aerobics|run|ran|" + "|".join(
    re.escape(name) for name in sorted(ACTIVITY_NAMES, key=len, reverse=True)
)


def activity_name(value):
    if not isinstance(value, str) or value.strip().casefold() not in ACTIVITY_NAMES:
        raise ValueError("Choose a cardio activity from the list.")
    return ACTIVITY_NAMES[value.strip().casefold()]


def validate_cardio_goal(raw):
    if not isinstance(raw, dict) or set(raw) != {"moderate", "high"}:
        raise ValueError("Set weekly moderate and high-intensity cardio minutes.")
    result = {}
    for intensity in ("moderate", "high"):
        value = numeric(raw[intensity], intensity + " cardio minutes")
        if not 0 <= value <= 10080:
            raise ValueError("Weekly cardio minutes must be between 0 and 10080.")
        result[intensity] = value
    return result


def weekly_cardio(entries, goal, reference, today):
    from .goals import calendar_window

    start, end = calendar_window({"period": 1, "unit": "week"}, reference)
    totals = {"moderate": 0, "high": 0}
    for entry in entries:
        if (
            entry["kind"] == "cardio"
            and start.isoformat() <= entry["date"] <= min(end, today).isoformat()
        ):
            totals[entry["intensity"]] += entry["minutes"]
    value = totals["moderate"] + totals["high"] * HIGH_WEIGHT
    target = goal["moderate"] + goal["high"] * HIGH_WEIGHT
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        **totals,
        "minutes": sum(totals.values()),
        "value": value,
        "target": target,
        "percent": value / target * 100 if target else None,
    }
