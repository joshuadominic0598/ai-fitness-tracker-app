"""Application-owned conversation state, source corrections and bounded log parsing."""

import re
from copy import deepcopy


def is_departure(message):
    return bool(
        re.search(
            r"^\s*(?:cancel|never mind|nevermind|forget (?:it|that)|stop)\b|"
            r"\b(?:help me learn|help me with|help me log supplements|help me log or plan|teach me|how (?:do|to)|what is|explain|instead tell me)\b|"
            r"^\s*(?:what|why|how|tell me|assess|estimate|help me estimate)\b",
            message,
            re.I,
        )
    )


def correct_workout_source(source, message, choices=()):
    """Patch named source movements; untouched lines and duplicate sets stay intact."""
    from .workout_notes import combine_source, inventory, movement_name

    lines = source.splitlines()
    changed = False
    from .exercise_matching import normalize
    from .store import EXERCISES

    if choices:
        selected = []
        option = re.fullmatch(r"\s*(?:option\s*)?([123])[.! ]*", message, re.I)
        if len(choices) == 1 and option and int(option[1]) <= len(choices[0]["candidates"]):
            selected.append((choices[0], choices[0]["candidates"][int(option[1]) - 1]))
        for choice in choices:
            for eid in choice["candidates"]:
                if normalize(EXERCISES[eid]["name"]) in normalize(message):
                    selected.append((choice, eid))
        for choice, eid in selected:
            for i, line in enumerate(lines):
                if normalize(choice["label"]) in normalize(line):
                    quantity = re.search(
                        r"\d+(?:\.\d+)?\s*(?:kg|reps?|seconds?|secs?|min|s)\b", line, re.I
                    )
                    if quantity:
                        lines[i] = EXERCISES[eid]["name"] + " " + line[quantity.start() :]
                        changed = True
    source = "\n".join(lines)
    if re.search(r"\bstanding biceps? curl\b", source, re.I):
        equipment = next(
            (
                word
                for word in ("dumbbell", "barbell", "cable")
                if re.search(r"\b" + word + r"s?\b", message, re.I)
            ),
            None,
        )
        option = re.fullmatch(r"\s*(?:option\s*)?([123])[.! ]*", message, re.I)
        if option:
            equipment = {"1": "dumbbell", "2": "barbell", "3": "cable"}[option[1]]
        if equipment:
            replacement = {
                "dumbbell": "Dumbbell bicep curl",
                "barbell": "Barbell curl",
                "cable": "Standing biceps cable curl",
            }[equipment]
            source = re.sub(r"standing biceps? curl", replacement, source, flags=re.I)
            lines = source.splitlines()
            changed = True
    set_edit = re.search(
        r"\b(?:change|update|correct)\s+(?:the\s+)?(first|second|third|\d+)(?:st|nd|rd|th)?\s+(.+?)\s+set\s+to\s+(\d+)\s*reps?",
        message,
        re.I,
    )
    if set_edit:
        index = {"first": 1, "second": 2, "third": 3}.get(
            set_edit[1].lower(), int(set_edit[1]) if set_edit[1].isdigit() else 1
        ) - 1
        wanted = set(normalize(set_edit[2]).split())
        groups = inventory(source)["groups"]
        targets = [
            g
            for g in groups
            if wanted <= set(normalize(g["label"]).split())
            or any(
                wanted <= set(normalize(EXERCISES[eid]["name"]).split()) for eid in g["candidates"]
            )
        ]
        if len(targets) == 1 and index < len(targets[0]["sets"]):
            group = targets[0]
            sets = deepcopy(group["sets"])
            sets[index]["reps"] = int(set_edit[3])
            source_lines = {s["source"] for s in group["sets"]}
            replacement = (
                EXERCISES[group["candidates"][0]]["name"]
                + " "
                + ", ".join(f"{s['weight']:g}kg {s['reps']} reps" for s in sets)
            )
            result = []
            inserted = False
            for line in lines:
                stripped = re.sub(r"^\s*\d+[.)]\s*", "", line).strip()
                if stripped in source_lines:
                    if not inserted:
                        result.append(replacement)
                        inserted = True
                else:
                    result.append(line)
            if inserted:
                return "\n".join(result)
    for correction in message.splitlines():
        correction = correction.strip()
        if not correction or re.search(r"^suggest changes|^change:\s*$", correction, re.I):
            continue
        hanging = re.search(r"\bhanging leg raises?\b", correction, re.I)
        if hanging:
            for i, line in enumerate(lines):
                if re.search(r"\bstanding leg raises?\b", line, re.I):
                    lines[i] = re.sub(
                        r"standing leg raises?", "Hanging leg raise", line, flags=re.I
                    )
                    lines[i] = re.split(r",?\s*not\b", lines[i], flags=re.I)[0]
                    changed = True
        parsed = inventory(correction)
        if not any(g["sets"] for g in parsed["groups"]):
            continue
        name = movement_name(correction)
        for i, line in enumerate(lines):
            old = movement_name(line)
            old_words = set(old.split()) - {
                "exercise",
                "excercise",
                "is",
                "its",
                "time",
                "each",
                "set",
            }
            new_words = set(name.split())
            if old_words and old_words <= new_words and re.search(r"\d", line):
                lines[i] = correction
                changed = True
                break
    return "\n".join(lines) if changed else combine_source(source, message)


def merge_revision(original, kind, proposal, message):
    """A partial model reply is a patch, never permission to erase untouched items."""
    if not isinstance(proposal, dict):
        return proposal
    old = deepcopy(original["data"])
    if original["kind"] in ("workout", "home_workout", "plan") and kind == original["kind"]:
        changed = {ex["exercise_id"]: ex for ex in proposal.get("exercises", [])}
        # Deletions require an explicit instruction and a named existing exercise.
        from .store import EXERCISES

        remove = re.search(r"\b(remove|delete|drop)\b", message, re.I)
        result = []
        for ex in old["exercises"]:
            name = EXERCISES[ex["exercise_id"]]["name"].lower()
            if remove and name in message.lower():
                continue
            result.append(changed.pop(ex["exercise_id"], ex))
        return {**old, **proposal, "exercises": result + list(changed.values())}
    if original["kind"] == "meal" and kind == "meal" and old.get("items") and proposal.get("items"):
        changed = {item["name"].strip().casefold(): item for item in proposal["items"]}
        items = [changed.pop(item["name"].strip().casefold(), item) for item in old["items"]]
        items.extend(changed.values())
        result = {
            **old,
            **proposal,
            "items": items,
            "protein": round(sum(float(item["protein"]) for item in items), 2),
        }
        if all(item.get("calories") is not None for item in items):
            result["calories"] = round(sum(float(item["calories"]) for item in items), 2)
        if (
            not float(result.get("low", result["protein"]))
            <= result["protein"]
            <= float(result.get("high", result["protein"]))
        ):
            result.pop("low", None)
            result.pop("high", None)
        return result
    if original["kind"] == "batch":
        updates = (
            proposal.get("entries", []) if kind == "batch" else [{"kind": kind, "data": proposal}]
        )

        def identity(entry):
            from .supplement_goals import is_creatine

            kind = (
                "creatine"
                if is_creatine({"kind": entry["kind"], **entry["data"]})
                else entry["kind"]
            )
            return kind, (
                ""
                if kind == "creatine"
                else entry["data"].get(
                    "activity", entry["data"].get("name", entry["data"].get("period", ""))
                )
            )

        changed = {identity(entry): entry for entry in updates}
        entries = []
        for entry in old["entries"]:
            update = changed.pop(identity(entry), None)
            if update is None:
                same_kind = [key for key in changed if key[0] == entry["kind"]]
                count_old = sum(old_entry["kind"] == entry["kind"] for old_entry in old["entries"])
                if count_old == 1 and len(same_kind) == 1:
                    update = changed.pop(same_kind[0])
            if update and entry["kind"] in ("workout", "home_workout", "plan"):
                update["data"] = merge_revision(entry, update["kind"], update["data"], message)
            chosen = update or entry
            if chosen["kind"] == "meal" and not chosen.get("calculation"):
                chosen["calculation"] = "+".join(
                    str(food["protein"]) for food in chosen["data"].get("items", [])
                ) or str(chosen["data"]["protein"])
            entries.append(chosen)
        return {"entries": entries + list(changed.values())}
    return proposal


def simple_intake(message, day, profile):
    """Resolve explicit sleep and configured pill units without asking a model to guess."""
    from .store import supplement_name

    entries, questions = [], []
    sleep = re.search(
        r"\b(nap|night|slept|sleep)\s*(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b", message, re.I
    )
    if sleep and len(list(re.finditer(r"\b(?:nap|night|slept|sleep)\s*\d", message, re.I))) > 1:
        return None  # Let the model preserve and separate multiple sleep periods.
    if re.search(r"\b(?:ate|meal|food|protein)\b", message, re.I):
        return None  # Mixed meal requests require the complete structured batch path.
    if sleep:
        continuous = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:h(?:rs?|ours?)?\s*)?un(?:inter\w*|iter\w*)", message, re.I
        )
        data = {
            "date": day,
            "hours": float(sleep[2]),
            "period": "other" if sleep[1].lower() == "nap" else "night",
        }
        if continuous:
            data["continuous_hours"] = float(continuous[1])
        entries.append({"kind": "sleep", "data": data})
    taken = bool(re.search(r"\b(?:took|taken|had|log|record)\b", message, re.I))
    if taken:
        for name in profile.get("supplements", []):
            aliases = [name.lower()]
            if name.lower().startswith("vitamin "):
                suffix = name.split()[-1]
                aliases += [
                    "vit " + suffix,
                    "vit" + suffix,
                    suffix,
                ]
            found = any(
                alias and re.search(r"\b" + re.escape(alias) + r"\b", message, re.I)
                for alias in aliases
            )
            if not found:
                continue
            goal = profile.get("supplement_goals", {}).get(name, {})
            measure = goal.get("measure")
            if measure in ("tablet", "capsule", "softgel"):
                found_alias = next(
                    re.finditer(
                        r"\b(?:"
                        + "|".join(re.escape(alias) for alias in aliases if alias)
                        + r")\b",
                        message,
                        re.I,
                    )
                )
                tail = re.split(
                    r",|\band\b|\bvit(?:amin)?\b",
                    message[found_alias.end() :],
                    maxsplit=1,
                    flags=re.I,
                )[0]
                explicit = re.search(
                    r"(\d+(?:\.\d+)?)\s*(?:tablets?|capsules?|softgels?)\b", tail, re.I
                )
                before = re.search(
                    r"(\d+(?:\.\d+)?)\s*(?:tablets?|capsules?|softgels?)\s*(?:of\s+)?$",
                    message[: found_alias.start()],
                    re.I,
                )
                explicit = explicit or before
                # One tablet for an unquantified singular intake; show the assumption.
                amount = float(explicit[1]) if explicit else 1
                entries.append(
                    {
                        "kind": "supplement",
                        "data": {
                            "date": day,
                            "name": supplement_name(name),
                            "amount": amount,
                            "unit": measure,
                            "notes": "Assumed one " + measure + "; confirm or correct."
                            if not explicit
                            else "",
                        },
                    }
                )
            else:
                questions.append(f"How much {name} did you take, and in which unit?")
    creatine = re.search(
        r"\bcreatine\s*(\d+(?:\.\d+)?)\s*g\b|\b(\d+(?:\.\d+)?)\s*g\s*(?:of\s+)?creatine\b",
        message,
        re.I,
    )
    if taken and re.search(r"\bcreatine\b", message, re.I) and not creatine:
        return None
    if creatine and taken:
        entries.append(
            {
                "kind": "creatine",
                "data": {"date": day, "amount": float(creatine[1] or creatine[2]), "unit": "g"},
            }
        )
    if questions:
        return (
            {
                "action": "clarify",
                "message": "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1)),
                "proposal": None,
            }
            if not entries
            else None
        )
    if not entries:
        return None
    return {
        "action": entries[0]["kind"] if len(entries) == 1 else "batch",
        "message": "Review your intake.",
        "proposal": entries[0]["data"] if len(entries) == 1 else {"entries": entries},
    }


def scope_statistics(entries):
    """Exact scoped aggregates, independent of the size of a retrieval sample."""
    from collections import defaultdict

    protein, sleep, supplements = defaultdict(float), defaultdict(float), defaultdict(float)
    workouts, sets, creatine = set(), 0, 0
    home_days, gym_days = set(), set()
    calories, missing_calories, cardio_moderate, cardio_high = 0, 0, 0, 0
    performance = defaultdict(list)
    for entry in entries:
        kind = entry["kind"]
        if kind in ("workout", "home_workout"):
            workouts.add(entry["date"])
            (home_days if kind == "home_workout" else gym_days).add(entry["date"])
            sets += sum(len(ex["sets"]) for ex in entry["exercises"])
            for exercise in entry["exercises"]:
                best = max(
                    exercise["sets"],
                    key=lambda s: (s.get("weight", 0), s.get("reps", 0), s.get("seconds", 0)),
                )
                performance[exercise["exercise_id"]].append({"date": entry["date"], **best})
        elif kind == "meal":
            protein[entry["date"]] += entry["protein"]
            calories += entry.get("calories") or 0
            missing_calories += entry.get("calories") is None
        elif kind == "cardio":
            if entry["intensity"] == "moderate":
                cardio_moderate += entry["minutes"]
            else:
                cardio_high += entry["minutes"]
        elif kind == "sleep":
            sleep[entry["date"]] += entry["hours"]
        elif kind == "creatine":
            creatine += entry["amount"]
        elif kind == "supplement":
            supplements[entry["name"] + " (" + entry["unit"] + ")"] += entry["amount"]
    return {
        "exercise_comparisons": [
            {
                "exercise_id": eid,
                "first": sorted(rows, key=lambda r: r["date"])[0],
                "latest": sorted(rows, key=lambda r: r["date"])[-1],
            }
            for eid, rows in performance.items()
            if len({row["date"] for row in rows}) >= 2
        ],
        "matched_records": len(entries),
        "workout_days": len(workouts),
        "gym_days": len(gym_days),
        "home_workout_days": len(home_days),
        "workout_sets": sets,
        "protein_g": round(sum(protein.values()), 2),
        "calories_kcal": round(calories, 2),
        "meals_missing_calories": missing_calories,
        "cardio_moderate_minutes": cardio_moderate,
        "cardio_high_minutes": cardio_high,
        "cardio_equivalent_minutes": cardio_moderate + 2 * cardio_high,
        "protein_logged_days": len(protein),
        "protein_g_per_logged_day": round(sum(protein.values()) / len(protein), 2)
        if protein
        else None,
        "creatine_g": round(creatine, 2),
        "supplement_totals_by_unit": dict(supplements),
        "sleep_logged_days": len(sleep),
        "sleep_hours": round(sum(sleep.values()), 2),
        "sleep_hours_per_logged_day": round(sum(sleep.values()) / len(sleep), 2) if sleep else None,
        "limitation": "Averages cover logged days only; missing records do not establish zero intake or sleep.",
    }


def format_assessment(context, next_steps):
    """Print computed observations; model suggestions cannot claim goal attainment."""
    stats = context["scope_totals"]
    kinds = context.get("evidence_scope", {}).get("kinds", [])

    def selected(kind):
        return not kinds or kind in kinds

    defaults = {
        "workouts": "Compare the same exercise, load and technique across sessions before judging strength changes.",
        "protein": "Include portions and product labels to make food estimates easier to compare.",
        "creatine": "Keep intake records separate from food protein and use your existing tracking goal.",
        "supplements": "Use your configured units and product labels; review any uncertain quantity before logging.",
        "sleep": "Log night sleep and naps separately, adding uninterrupted hours when useful.",
    }

    def suggestion(key):
        values = next_steps.get(key, []) if isinstance(next_steps, dict) else []
        value = (
            values[0] if isinstance(values, list) and values and isinstance(values[0], str) else ""
        )
        if not value or re.search(
            r"\d|\b(?:met|meeting|achieved|completed|logged|recorded|increase.*supplement|add.*supplement)\b",
            value,
            re.I,
        ):
            value = defaults[key]
        if key == "supplements" and re.search(
            r"\b(?:add|increase|start|targeted support)\b", value, re.I
        ):
            return defaults[key]
        if key == "protein":
            goal = context.get("profile", {}).get("goals", {}).get("protein", {})
            average = stats.get("protein_g_per_logged_day")
            if (
                average is not None
                and goal.get("unit") == "day"
                and goal.get("period") == 1
                and average < goal.get("amount", 0)
            ):
                return f"Your configured goal is {goal['amount']:g} g per day. Check portions and complete missing meal logs before judging intake."
        return value

    def counted(amount, singular):
        return f"{amount} {singular}" + ("" if amount == 1 else "s")

    scope = context.get("evidence_scope", {})
    dates = scope.get("start", "All recorded dates")
    if scope.get("end") and scope["end"] != scope.get("start"):
        dates += " to " + scope["end"]
    sections = ["**Progress assessment · " + dates + "**"]
    if selected("workout") or selected("home_workout"):
        sections.append(
            f"**Workouts**\n1. **Training:** {counted(stats['workout_days'], 'logged workout day')}, {counted(stats['workout_sets'], 'set')}. Gym: {stats.get('gym_days', stats['workout_days'])} day(s); home: {stats.get('home_workout_days', 0)} day(s). {suggestion('workouts')}"
        )
    intake = []
    if selected("meal"):
        fact = f"{stats['protein_g']:g} g across {counted(stats['protein_logged_days'], 'logged day')}."
        if stats["protein_g_per_logged_day"] is not None:
            fact += f" Average: {stats['protein_g_per_logged_day']:g} g per logged day."
        intake.append("**Protein:** " + fact + " " + suggestion("protein"))
    if selected("creatine"):
        intake.append(
            f"**Creatine:** {stats['creatine_g']:g} g in the selected records. "
            + suggestion("creatine")
        )
    if selected("supplement"):
        values = (
            "; ".join(
                f"{name}: {amount:g}" for name, amount in stats["supplement_totals_by_unit"].items()
            )
            or "No supplement records in this scope"
        )
        intake.append("**Supplements:** " + values + ". " + suggestion("supplements"))
    if selected("sleep"):
        fact = f"{stats['sleep_hours']:g} h across {counted(stats['sleep_logged_days'], 'logged day')}."
        if stats["sleep_hours_per_logged_day"] is not None:
            fact += f" Average: {stats['sleep_hours_per_logged_day']:g} h per logged day."
        intake.append("**Sleep:** " + fact + " " + suggestion("sleep"))
    if selected("workout") or selected("home_workout"):
        from .store import EXERCISES

        comparisons = stats.get("exercise_comparisons", [])
        if comparisons:
            details = []
            for comparison in comparisons[:4]:

                def values(row):
                    return (
                        f"{row.get('seconds', 0):g} sec"
                        if row.get("seconds")
                        else f"{row.get('weight', 0):g} kg × {row.get('reps', 0)} reps"
                    )

                first, latest = comparison["first"], comparison["latest"]
                details.append(
                    EXERCISES[comparison["exercise_id"]]["name"]
                    + f": best logged set {values(first)} ({first['date']}) → {values(latest)} ({latest['date']})."
                )
            sections.append(
                "**Recorded exercise comparisons**\n"
                + "\n".join(f"{i}. {value}" for i, value in enumerate(details, 1))
            )
        else:
            sections.append(
                "**Strength trends:** This scope does not contain repeated sessions for the same exercise. A strength trend needs comparable sessions."
            )
    if kinds == ["meal"]:
        meals = [entry for entry in context.get("recent_entries", []) if entry["kind"] == "meal"][
            :3
        ]
        if meals:
            sections.append(
                "**Logged meals**\n"
                + "\n".join(
                    f"{i}. {entry['date']}: {entry['description']} — {entry['protein']:g} g protein."
                    for i, entry in enumerate(meals, 1)
                )
            )
    if intake:
        sections.append(
            "**Intake and recovery**\n"
            + "\n".join(f"{i}. {value}" for i, value in enumerate(intake, 1))
        )
    sections.append(
        "Missing logs do not establish zero intake or sleep. Logging frequency alone does not measure strength or health."
    )
    return "\n\n".join(sections)


def stated_day(message, reference_day):
    """Resolve explicit ISO or day-month dates; never guess a different journal year."""
    from datetime import date

    iso = re.search(r"\b\d{4}-\d{2}-\d{2}\b", message)
    if iso:
        return date.fromisoformat(iso[0]).isoformat()
    match = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b(?:[, ]+(\d{4}))?",
        message,
        re.I,
    )
    if not match:
        return None
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    return date(
        int(match[3] or reference_day[:4]), months.index(match[2][:3].lower()) + 1, int(match[1])
    ).isoformat()
