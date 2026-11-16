"""User-entered sleep episodes, including an explicitly recorded night stretch."""


def sleep_days(entries):
    days = {}
    for entry in entries:
        if entry["kind"] != "sleep":
            continue
        day = days.setdefault(
            entry["date"],
            {
                "hours": 0,
                "night_hours": 0,
                "night_continuous": 0,
                "continuity_recorded": False,
                "entries": 0,
            },
        )
        day["hours"] += entry["hours"]
        day["entries"] += 1
        if entry["period"] == "night":
            day["night_hours"] += entry["hours"]
        if entry["period"] == "night" and entry.get("continuous_hours") is not None:
            day["continuity_recorded"] = True
            day["night_continuous"] = max(day["night_continuous"], entry["continuous_hours"])
    return days
