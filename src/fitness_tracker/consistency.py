"""A forgiving journal-adherence score, unrelated to health or exercise performance."""

from datetime import date, timedelta

from .goals import calendar_window
from .sleep import sleep_days
from .supplement_goals import daily_values, hydrate_supplement_goals


def gap_weight(days):
    if days <= 7:
        return 0.10
    if days <= 14:
        return 0.35
    if days <= 21:
        return 0.65
    return 1.0


def score_periods(periods):
    """Chronological (adherence, days, closed) buckets; rest days are inside gym targets."""
    credit = penalty = 0.0
    gap = 0
    for adherence, days, closed in periods:
        adherence = min(1, max(0, adherence))
        credit += adherence * days
        if adherence:
            gap = 0
            if closed:
                penalty += (1 - adherence) * days * 0.25
        elif closed:
            for _ in range(days):
                gap += 1
                penalty += gap_weight(gap)
    return round(100 * credit / (credit + penalty), 1) if credit + penalty else None


def period_window(goal, reference):
    start, end = calendar_window(goal, reference)
    return start, end, (end - start).days + 1


def metric_score(values, goal, today, since):
    start, end, width = period_window(goal, today)
    buckets = []
    while end >= since:
        clipped = max(start, since)
        days = (min(end, today) - clipped).days + 1
        value = sum(value for day, value in values.items() if clipped <= day <= min(end, today))
        ratio = min(1, value / goal["amount"])
        buckets.append((ratio, days, end < today))
        start, end, width = period_window(goal, start - timedelta(days=1))
    closed = [(ratio, days) for ratio, days, complete in buckets if complete]
    days = sum(days for _, days in closed)
    return {
        "score": score_periods(reversed(buckets)),
        "attainment": round(sum(ratio * count for ratio, count in closed) / days * 100, 1)
        if days
        else None,
        "met_periods": sum(ratio >= 1 for ratio, _ in closed),
        "completed_periods": len(closed),
    }


def consistency(entries, profile, today):
    earliest = today - timedelta(days=364)
    records = [e for e in entries if earliest.isoformat() <= e["date"] <= today.isoformat()]
    goals = profile["goals"]
    categories = {}
    for key, kind in (("exercise", "workout"), ("protein", "meal")):
        selected = [e for e in records if e["kind"] == kind]
        if not selected:
            categories[key] = {
                "score": None,
                "attainment": None,
                "met_periods": 0,
                "completed_periods": 0,
                "since": None,
                "logged_days": 0,
            }
            continue
        values = {}
        for entry in selected:
            day = date.fromisoformat(entry["date"])
            values[day] = 1 if key == "exercise" else values.get(day, 0) + entry["protein"]
        since = min(values)
        categories[key] = {
            **metric_score(values, goals["workout" if key == "exercise" else key], today, since),
            "since": since.isoformat(),
            "logged_days": len(values),
        }
    empty = {
        "score": None,
        "attainment": None,
        "met_periods": 0,
        "completed_periods": 0,
        "since": None,
        "logged_days": 0,
    }
    creatine = {**goals["creatine"], "measure": "g"}
    values = daily_values(records, "Creatine", creatine)
    if creatine["amount"] > 0 and values:
        parsed = {date.fromisoformat(day): value for day, value in values.items()}
        since = min(parsed)
        categories["creatine"] = {
            **metric_score(parsed, creatine, today, since),
            "since": since.isoformat(),
            "logged_days": len(parsed),
        }
    else:
        categories["creatine"] = dict(empty)
    supplement_goals = hydrate_supplement_goals(profile)
    components = []
    logged_dates = set()
    for name in profile["consistency_supplements"]:
        if name == "Creatine":
            continue
        goal = supplement_goals[name]
        values = daily_values(records, name, goal)
        if values:
            parsed = {date.fromisoformat(day): value for day, value in values.items()}
            since = min(parsed)
            item = {
                **metric_score(parsed, goal, today, since),
                "since": since.isoformat(),
                "logged_days": len(parsed),
            }
            logged_dates.update(values)
        else:
            item = dict(empty)
        components.append({"name": name, "goal": goal, **item})
    scores = [item["score"] for item in components if item["score"] is not None]
    attained = [item["attainment"] for item in components if item["attainment"] is not None]
    categories["supplements"] = {
        "score": round(sum(scores) / len(scores), 1) if scores else None,
        "attainment": round(sum(attained) / len(attained), 1) if attained else None,
        "met_periods": sum(item["met_periods"] for item in components),
        "completed_periods": sum(item["completed_periods"] for item in components),
        "since": min(logged_dates) if logged_dates else None,
        "logged_days": len(logged_dates),
        "items": components,
    }
    sleep = sleep_days(records)
    if sleep:
        values = {
            date.fromisoformat(day): min(
                info["hours"] / profile.get("sleep_goal", 7),
                info["night_hours"] / profile.get("night_hours_goal", 6),
                1,
            )
            for day, info in sleep.items()
        }
        since = min(values)
        categories["sleep"] = {
            **metric_score(values, {"amount": 1, "period": 1, "unit": "day"}, today, since),
            "since": since.isoformat(),
            "logged_days": len(values),
        }
    else:
        categories["sleep"] = dict(empty)
    available = [item["score"] for item in categories.values() if item["score"] is not None]
    exact = [item["attainment"] for item in categories.values() if item["attainment"] is not None]
    return {
        "attainment": round(sum(exact) / len(exact), 1) if exact else None,
        "attainment_categories": len(exact),
        "overall": round(sum(available) / len(available), 1) if available else None,
        "categories": categories,
        "scored_categories": len(available),
        "history_days": 365,
        "method": "forgiving-v1",
    }


def consistency_trend(entries, profile, today):
    """Recalculate historical snapshots with current goals, without future records."""
    dates = [
        date.fromisoformat(e["date"])
        for e in entries
        if e["kind"] in ("workout", "meal", "creatine", "supplement", "sleep")
        and e["date"] <= today.isoformat()
    ]
    if not dates:
        return []
    start = max(min(dates), today - timedelta(days=83))
    step = 1 if (today - start).days <= 28 else 7
    points = []
    day = start
    while day < today:
        points.append(day)
        day += timedelta(days=step)
    points.append(today)
    return [
        {"date": day.isoformat(), "overall": consistency(entries, profile, day)["overall"]}
        for day in points
    ]
