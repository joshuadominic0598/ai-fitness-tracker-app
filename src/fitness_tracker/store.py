"""SQLite persistence and validated domain operations. No provider code writes logs."""

import hashlib
import json
import math
import sqlite3
import uuid
from contextlib import closing, contextmanager, nullcontext
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .anatomy import classify, training_areas
from .cardio import activity_name, validate_cardio_goal, weekly_cardio
from .consistency import consistency, consistency_trend
from .goals import with_goals
from .sleep import sleep_days
from .supplement_goals import hydrate_supplement_goals, is_creatine, validate_supplement_goals

CATALOG = json.loads((Path(__file__).parent / "exercises.json").read_text())
CATALOG += json.loads((Path(__file__).parent / "custom_exercises.json").read_text())
CATALOG = [classify(e) for e in CATALOG]
EXERCISES = {e["id"]: e for e in CATALOG}
SUPPLEMENT_OPTIONS = ["Vitamin D", "Vitamin C", "Vitamin B12", "Fish Oil", "Collagen"]


DEFAULT_PROFILE = {
    "name": "",
    "weekly_goal": 3,
    "protein_goal": 120,
    "creatine_goal": 5,
    "cardio_goal": {"moderate": 0, "high": 0},
    "sleep_goal": 7,
    "night_hours_goal": 6,
    "night_sleep_goal": 6,
    "focus": "",
    "weight_kg": None,
    "experience": "beginner",
    "constraints": "",
    "supplements": SUPPLEMENT_OPTIONS,
    "consistency_supplements": [],
}


def number(value, name, low=0, high=100000):
    if isinstance(value, bool):
        raise ValueError(name + " must be a number.")
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(name + " must be a number.") from None
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{name} must be between {low} and {high}.")
    return result


def text(value, name, limit=4000, required=True):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f"Enter a valid {name} (up to {limit} characters).")
    return value.strip()


def supplement_name(value):
    name = text(value, "supplement name", 100)
    aliases = {
        "creatine": "Creatine",
        "vit d": "Vitamin D",
        "vitamin d": "Vitamin D",
        "vit c": "Vitamin C",
        "vitamin c": "Vitamin C",
        "vit b12": "Vitamin B12",
        "vitamin b12": "Vitamin B12",
        "b12": "Vitamin B12",
        "fish oil": "Fish Oil",
        "collagen": "Collagen",
    }
    return aliases.get(" ".join(name.casefold().split()), name)


def supplement_options(values):
    if not isinstance(values, list):
        raise ValueError("Supplement options must be a list.")
    result, seen = [], set()
    for value in SUPPLEMENT_OPTIONS + values:
        name = supplement_name(value)
        if name.casefold() != "creatine" and name.casefold() not in seen:
            result.append(name)
            seen.add(name.casefold())
    if len(result) > 100:
        raise ValueError("Use up to 100 supplement options.")
    return result


def valid_date(value):
    try:
        result = date.fromisoformat(value)
        if not 1900 <= result.year <= 2050:
            raise ValueError()
        return result.isoformat()
    except (ValueError, TypeError):
        raise ValueError("Choose a valid date.") from None


def session_title(value):
    day = date.fromisoformat(value)
    suffix = (
        "th" if 11 <= day.day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day.day % 10, "th")
    )
    month = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")[
        day.month - 1
    ]
    return f"{month} {day.day}{suffix} {day.year % 100:02d}'"


def validate(kind, raw):
    if not isinstance(raw, dict):
        raise ValueError("Entry must be an object.")
    d = {
        "date": valid_date(raw.get("date")),
        "notes": text(
            raw.get("notes", ""),
            "notes",
            20000 if kind in ("workout", "home_workout") else 4000,
            required=False,
        ),
    }
    if kind == "plan":
        exercises = raw.get("exercises")
        if not isinstance(exercises, list) or not 1 <= len(exercises) <= 50:
            raise ValueError("Choose 1–50 exercises for the session plan.")
        ids = [ex.get("exercise_id") if isinstance(ex, dict) else None for ex in exercises]
        if any(eid not in EXERCISES for eid in ids):
            raise ValueError("Choose exercises from the library.")
        return {
            "date": d["date"],
            "name": session_title(d["date"]),
            "exercises": [{"exercise_id": eid} for eid in dict.fromkeys(ids)],
        }
    if kind in ("workout", "home_workout", "plan"):
        d["name"] = session_title(d["date"])
        d["duration"] = number(raw.get("duration", 0), "Duration", 0, 1440)
        if not isinstance(raw.get("exercises"), list) or not 1 <= len(raw["exercises"]) <= 50:
            raise ValueError("Add between 1 and 50 exercises.")
        d["exercises"] = []
        for ex in raw["exercises"]:
            if not isinstance(ex, dict) or ex.get("exercise_id") not in EXERCISES:
                raise ValueError("Select an exercise from the library.")
            if kind == "home_workout" and EXERCISES[ex["exercise_id"]].get("category") == "cardio":
                raise ValueError("Log aerobic activity separately in Cardio, not Home workouts.")
            sets = ex.get("sets")
            if not isinstance(sets, list) or not 1 <= len(sets) <= 30:
                raise ValueError("Each exercise needs 1–30 sets.")
            tracking = ex.get("tracking")
            if ex["exercise_id"] == "Plank":
                if tracking not in (None, "time"):
                    raise ValueError("Planks are tracked by time, not reps.")
                tracking = "time"
            elif tracking is None:
                tracking = (
                    "time"
                    if all(
                        isinstance(s, dict) and not s.get("reps") and s.get("seconds") for s in sets
                    )
                    else "reps"
                )
            if tracking not in ("time", "reps"):
                raise ValueError("Choose reps or time for this exercise.")
            load_mode = ex.get("load_mode")
            if load_mode not in (None, "bodyweight", "weighted"):
                raise ValueError("Choose Bodyweight or Added weight for this exercise.")
            clean = []
            for s in sets:
                if not isinstance(s, dict):
                    raise ValueError("Invalid set.")
                weight = number(s.get("weight", 0), "Weight (kg)", 0, 1000)
                if load_mode == "bodyweight" and weight != 0:
                    raise ValueError(
                        "Bodyweight sets cannot include added kg. Select Added weight to enter a load."
                    )
                reps = number(s.get("reps", 0), "Reps", 0, 1000)
                seconds = number(s.get("seconds", 0), "Seconds", 0, 86400)
                if reps != int(reps):
                    raise ValueError("Reps must be a whole number.")
                if tracking == "time" and (seconds <= 0 or reps != 0):
                    raise ValueError("Timed exercises need a duration in seconds and no reps.")
                if tracking == "reps" and (reps <= 0 or seconds != 0):
                    raise ValueError(
                        "Rep-based exercises need reps and no duration. Choose time for holds."
                    )
                clean.append({"weight": weight, "reps": int(reps), "seconds": seconds})
            d["exercises"].append(
                {
                    "exercise_id": ex["exercise_id"],
                    "tracking": tracking,
                    "load_mode": load_mode
                    or ("weighted" if any(s["weight"] > 0 for s in clean) else "bodyweight"),
                    "sets": clean,
                }
            )
        grouped = {}
        for exercise in d["exercises"]:
            eid = exercise["exercise_id"]
            if eid not in grouped:
                grouped[eid] = exercise
            else:
                previous = grouped[eid]
                if previous["tracking"] != exercise["tracking"]:
                    raise ValueError(
                        "Use the same reps/time tracking for repeated entries of one exercise."
                    )
                previous["sets"].extend(exercise["sets"])
                if exercise["load_mode"] == "weighted":
                    previous["load_mode"] = "weighted"
                if len(previous["sets"]) > 30:
                    raise ValueError("Each exercise can contain up to 30 sets.")
        d["exercises"] = list(grouped.values())
    elif kind == "cardio":
        if raw.get("intensity") not in ("moderate", "high"):
            raise ValueError("Choose moderate or high cardio intensity.")
        d.update(
            activity=activity_name(raw.get("activity")),
            minutes=number(raw.get("minutes"), "Cardio minutes", 0.1, 1440),
            intensity=raw["intensity"],
        )
    elif kind == "meal":
        d.update(
            description=text(raw.get("description"), "food description", 2000),
            protein=number(raw.get("protein"), "Protein (g)", 0, 500),
            source=raw.get("source", "manual")
            if raw.get("source") in ("manual", "ai")
            else "manual",
        )
        if raw.get("calories") not in (None, ""):
            d["calories"] = number(raw["calories"], "Calories (kcal)", 0, 10000)
        if raw.get("items") is not None:
            items = raw["items"]
            if not isinstance(items, list) or not 1 <= len(items) <= 50:
                raise ValueError("A meal breakdown needs 1–50 food items.")
            d["items"] = []
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("Each meal item needs a food, portion and protein estimate.")
                d["items"].append(
                    {
                        "name": text(item.get("name"), "food name", 200),
                        "portion": text(item.get("portion"), "food portion", 200),
                        "protein": number(item.get("protein"), "Item protein (g)", 0, 500),
                        "notes": text(
                            item.get("notes", ""), "food assumption", 500, required=False
                        ),
                    }
                )
                if item.get("calories") not in (None, ""):
                    d["items"][-1]["calories"] = number(
                        item["calories"], "Item calories (kcal)", 0, 10000
                    )
            total = sum(item["protein"] for item in d["items"])
            precision = max(0, -Decimal(str(d["protein"])).normalize().as_tuple().exponent)
            if abs(total - d["protein"]) > 0.05 and round(total, precision) != d["protein"]:
                raise ValueError("Meal item protein estimates do not add up to the total.")
            if "calories" in d and all("calories" in item for item in d["items"]):
                total_calories = sum(item["calories"] for item in d["items"])
                if abs(total_calories - d["calories"]) > 1:
                    raise ValueError("Meal item calorie estimates do not add up to the total.")
        for key in ("low", "high"):
            if raw.get(key) is not None:
                d[key] = number(raw[key], key + " protein estimate", 0, 500)
        if "low" in d and "high" in d and not d["low"] <= d["protein"] <= d["high"]:
            raise ValueError("Protein estimate must be inside the stated range.")
    elif kind in ("supplement", "creatine"):
        d.update(
            name="Creatine" if kind == "creatine" else supplement_name(raw.get("name")),
            amount=number(raw.get("amount"), "Amount", 0.001, 100000),
            unit=text(raw.get("unit", "g" if kind == "creatine" else None), "unit", 20),
        )
        if d["name"].lower() == "creatine" and d["unit"] != "g":
            raise ValueError("Log creatine in grams so adherence can be calculated.")
    elif kind == "sleep":
        hours = number(raw.get("hours"), "Sleep hours", 0.1, 24)
        period = raw.get("period")
        if period not in ("night", "afternoon", "other"):
            raise ValueError("Choose night sleep, afternoon nap or another nap.")
        continuous = raw.get("continuous_hours")
        if continuous in (None, ""):
            continuous = None
        else:
            continuous = number(continuous, "Continuous night hours", 0, hours)
            if period != "night":
                raise ValueError("A continuous night stretch must belong to night sleep.")
        d.update(hours=hours, period=period, continuous_hours=continuous)
    elif kind == "body":
        d.update(weight_kg=number(raw.get("weight_kg"), "Body weight (kg)", 20, 500))
    else:
        raise ValueError("Unknown entry type.")
    return d


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        self.path = self.directory / "fitness.sqlite3"
        with self.connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS entries
                (id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workout_revisions
                (revision_id TEXT PRIMARY KEY, entry_id TEXT NOT NULL, data TEXT NOT NULL,
                 archived_at TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS messages
                (id INTEGER PRIMARY KEY, role TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS completed_chat_requests
                (request_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, response_id INTEGER NOT NULL,
                 user_data TEXT NOT NULL, response_data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS drafts
                (id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL, status TEXT DEFAULT 'pending');
            """)
        self.path.chmod(0o600)
        with self.connect() as con:
            for (message_id,) in con.execute(
                "SELECT id FROM messages WHERE role='user'"
            ).fetchall():
                self._cache_chat_exchange(con, message_id)
            if "baseline" not in {row[1] for row in con.execute("PRAGMA table_info(drafts)")}:
                con.execute("ALTER TABLE drafts ADD COLUMN baseline TEXT DEFAULT '{}'")
        from .semantic_index import initialize, journal_chunk, upsert

        with self.connect() as con:
            initialize(con)
            for exercise in CATALOG:
                content = " ".join(
                    [
                        exercise["name"],
                        *exercise.get("aliases", []),
                        exercise.get("equipment") or "",
                        *exercise["primaryMuscles"],
                        *exercise.get("instructions", []),
                    ]
                )
                upsert(con, "exercise:" + exercise["id"], "exercise", "", content)
            for identifier, kind, raw in con.execute("SELECT id,kind,data FROM entries").fetchall():
                journal_chunk(con, identifier, kind, json.loads(raw))
            row = con.execute("SELECT data FROM settings WHERE key='chat_start_id'").fetchone()
            boundary = int(json.loads(row[0])) if row else 0
            for identifier, raw in con.execute(
                "SELECT id,data FROM messages WHERE role='user' AND id>?", (boundary,)
            ).fetchall():
                message = json.loads(raw)
                chunk_id = "conversation:" + str(identifier)
                if (
                    message.get("status") not in ("pending", "failed")
                    and not con.execute(
                        "SELECT 1 FROM coach_chunks WHERE id=?", (chunk_id,)
                    ).fetchone()
                ):
                    upsert(
                        con,
                        chunk_id,
                        "conversation",
                        message.get("context_date", date.today().isoformat()),
                        "User said (unverified conversation): " + message.get("text", ""),
                    )
        self._consolidate_workout_days()
        with self.connect() as con:
            self._supersede_workout_previews(con)

    def _archive_workout(self, con, entry_id, data):
        con.execute(
            "INSERT INTO workout_revisions(revision_id,entry_id,data) VALUES (?,?,?)",
            (uuid.uuid4().hex, entry_id, data),
        )

    def _consolidate_workout_days(self):
        with self.connect() as con:
            rows = con.execute(
                "SELECT id,data FROM entries WHERE kind='workout' ORDER BY rowid DESC"
            ).fetchall()
        days = [json.loads(data)["date"] for _, data in rows]
        if len(set(days)) == len(days):
            return
        backups = self.directory / "backups"
        backups.mkdir(mode=0o700, exist_ok=True)
        backup = backups / ("before-daily-workouts-" + uuid.uuid4().hex[:12] + ".sqlite3")
        backup.touch(mode=0o600)
        with self.connect() as source, closing(sqlite3.connect(str(backup))) as target:
            source.backup(target)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            seen = set()
            for entry_id, data in con.execute(
                "SELECT id,data FROM entries WHERE kind='workout' ORDER BY rowid DESC"
            ).fetchall():
                day = json.loads(data)["date"]
                if day in seen:
                    self._archive_workout(con, entry_id, data)
                    con.execute("DELETE FROM entries WHERE id=?", (entry_id,))
                    con.execute("DELETE FROM coach_chunks WHERE id=?", ("entry:" + entry_id,))
                else:
                    seen.add(day)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(str(self.path), timeout=15)
        try:
            with con:
                yield con
        finally:
            con.close()

    def profile(self):
        with self.connect() as con:
            row = con.execute("SELECT data FROM settings WHERE key='profile'").fetchone()
        result = {**DEFAULT_PROFILE, **(json.loads(row[0]) if row else {})}
        result["cardio_goal"] = validate_cardio_goal(result["cardio_goal"])
        result["supplements"] = supplement_options(result["supplements"])
        result["consistency_supplements"] = [
            n for n in result["consistency_supplements"] if n.casefold() != "creatine"
        ]
        result["supplement_goals"] = hydrate_supplement_goals(result)
        return with_goals(result, result.get("goals"))

    def save_profile(self, p):
        if not isinstance(p, dict):
            raise ValueError("Profile must be an object.")
        current = self.profile()
        result = {key: p.get(key, current[key]) for key in DEFAULT_PROFILE}
        result["cardio_goal"] = validate_cardio_goal(result["cardio_goal"])
        for key in ("name", "focus", "experience", "constraints"):
            result[key] = text(result[key], key, 1000, False)
        if "goals" in p:
            if p["goals"] is None:
                raise ValueError("Set overall gym, protein and creatine goals.")
            result = with_goals(result, p["goals"])
        elif any(key in p for key in ("weekly_goal", "protein_goal", "creatine_goal")):
            # Legacy updates change only their own target, preserving other timeframes.
            goals = dict(current["goals"])
            for key, target, low, high, unit in (
                ("weekly_goal", "workout", 1, 7, "week"),
                ("protein_goal", "protein", 1, 500, "day"),
                ("creatine_goal", "creatine", 0, 20, "day"),
            ):
                if key not in p:
                    continue
                amount = number(p[key], key, low, high)
                if key == "weekly_goal" and amount != int(amount):
                    raise ValueError("Weekly goal must be a whole number.")
                goals[target] = {"amount": amount, "period": 1, "unit": unit}
            result = with_goals(result, goals)
        else:
            result = with_goals(result, current["goals"])
        result["sleep_goal"] = number(result["sleep_goal"], "Daily sleep target", 0.1, 24)
        result["night_hours_goal"] = number(
            result["night_hours_goal"], "Night sleep target", 0.1, result["sleep_goal"]
        )
        result["night_sleep_goal"] = number(
            result["night_sleep_goal"], "Continuous night target", 0.1, result["sleep_goal"]
        )
        if result["weight_kg"] not in (None, ""):
            result["weight_kg"] = number(result["weight_kg"], "Body weight", 20, 500)
        else:
            result["weight_kg"] = None
        result["supplements"] = supplement_options(result["supplements"])
        choices = result["consistency_supplements"]
        if not isinstance(choices, list) or len(choices) > 100:
            raise ValueError("Choose supplements from your routine.")
        choices = list(
            dict.fromkeys(supplement_name(v) for v in choices if supplement_name(v) != "Creatine")
        )
        if any(v not in result["supplements"] for v in choices):
            raise ValueError(
                "Add a supplement to your selection list before tracking its consistency."
            )
        result["consistency_supplements"] = choices
        supplied = p.get("supplement_goals", current["supplement_goals"])
        result["supplement_goals"] = {
            **{k: v for k, v in current["supplement_goals"].items() if k in result["supplements"]},
            **validate_supplement_goals(supplied, result["supplements"]),
        }
        if "supplement_goals" in p and any(
            name != "Creatine" and name not in result["supplement_goals"] for name in choices
        ):
            raise ValueError("Set a goal for every selected supplement.")
        result["consistency_supplements"] = [
            n for n in result["consistency_supplements"] if n.casefold() != "creatine"
        ]
        result["supplement_goals"] = hydrate_supplement_goals(result)
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO settings VALUES ('profile', ?)", (json.dumps(result),)
            )
        return result

    def _register_supplement(self, con, name):
        name = supplement_name(name)
        if name == "Creatine":
            raise ValueError("Use dedicated Creatine tracking, not the supplement list.")
        row = con.execute("SELECT data FROM settings WHERE key='profile'").fetchone()
        profile = json.loads(row[0]) if row else {}
        options = supplement_options(profile.get("supplements", []))
        existing = next(
            (option for option in options if option.casefold() == name.casefold()), None
        )
        if not existing:
            options = supplement_options(options + [name])
        if profile.get("supplements") != options:
            profile["supplements"] = options
            con.execute(
                "INSERT OR REPLACE INTO settings VALUES ('profile', ?)", (json.dumps(profile),)
            )
        return existing or name

    def add_supplement(self, name):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            chosen = self._register_supplement(con, name)
        return {"name": chosen, "options": self.profile()["supplements"]}

    def entries(self):
        with self.connect() as con:
            rows = con.execute("SELECT id, kind, data FROM entries ORDER BY rowid DESC").fetchall()
        entries = [dict(json.loads(d), id=i, kind=k) for i, k, d in rows]
        for entry in entries:
            if is_creatine(entry):
                entry["kind"] = "creatine"
            if entry["kind"] == "plan":
                entry.update(validate("plan", entry))
                for key in ("duration", "notes"):
                    entry.pop(key, None)
            if entry["kind"] in ("workout", "home_workout", "plan"):
                entry["name"] = session_title(entry["date"])
        return sorted(
            entries,
            key=lambda e: e["date"],
            reverse=True,
        )

    def save(self, kind, raw, entry_id=None, _con=None):
        data = validate(kind, raw)
        if is_creatine({"kind": kind, **data}):
            kind = "creatine"
        with nullcontext(_con) if _con is not None else self.connect() as con:
            if _con is None:
                con.execute("BEGIN IMMEDIATE")
            original = (
                con.execute("SELECT kind,data FROM entries WHERE id=?", (entry_id,)).fetchone()
                if entry_id
                else None
            )
            if raw.get("id") and not original:
                raise ValueError("Entry no longer exists. Reopen the current day's workout.")
            if (
                original
                and original[0] != kind
                and (
                    kind in ("workout", "home_workout")
                    or original[0] in ("workout", "home_workout")
                )
            ):
                raise ValueError("Edit the original gym or home workout in its own category.")
            if kind == "sleep":
                others = [
                    json.loads(row[0])
                    for row in con.execute(
                        "SELECT data FROM entries WHERE kind='sleep' AND id != ?", (entry_id or "",)
                    )
                ]
                if (
                    sum(e["hours"] for e in others if e["date"] == data["date"]) + data["hours"]
                    > 24.00001
                ):
                    raise ValueError("Sleep entries cannot total more than 24 hours on one date.")
            if kind == "supplement":
                data["name"] = self._register_supplement(con, data["name"])
            if kind == "workout":
                same_day = [
                    (old_id, old_data)
                    for old_id, old_data in con.execute(
                        "SELECT id,data FROM entries WHERE kind='workout' ORDER BY rowid DESC"
                    ).fetchall()
                    if json.loads(old_data)["date"] == data["date"]
                ]
                entry_id = entry_id or (same_day[0][0] if same_day else uuid.uuid4().hex)
                archived = set()
                for old_id, old_data in same_day:
                    self._archive_workout(con, old_id, old_data)
                    archived.add(old_id)
                    if old_id != entry_id:
                        con.execute("DELETE FROM entries WHERE id=?", (old_id,))
                        con.execute("DELETE FROM coach_chunks WHERE id=?", ("entry:" + old_id,))
                if original and entry_id not in archived and original[0] == "workout":
                    self._archive_workout(con, entry_id, original[1])
            entry_id = entry_id or uuid.uuid4().hex
            con.execute(
                "INSERT OR REPLACE INTO entries VALUES (?, ?, ?)",
                (entry_id, kind, json.dumps(data)),
            )
            from .semantic_index import journal_chunk

            journal_chunk(con, entry_id, kind, data)
        return dict(data, id=entry_id, kind=kind)

    def delete(self, entry_id):
        with self.connect() as con:
            con.execute("DELETE FROM entries WHERE id=?", (entry_id,))
            con.execute("DELETE FROM coach_chunks WHERE id=?", ("entry:" + entry_id,))
            con.execute("DELETE FROM workout_revisions WHERE entry_id=?", (entry_id,))

    def reset(self):
        """Clear personal journal data atomically; retain only the internal demo seed marker."""
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM coach_chunks WHERE category!='exercise'")
            for table in (
                "entries",
                "workout_revisions",
                "messages",
                "drafts",
                "completed_chat_requests",
            ):
                con.execute(f"DELETE FROM {table}")
            con.execute("DELETE FROM settings WHERE key != 'demo_initialized'")

    def coach_consent(self):
        with self.connect() as con:
            row = con.execute("SELECT data FROM settings WHERE key='coach_consent'").fetchone()
        value = json.loads(row[0]) if row else {}
        return {
            "accepted": value.get("accepted") is True and value.get("version") == 1,
            "version": 1,
            "providers": ["ollama"],
            "accepted_at": value.get("accepted_at"),
        }

    def set_coach_consent(self, accepted, version=1):
        if not isinstance(accepted, bool) or type(version) is not int or version != 1:
            raise ValueError("Review the current sharing agreement and choose whether to accept.")
        value = {
            "accepted": accepted,
            "version": 1,
            "accepted_at": datetime.now(timezone.utc).isoformat() if accepted else None,
        }
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO settings VALUES ('coach_consent', ?)", (json.dumps(value),)
            )
        return self.coach_consent()

    def update_message(self, message_id, data):
        with self.connect() as con:
            self._cache_chat_exchange(con, message_id)
            con.execute("UPDATE messages SET data=? WHERE id=?", (json.dumps(data), message_id))

    def _cache_chat_exchange(self, con, message_id):
        """Freeze a completed response before its visible exchange can be edited."""
        row = con.execute(
            "SELECT data FROM messages WHERE id=? AND role='user'", (message_id,)
        ).fetchone()
        if not row:
            return
        user = json.loads(row[0])
        request_id = user.get("request_id")
        if not request_id or user.get("status") in ("pending", "failed"):
            return
        answer = con.execute(
            "SELECT id,role,data FROM messages WHERE id>? ORDER BY id LIMIT 1", (message_id,)
        ).fetchone()
        if not answer or answer[1] != "assistant":
            return
        response = json.loads(answer[2])
        if response.get("request_id") != request_id:
            return
        con.execute(
            "INSERT OR IGNORE INTO completed_chat_requests VALUES (?,?,?,?,?)",
            (request_id, message_id, answer[0], row[0], answer[2]),
        )

    def chat_request(self, request_id):
        with self.connect() as con:
            cached = con.execute(
                "SELECT user_id,response_id,user_data,response_data FROM completed_chat_requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if cached:
                return [
                    dict(json.loads(cached[2]), role="user", id=cached[0]),
                    dict(json.loads(cached[3]), role="assistant", id=cached[1]),
                ]
            rows = con.execute(
                "SELECT id,role,data FROM messages WHERE json_extract(data,'$.request_id')=? ORDER BY id",
                (request_id,),
            ).fetchall()
        return [dict(json.loads(data), role=role, id=message_id) for message_id, role, data in rows]

    def recover_chat_requests(self):
        with self.connect() as con:
            rows = con.execute(
                "SELECT id,data FROM messages WHERE role='user' AND json_extract(data,'$.status')='pending'"
            ).fetchall()
            for message_id, raw in rows:
                data = json.loads(raw)
                data.update(
                    status="failed",
                    error="The app restarted before this answer finished. You can retry your message.",
                )
                con.execute("UPDATE messages SET data=? WHERE id=?", (json.dumps(data), message_id))

    def complete_chat_request(self, message_id, user, response):
        from .semantic_index import upsert

        with self.connect() as con:
            self._cache_chat_exchange(con, message_id)
            # Quoted conversation is recall evidence, never a journal observation or instruction.
            upsert(
                con,
                "conversation:" + str(message_id),
                "conversation",
                user.get("context_date", date.today().isoformat()),
                "User said: "
                + user["text"]
                + "\nCoach replied (unverified conversation): "
                + response["text"][:2000],
            )
            user = {**user, "status": "sent"}
            con.execute("UPDATE messages SET data=? WHERE id=?", (json.dumps(user), message_id))
            replacement = user.get("replace_response_id")
            if replacement:
                con.execute(
                    "UPDATE messages SET data=? WHERE id=? AND role='assistant'",
                    (json.dumps(response), replacement),
                )
            else:
                con.execute(
                    "INSERT INTO messages(role,data) VALUES ('assistant',?)",
                    (json.dumps(response),),
                )
            self._cache_chat_exchange(con, message_id)

    def editable_chat_exchange(self, message_id):
        """Resolve a current, unresolved logging exchange before replacing its source."""
        if type(message_id) is not int or message_id < 1:
            raise ValueError("Choose a logging message to edit.")
        messages = self.messages()
        index = next((i for i, m in enumerate(messages) if m["id"] == message_id), None)
        if index is None or messages[index]["role"] != "user":
            raise ValueError("That logging message is no longer in this chat.")
        user = messages[index]
        if user.get("revise_draft_id"):
            raise ValueError(
                "This message is a correction. Suggest changes to its pending preview instead of replacing the full source."
            )
        answer = messages[index + 1] if index + 1 < len(messages) else None
        if answer and answer["role"] != "assistant":
            answer = None
        draft = next(
            (d for d in self.drafts() if answer and d["id"] == answer.get("draft", {}).get("id")),
            None,
        )
        if (answer and answer.get("approved")) or not (
            draft
            or (user.get("logging_kind") and (not answer or answer.get("action") == "clarify"))
            or (user.get("status") == "failed" and user.get("edit_message_id"))
        ):
            raise ValueError(
                "Only an unresolved logging message can be edited. Start a new log instead."
            )
        return user, answer, draft

    def message(self, role, data):
        with self.connect() as con:
            return con.execute(
                "INSERT INTO messages(role,data) VALUES (?,?)", (role, json.dumps(data))
            ).lastrowid

    def coach_state(self, key="task", value=None):
        setting = "coach_" + key
        with self.connect() as con:
            if value is not None:
                con.execute(
                    "INSERT OR REPLACE INTO settings VALUES (?,?)", (setting, json.dumps(value))
                )
                return value
            row = con.execute("SELECT data FROM settings WHERE key=?", (setting,)).fetchone()
        return json.loads(row[0]) if row else {}

    def start_chat(self):
        """Archive the current conversation and exclude it from future model history."""
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM settings WHERE key IN ('coach_task','coach_scope')")
            con.execute("DELETE FROM coach_chunks WHERE category='conversation'")
            last_id = con.execute("SELECT COALESCE(MAX(id),0) FROM messages").fetchone()[0]
            con.execute(
                "INSERT OR REPLACE INTO settings VALUES ('chat_start_id', ?)",
                (json.dumps(last_id),),
            )
            hidden = [row[0] for row in con.execute("SELECT id FROM drafts WHERE status='pending'")]
            con.execute(
                "INSERT OR REPLACE INTO settings VALUES ('chat_hidden_drafts', ?)",
                (json.dumps(hidden),),
            )
            con.execute("UPDATE drafts SET status='dismissed' WHERE status='pending'")

    def chat_hidden_drafts(self):
        with self.connect() as con:
            row = con.execute("SELECT data FROM settings WHERE key='chat_hidden_drafts'").fetchone()
        return json.loads(row[0]) if row else []

    def messages(self, include_archived=False):
        with self.connect() as con:
            row = con.execute("SELECT data FROM settings WHERE key='chat_start_id'").fetchone()
            boundary = int(json.loads(row[0])) if row and not include_archived else 0
            rows = con.execute(
                "SELECT id,role,data FROM messages WHERE id>? ORDER BY id DESC", (boundary,)
            ).fetchall()
        return [dict(json.loads(d), role=r, id=i) for i, r, d in reversed(rows)]

    def _draft_items(self, kind, data):
        if kind == "batch":
            items = data.get("entries") if isinstance(data, dict) else None
            if not isinstance(items, list) or not 1 <= len(items) <= 12:
                raise ValueError("Prepare between 1 and 12 entries at a time.")
        else:
            items = [{"kind": kind, "data": data}]
        clean = []
        for item in items:
            if not isinstance(item, dict) or item.get("kind") not in (
                "meal",
                "cardio",
                "workout",
                "home_workout",
                "plan",
                "supplement",
                "creatine",
                "sleep",
                "body",
            ):
                raise ValueError("Choose a supported journal entry type.")
            validated = validate(item["kind"], item.get("data"))
            entry_kind = (
                "creatine" if is_creatine({"kind": item["kind"], **validated}) else item["kind"]
            )
            clean.append({"kind": entry_kind, "data": validated})
        if len({item["data"]["date"] for item in clean}) != 1:
            raise ValueError("Prepare one journal day at a time.")
        if sum(item["kind"] == "workout" for item in clean) > 1:
            raise ValueError("Combine completed exercises into one workout for the day.")
        return clean

    def _baseline(self, con, items):
        days = {item["data"]["date"] for item in items}
        records = [
            (eid, k, d)
            for eid, k, d in con.execute("SELECT id,kind,data FROM entries ORDER BY id")
            if json.loads(d)["date"] in days
        ]
        return hashlib.sha256(json.dumps(records).encode()).hexdigest()

    def draft(self, kind, data):
        items = self._draft_items(kind, data)
        data = {"entries": items} if kind == "batch" else items[0]["data"]
        if kind != "batch":
            kind = items[0]["kind"]
        draft_id = uuid.uuid4().hex
        with self.connect() as con:
            con.execute(
                "INSERT INTO drafts(id,kind,data,baseline) VALUES (?,?,?,?)",
                (draft_id, kind, json.dumps(data), self._baseline(con, items)),
            )
        return {"id": draft_id, "kind": kind, "data": data, "status": "pending"}

    def drafts(self):
        with self.connect() as con:
            rows = con.execute(
                "SELECT id,kind,data,status FROM drafts WHERE status='pending'"
            ).fetchall()
        result = []
        for i, k, d, status in rows:
            items = self._draft_items(k, json.loads(d))
            result.append(
                {
                    "id": i,
                    "kind": k if k == "batch" else items[0]["kind"],
                    "data": {"entries": items} if k == "batch" else items[0]["data"],
                    "status": status,
                }
            )
        return result

    def _supersede_workout_previews(self, con):
        # One saved workout per day: a later approval replaces earlier workout proposals.
        # Keep raw proposals for audit, and keep other dates, plans and mixed batches pending.
        rows = con.execute(
            "SELECT rowid,id,kind,data,status FROM drafts "
            "WHERE status IN ('pending','approved') ORDER BY rowid"
        ).fetchall()
        approved_days = {}
        pending = []
        for order, draft_id, kind, raw, status in rows:
            data = json.loads(raw)
            items = data["entries"] if kind == "batch" else [{"kind": kind, "data": data}]
            if status == "approved":
                for item in items:
                    if item["kind"] == "workout":
                        approved_days[item["data"]["date"]] = order
            elif all(item["kind"] == "workout" for item in items):
                pending.append((order, draft_id, items[0]["data"]["date"]))
        for order, draft_id, day in pending:
            if order < approved_days.get(day, 0):
                con.execute("UPDATE drafts SET status='superseded' WHERE id=?", (draft_id,))

    def _apply_draft(self, con, draft_id, edited=None):
        row = con.execute(
            "SELECT kind,data,baseline FROM drafts WHERE id=? AND status='pending'", (draft_id,)
        ).fetchone()
        if not row:
            raise ValueError(
                "This preview is no longer pending. It was approved, replaced or reverted."
            )
        items = self._draft_items(row[0], edited if edited is not None else json.loads(row[1]))
        task = con.execute("SELECT data FROM settings WHERE key='coach_task'").fetchone()
        if task:
            task = json.loads(task[0])
            if task.get("draft_id") == draft_id and task.get("incomplete"):
                raise ValueError(
                    "Resolve the highlighted workout questions before approving this preview."
                )
        if row[2] and row[2] != "{}" and self._baseline(con, items) != row[2]:
            raise ValueError(
                "This day changed after the preview was prepared. Ask the coach to prepare a fresh preview before approving."
            )
        saved = []
        for item in items:
            kind, data = item["kind"], item["data"]
            if kind == "workout":
                current = next(
                    (
                        json.loads(d)
                        for (d,) in con.execute(
                            "SELECT data FROM entries WHERE kind='workout' ORDER BY rowid DESC"
                        )
                        if json.loads(d)["date"] == data["date"]
                    ),
                    None,
                )
                if current:
                    replacements = {e["exercise_id"]: e for e in data["exercises"]}
                    merged = [replacements.pop(e["exercise_id"], e) for e in current["exercises"]]
                    data = {
                        **data,
                        "exercises": merged + list(replacements.values()),
                        "duration": data["duration"] or current.get("duration", 0),
                        "notes": data["notes"] or current.get("notes", ""),
                    }
            saved.append(self.save(kind, data, _con=con))
        approved_data = {"entries": items} if row[0] == "batch" else items[0]["data"]
        con.execute(
            "UPDATE drafts SET status='approved',data=? WHERE id=?",
            (json.dumps(approved_data), draft_id),
        )
        self._supersede_workout_previews(con)
        return saved

    def preview(self, draft_id):
        # Exercise the same validation/merge rules, then roll back every write.
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                entries = self._apply_draft(con, draft_id)
            finally:
                con.rollback()
        return {"entries": entries, "date": entries[0]["date"], "draft_id": draft_id}

    def approve(self, draft_id, edited=None):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            entries = self._apply_draft(con, draft_id, edited)
        return entries[0] if len(entries) == 1 else {"entries": entries}

    def dismiss(self, draft_id):
        with self.connect() as con:
            con.execute(
                "UPDATE drafts SET status='dismissed' WHERE id=? AND status='pending'", (draft_id,)
            )


def insights(entries, profile, today=None):
    today = today or date.today()
    profile = with_goals(profile, profile.get("goals"))
    profile.setdefault("consistency_supplements", [])
    start = today - timedelta(days=today.weekday())
    workouts = [e for e in entries if e["kind"] == "workout" and e["date"] <= today.isoformat()]
    week_days = sorted({e["date"] for e in workouts if start.isoformat() <= e["date"]})
    daily, muscles, prs, monthly, frequency = {}, {}, {}, {}, {}
    body_parts, area_details = {}, {}
    sleep = sleep_days(entries)
    for i in range(84):
        day = (today - timedelta(days=83 - i)).isoformat()
        daily[day] = {
            "protein": 0,
            "calories": 0,
            "calorie_meals": 0,
            "cardio_minutes": 0,
            "creatine": 0,
            "workouts": 0,
            "home_workouts": 0,
            "sets": 0,
            "meals": 0,
            "body": None,
            "sleep": sleep.get(day),
        }
    recent_start = (today - timedelta(days=27)).isoformat()
    for e in entries:
        day = daily.get(e["date"])
        if day is not None:
            if e["kind"] == "meal":
                day["protein"] += e["protein"]
                day["meals"] += 1
                if e.get("calories") is not None:
                    day["calories"] += e["calories"]
                    day["calorie_meals"] += 1
            if e["kind"] == "cardio":
                day["cardio_minutes"] += e["minutes"]
            if is_creatine(e) and e["unit"] == "g":
                day["creatine"] += e["amount"]
            if e["kind"] == "body":
                if day["body"] is None:
                    day["body"] = e["weight_kg"]
        if e["kind"] not in ("workout", "home_workout") or e["date"] > today.isoformat():
            continue
        if day is not None:
            day["home_workouts" if e["kind"] == "home_workout" else "workouts"] += 1
        seen = set()
        for item in e["exercises"]:
            ex = EXERCISES[item["exercise_id"]]
            if day is not None:
                day["sets"] += len(item["sets"])
            if e["date"] >= recent_start:
                for group in ex["bodyParts"]:
                    body_parts[group] = body_parts.get(group, 0) + len(item["sets"])
                    detail = area_details.setdefault(group, {"areas": {}, "exercises": {}})
                    detail["exercises"][ex["id"]] = detail["exercises"].get(ex["id"], 0) + len(
                        item["sets"]
                    )
                    for area in training_areas(ex, group):
                        detail["areas"][area] = detail["areas"].get(area, 0) + len(item["sets"])
                for muscle in ex["primaryMuscles"]:
                    muscles[muscle] = muscles.get(muscle, 0) + len(item["sets"])
                if ex["id"] not in seen:
                    frequency[ex["id"]] = frequency.get(ex["id"], 0) + 1
                    seen.add(ex["id"])
            pr = prs.setdefault(
                ex["id"],
                {"weight": 0, "reps": 0, "seconds": 0, "estimated_1rm": 0, "date": e["date"]},
            )
            month = e["date"][:7]
            history = monthly.setdefault(ex["id"], {})
            for s in item["sets"]:
                if s["weight"] > pr["weight"] or (
                    s["weight"] == pr["weight"] and s["reps"] > pr["reps"]
                ):
                    pr.update(weight=s["weight"], reps=s["reps"], date=e["date"])
                if s["seconds"] > pr["seconds"]:
                    pr["seconds"] = s["seconds"]
                    pr["seconds_date"] = e["date"]
                if 1 <= s["reps"] <= 10 and s["weight"] > 0:
                    pr["estimated_1rm"] = max(
                        pr["estimated_1rm"],
                        round(
                            s["weight"] if s["reps"] == 1 else s["weight"] * (1 + s["reps"] / 30), 1
                        ),
                    )
                m = history.setdefault(month, {"weight": 0, "reps": 0, "seconds": 0})
                m["weight"] = max(m["weight"], s["weight"])
                m["reps"] = max(m["reps"], s["reps"])
                m["seconds"] = max(m["seconds"], s["seconds"])
    recent = list(daily.values())[-28:]
    logged = [d for d in recent if d["meals"]]
    return {
        "sleep_average": round(
            sum(d["hours"] for day, d in sleep.items() if recent_start <= day <= today.isoformat())
            / len([day for day in sleep if recent_start <= day <= today.isoformat()]),
            1,
        )
        if any(recent_start <= day <= today.isoformat() for day in sleep)
        else None,
        "consistency": consistency(entries, profile, today),
        "consistency_trend": consistency_trend(entries, profile, today),
        "today": daily[today.isoformat()],
        "daily": daily,
        "weekly_days": week_days,
        "week_start": start.isoformat(),
        "cardio_week": weekly_cardio(entries, profile["cardio_goal"], today, today),
        "workouts": len(workouts),
        "home_workouts": sum(
            e["kind"] == "home_workout" and e["date"] <= today.isoformat() for e in entries
        ),
        "prs": prs,
        "monthly": monthly,
        "muscles": muscles,
        "body_parts": body_parts,
        "area_details": area_details,
        "frequency": frequency,
        "protein_average": round(sum(d["protein"] for d in logged) / len(logged), 1)
        if logged
        else None,
        "nutrition_days": len(logged),
        "creatine_days": sum(d["creatine"] > 0 for d in recent),
        "protein_goal_days": sum(
            d["protein"] >= profile["protein_goal"] for d in list(daily.values())[-29:-1]
        )
        if not profile.get("goals")
        or (
            profile["goals"]["protein"]["period"] == 1
            and profile["goals"]["protein"]["unit"] == "day"
        )
        else None,
    }
