import math
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

from fitness_tracker.store import CATALOG, Store, insights, session_title, validate

EX = "Barbell_Curl"


def workout(day=None, weight=20, reps=8, seconds=0):
    return {
        "date": day or date.today().isoformat(),
        "name": "Arms",
        "duration": 40,
        "exercises": [
            {"exercise_id": EX, "sets": [{"weight": weight, "reps": reps, "seconds": seconds}]}
        ],
    }


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_catalog_and_all_photos_bundled(self):
        root = Path(__file__).resolve().parents[1] / "src/fitness_tracker/web/assets/exercises"
        self.assertGreater(len(CATALOG), 800)
        self.assertEqual(len({e["id"] for e in CATALOG}), len(CATALOG))
        self.assertTrue(all((root / (e["id"] + ".webp")).is_file() for e in CATALOG))

    def test_week_counts_unique_days_and_excludes_plans(self):
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        for _ in range(2):
            self.store.save("workout", workout(monday.isoformat()))
        self.store.save("workout", workout((monday - timedelta(days=1)).isoformat()))
        self.store.save("plan", workout((today + timedelta(days=1)).isoformat()))
        s = insights(self.store.entries(), self.store.profile(), today)
        self.assertEqual(s["weekly_days"], [monday.isoformat()])
        self.assertEqual(s["workouts"], 2)

    def test_missing_food_is_not_zero_in_average(self):
        self.store.save(
            "meal", {"date": date.today().isoformat(), "description": "eggs", "protein": 25}
        )
        s = insights(self.store.entries(), self.store.profile())
        self.assertEqual(s["protein_average"], 25)
        self.assertEqual(s["nutrition_days"], 1)
        self.assertEqual(s["daily"][(date.today() - timedelta(days=1)).isoformat()]["meals"], 0)

    def test_pr_and_monthly_history(self):
        self.store.save("workout", workout("2026-01-01", 15, 10))
        self.store.save("workout", workout("2026-02-02", 20, 6))
        self.store.save("workout", workout("2026-02-03", 20, 8))
        self.store.save("workout", workout("2026-03-01", 18, 12))
        s = insights(self.store.entries(), self.store.profile(), date(2026, 4, 1))
        self.assertEqual(s["prs"][EX]["weight"], 20)
        self.assertEqual(s["prs"][EX]["reps"], 8)
        self.assertAlmostEqual(s["prs"][EX]["estimated_1rm"], 25.3)
        self.assertEqual(s["monthly"][EX]["2026-01"]["weight"], 15)
        self.assertEqual(s["monthly"][EX]["2026-03"]["weight"], 18)

    def test_approval_is_atomic_and_exactly_once(self):
        draft = self.store.draft(
            "meal", {"date": date.today().isoformat(), "description": "Lunch", "protein": 30}
        )
        self.assertEqual(self.store.entries(), [])

        def approve():
            try:
                return self.store.approve(draft["id"], {**draft["data"], "protein": 32})
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: approve(), range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(self.store.entries()[0]["protein"], 32)
        self.assertEqual(self.store.drafts(), [])

    def test_invalid_edits_leave_pending_draft(self):
        draft = self.store.draft(
            "meal", {"date": date.today().isoformat(), "description": "Lunch", "protein": 30}
        )
        with self.assertRaises(ValueError):
            self.store.approve(draft["id"], {**draft["data"], "protein": math.nan})
        self.assertEqual(len(self.store.drafts()), 1)
        self.assertEqual(self.store.entries(), [])

    def test_bad_values_rejected(self):
        for weight in (-1, 1001, math.inf, math.nan, True):
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                validate("workout", workout(weight=weight))
        for reps in (1.5, -1, 1001):
            with self.subTest(reps=reps), self.assertRaises(ValueError):
                validate("workout", workout(reps=reps))
        with self.assertRaises(ValueError):
            validate("workout", workout(reps=0))
        self.assertEqual(
            validate("workout", workout(weight=0, reps=0, seconds=60))["exercises"][0]["sets"][0][
                "seconds"
            ],
            60,
        )

    def test_future_entries_use_the_selected_date(self):
        future = (date.today() + timedelta(days=1)).isoformat()
        self.assertEqual(self.store.save("workout", workout(future))["date"], future)
        self.assertEqual(self.store.save("plan", workout(future))["date"], future)

    def test_creatine_units_and_estimate_range(self):
        with self.assertRaises(ValueError):
            validate(
                "supplement",
                {"date": date.today().isoformat(), "name": "Creatine", "amount": 5, "unit": "mg"},
            )
        with self.assertRaises(ValueError):
            validate(
                "meal",
                {
                    "date": date.today().isoformat(),
                    "description": "Lunch",
                    "protein": 50,
                    "low": 20,
                    "high": 40,
                },
            )

    def test_persistence_edit_delete(self):
        entry = self.store.save("workout", workout())
        self.store.save("workout", {**entry, "notes": "Updated"}, entry["id"])
        reopened = Store(self.temp.name)
        self.assertEqual(reopened.entries()[0]["notes"], "Updated")
        reopened.delete(entry["id"])
        self.assertEqual(reopened.entries(), [])

    def test_dismissed_draft_cannot_log(self):
        draft = self.store.draft("plan", workout())
        self.store.dismiss(draft["id"])
        with self.assertRaises(ValueError):
            self.store.approve(draft["id"], draft["data"])
        self.assertEqual(self.store.entries(), [])

    def test_duration_pr_tracks_the_date_it_was_set(self):
        self.store.save("workout", workout("2026-01-01", 0, 0, 60))
        self.store.save("workout", workout("2026-02-01", 0, 0, 45))
        result = insights(self.store.entries(), self.store.profile(), date(2026, 4, 1))
        self.assertEqual(result["prs"][EX]["seconds"], 60)
        self.assertEqual(result["prs"][EX]["seconds_date"], "2026-01-01")

    def test_one_rep_estimate_equals_actual_load(self):
        self.store.save("workout", workout(weight=20, reps=1))
        result = insights(self.store.entries(), self.store.profile())
        self.assertEqual(result["prs"][EX]["estimated_1rm"], 20)

    def test_workout_and_nutrition_can_share_any_selected_day(self):
        for offset in (-365, -4, 0, 3):
            day = (date.today() + timedelta(days=offset)).isoformat()
            with self.subTest(day=day):
                raw = workout(day)
                w = self.store.save("workout", raw)
                m = self.store.save("meal", {"date": day, "description": "Lunch", "protein": 30})
                s = self.store.save(
                    "supplement", {"date": day, "name": "Creatine", "amount": 5, "unit": "g"}
                )
                self.assertEqual({w["date"], m["date"], s["date"]}, {day})

    def test_history_can_be_corrected_and_redated(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        older = (date.today() - timedelta(days=2)).isoformat()
        entry = self.store.save("workout", workout(yesterday))
        updated = self.store.save("workout", {**entry, "date": older}, entry["id"])
        self.assertEqual(updated["date"], older)
        self.assertEqual(updated["name"], session_title(older))

    def test_food_draft_approval_preserves_selected_historical_date(self):
        day = (date.today() - timedelta(days=4)).isoformat()
        raw = {"date": day, "description": "Lunch", "protein": 30}
        draft = self.store.draft("meal", raw)
        result = self.store.approve(draft["id"], raw)
        self.assertEqual(result["date"], day)

    def test_session_titles_use_requested_date_format(self):
        self.assertEqual(session_title("2026-11-05"), "Nov 5th 26'")
        for day, suffix in [
            (1, "st"),
            (2, "nd"),
            (3, "rd"),
            (11, "th"),
            (12, "th"),
            (13, "th"),
            (21, "st"),
            (22, "nd"),
            (23, "rd"),
            (31, "st"),
        ]:
            self.assertEqual(session_title(f"2026-01-{day:02d}"), f"Jan {day}{suffix} 26'")

    def test_workout_name_is_automatic_on_create_edit_and_read(self):
        raw = workout()
        raw.pop("name")
        entry = self.store.save("workout", raw)
        self.assertEqual(entry["name"], session_title(raw["date"]))
        updated = self.store.save("workout", {**entry, "name": "Unneeded title"}, entry["id"])
        self.assertEqual(updated["name"], session_title(raw["date"]))
        self.assertEqual(self.store.entries()[0]["name"], updated["name"])

    def test_planks_require_time_and_no_reps(self):
        raw = workout(weight=0, reps=0, seconds=45)
        raw["exercises"][0]["exercise_id"] = "Plank"
        entry = self.store.save("workout", raw)
        self.assertEqual(entry["exercises"][0]["tracking"], "time")
        self.assertEqual(entry["exercises"][0]["sets"][0]["seconds"], 45)
        raw["exercises"][0]["sets"][0]["reps"] = 10
        with self.assertRaisesRegex(ValueError, "no reps"):
            self.store.save("workout", raw)
        raw["exercises"][0]["tracking"] = "reps"
        with self.assertRaisesRegex(ValueError, "Planks"):
            self.store.save("workout", raw)

    def test_reps_and_time_are_exclusive(self):
        raw = workout(weight=0, reps=0, seconds=60)
        raw["exercises"][0]["tracking"] = "time"
        self.assertEqual(self.store.save("workout", raw)["exercises"][0]["sets"][0]["reps"], 0)
        raw["exercises"][0]["tracking"] = "reps"
        with self.assertRaises(ValueError):
            self.store.save("workout", raw)

    def test_edit_and_delete_recompute_records(self):
        first = self.store.save(
            "workout", workout((date.today() - timedelta(days=1)).isoformat(), weight=20, reps=8)
        )
        second = self.store.save("workout", workout(weight=25, reps=8))
        self.assertEqual(
            insights(self.store.entries(), self.store.profile())["prs"][EX]["weight"], 25
        )
        self.store.save(
            "workout",
            {**second, "exercises": [{"exercise_id": EX, "sets": [{"weight": 15, "reps": 8}]}]},
            second["id"],
        )
        self.assertEqual(
            insights(self.store.entries(), self.store.profile())["prs"][EX]["weight"], 20
        )
        self.store.delete(first["id"])
        self.assertEqual(
            insights(self.store.entries(), self.store.profile())["prs"][EX]["weight"], 15
        )
        self.store.delete(second["id"])
        self.assertEqual(insights(self.store.entries(), self.store.profile())["prs"], {})

    def test_reset_clears_personal_data_and_records(self):
        self.store.save_profile({"name": "Example", "weekly_goal": 5})
        self.store.save("workout", workout())
        self.store.save(
            "meal", {"date": date.today().isoformat(), "description": "Lunch", "protein": 30}
        )
        self.store.message("user", {"text": "Example"})
        self.store.draft("plan", workout())
        self.store.reset()
        reopened = Store(self.temp.name)
        self.assertEqual(reopened.entries(), [])
        self.assertEqual(reopened.messages(), [])
        self.assertEqual(reopened.drafts(), [])
        self.assertEqual(reopened.profile()["name"], "")
        self.assertEqual(reopened.profile()["weekly_goal"], 3)
        self.assertEqual(insights(reopened.entries(), reopened.profile())["prs"], {})
        self.assertGreater(len(CATALOG), 800)

    def test_reset_demo_stays_empty_after_reopening(self):
        from fitness_tracker.server import seed_demo

        seed_demo(self.store)
        self.assertTrue(self.store.entries())
        self.store.reset()
        seed_demo(Store(self.temp.name))
        self.assertEqual(self.store.entries(), [])

    def test_wide_neutral_pullup_is_searchable_and_has_separate_records(self):
        from fitness_tracker.store import EXERCISES

        exercise = EXERCISES["Wide_Grip_Neutral_Pull_Up"]
        self.assertEqual(exercise["name"], "Wide-Grip Neutral Pull-Up")
        aliases = " ".join(exercise["aliases"]).lower()
        for term in ("parallel", "v-bar", "semi"):
            self.assertIn(term, aliases)
        self.assertIn("reference", exercise["photoNote"].lower())
        raw = workout((date.today() - timedelta(days=1)).isoformat(), weight=0, reps=6)
        raw["exercises"][0]["exercise_id"] = exercise["id"]
        self.store.save("workout", raw)
        self.store.save("workout", workout(weight=0, reps=10))
        records = insights(self.store.entries(), self.store.profile())["prs"]
        self.assertEqual(records[exercise["id"]]["reps"], 6)
        self.assertEqual(records[EX]["reps"], 10)

    def test_default_supplement_choices(self):
        self.assertEqual(
            self.store.profile()["supplements"],
            ["Vitamin D", "Vitamin C", "Vitamin B12", "Fish Oil", "Collagen"],
        )

    def test_custom_supplement_choice_persists_without_logging_intake(self):
        self.store.save_profile({"name": "Example", "weekly_goal": 4})
        result = self.store.add_supplement("Magnesium")
        self.assertEqual(result["name"], "Magnesium")
        reopened = Store(self.temp.name)
        self.assertIn("Magnesium", reopened.profile()["supplements"])
        self.assertEqual(reopened.profile()["name"], "Example")
        self.assertEqual(reopened.profile()["weekly_goal"], 4)
        self.assertEqual(reopened.entries(), [])
        again = reopened.add_supplement("magnesium")
        self.assertEqual(again["name"], "Magnesium")
        self.assertEqual(sum(name.lower() == "magnesium" for name in again["options"]), 1)

    def test_supplement_aliases_and_validation(self):
        self.assertEqual(self.store.add_supplement("vit d")["name"], "Vitamin D")
        self.assertEqual(self.store.add_supplement("vit b12")["name"], "Vitamin B12")
        self.assertEqual(self.store.add_supplement("fish oil")["name"], "Fish Oil")
        for name in ("", "   ", "x" * 101, None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.store.add_supplement(name)
        self.assertEqual(self.store.entries(), [])

    def test_logged_or_approved_supplements_join_selection_list(self):
        raw = {"date": date.today().isoformat(), "name": "Zinc", "amount": 1, "unit": "tablet"}
        self.store.save("supplement", raw)
        self.assertIn("Zinc", self.store.profile()["supplements"])
        draft = self.store.draft("supplement", {**raw, "name": "Magnesium"})
        self.assertNotIn("Magnesium", self.store.profile()["supplements"])
        self.store.approve(draft["id"], draft["data"])
        self.assertIn("Magnesium", self.store.profile()["supplements"])

    def test_concurrent_supplement_additions_are_not_lost(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(self.store.add_supplement, ["Magnesium", "Zinc"]))
        self.assertTrue({"Magnesium", "Zinc"}.issubset(self.store.profile()["supplements"]))

    def test_bodyweight_sets_do_not_require_load(self):
        raw = workout(weight=0, reps=12)
        item = raw["exercises"][0]
        item["exercise_id"] = "Flat_Bench_Lying_Leg_Raise"
        item["load_mode"] = "bodyweight"
        item["sets"][0].pop("weight")
        entry = self.store.save("workout", raw)
        self.assertEqual(entry["exercises"][0]["load_mode"], "bodyweight")
        self.assertEqual(entry["exercises"][0]["sets"][0]["weight"], 0)
        record = insights(self.store.entries(), self.store.profile())["prs"][item["exercise_id"]]
        self.assertEqual(record["reps"], 12)
        self.assertEqual(record["estimated_1rm"], 0)
        item["sets"][0]["weight"] = 10
        with self.assertRaisesRegex(ValueError, "Bodyweight"):
            self.store.save("workout", raw)

    def test_same_day_workout_saves_update_one_current_record(self):
        first = self.store.save("workout", workout(weight=20, reps=8))
        second = self.store.save("workout", workout(weight=25, reps=10))
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.store.entries()), 1)
        self.assertEqual(self.store.entries()[0]["exercises"][0]["sets"][0]["weight"], 25)
        s = insights(self.store.entries(), self.store.profile())
        self.assertEqual(s["workouts"], 1)
        self.assertEqual(s["today"]["sets"], 1)
        self.assertEqual(s["prs"][EX]["weight"], 25)

    def test_concurrent_same_day_updates_do_not_duplicate_workouts(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            entries = list(
                pool.map(lambda w: self.store.save("workout", workout(weight=w)), [20, 25])
            )
        self.assertEqual(entries[0]["id"], entries[1]["id"])
        self.assertEqual(len(self.store.entries()), 1)

    def test_legacy_duplicate_days_keep_latest_snapshot_with_backup(self):
        import json
        import sqlite3

        first = validate("workout", workout(weight=20, reps=8))
        latest = validate("workout", workout(weight=25, reps=10))
        with self.store.connect() as con:
            con.execute(
                "INSERT INTO entries VALUES (?,?,?)", ("older", "workout", json.dumps(first))
            )
            con.execute(
                "INSERT INTO entries VALUES (?,?,?)", ("latest", "workout", json.dumps(latest))
            )
        reopened = Store(self.temp.name)
        self.assertEqual(len(reopened.entries()), 1)
        self.assertEqual(reopened.entries()[0]["id"], "latest")
        backups = list((Path(self.temp.name) / "backups").glob("*.sqlite3"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(str(backups[0])) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM entries").fetchone()[0], 2)
        with reopened.connect() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM workout_revisions").fetchone()[0], 1)
