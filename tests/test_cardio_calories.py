import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.cardio import ACTIVITIES, weekly_cardio
from fitness_tracker.coach import Coach, Connections
from fitness_tracker.local_model import generate, response_schema
from fitness_tracker.store import Store, insights, validate

DAY = "2026-11-18"


class CardioAndCaloriesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def cardio(self, minutes=30, intensity="high", activity="Badminton"):
        return {"date": DAY, "activity": activity, "minutes": minutes, "intensity": intensity}

    def test_cardio_roundtrip_edit_delete_and_strength_separation(self):
        entry = self.store.save("cardio", self.cardio())
        reopened = Store(self.temp.name)
        self.assertEqual(reopened.entries()[0], entry)
        stats = insights(reopened.entries(), reopened.profile(), date(2026, 11, 19))
        self.assertEqual(stats["workouts"], 0)
        self.assertEqual(stats["prs"], {})
        self.assertEqual(stats["daily"][DAY]["cardio_minutes"], 30)
        changed = reopened.save("cardio", {**entry, "minutes": 45}, entry["id"])
        self.assertEqual(changed["minutes"], 45)
        reopened.delete(entry["id"])
        self.assertEqual(reopened.entries(), [])

    def test_goal_equivalence_mixed_target_and_calendar_boundaries(self):
        self.store.save_profile({"cardio_goal": {"moderate": 60, "high": 30}})
        self.store.save_profile({"name": "Updated"})
        goal = Store(self.temp.name).profile()["cardio_goal"]
        self.assertEqual(goal, {"moderate": 60, "high": 30})
        for moderate, high in [(120, 0), (0, 60), (60, 30)]:
            entries = [
                {"kind": "cardio", **self.cardio(moderate, "moderate")},
                {"kind": "cardio", **self.cardio(high, "high")},
                {"kind": "cardio", **self.cardio(900), "date": "2026-11-22"},
                {"kind": "cardio", **self.cardio(900), "date": "2026-11-15"},
            ]
            result = weekly_cardio(entries, goal, date(2026, 11, 18), date(2026, 11, 19))
            self.assertEqual(result["percent"], 100)
            self.assertEqual(result["target"], 120)
            self.assertEqual(result["minutes"], moderate + high)
        self.assertEqual(
            weekly_cardio(
                [{"kind": "cardio", **self.cardio(80, "moderate")}],
                {"moderate": 0, "high": 30},
                date(2026, 11, 18),
                date(2026, 11, 19),
            )["value"],
            80,
        )
        self.assertIsNone(
            weekly_cardio([], {"moderate": 0, "high": 0}, date(2026, 11, 18), date(2026, 11, 19))[
                "percent"
            ]
        )

    def test_invalid_cardio_and_goals_do_not_persist(self):
        for changes in [
            {"minutes": 0},
            {"minutes": True},
            {"minutes": float("nan")},
            {"minutes": 1441},
            {"intensity": "low"},
            {"activity": "Invented"},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.store.save("cardio", {**self.cardio(), **changes})
        before = self.store.profile()
        for goal in [{"moderate": -1, "high": 0}, {"moderate": 0, "high": True}, None]:
            with self.assertRaises(ValueError):
                self.store.save_profile({"cardio_goal": goal, "name": "Do not save"})
            self.assertEqual(self.store.profile(), before)
        self.assertEqual(self.store.entries(), [])
        activities = [name for group in ACTIVITIES.values() for name in group]
        self.assertGreater(len(activities), 40)
        for name in ["Badminton", "Swimming", "Pickleball", "Cycling", "Running"]:
            self.assertIn(name, activities)

    def meal(self):
        return {
            "date": DAY,
            "description": "Synthetic foods",
            "protein": 15,
            "calories": 250,
            "items": [
                {"name": "Food A", "portion": "1 portion", "protein": 10, "calories": 150},
                {"name": "Food B", "portion": "1 portion", "protein": 5, "calories": 100},
            ],
        }

    def test_calories_validate_totals_and_preserve_unknown_legacy_meals(self):
        entry = self.store.save("meal", self.meal())
        self.assertEqual(Store(self.temp.name).entries()[0]["calories"], 250)
        for value in [-1, True, float("inf"), 10001]:
            with self.assertRaises(ValueError):
                validate("meal", {**self.meal(), "calories": value})
        with self.assertRaisesRegex(ValueError, "calorie estimates do not add up"):
            validate("meal", {**self.meal(), "calories": 999})
        legacy = self.store.save("meal", {"date": DAY, "description": "Older food", "protein": 5})
        self.assertNotIn("calories", legacy)
        stats = insights(self.store.entries(), self.store.profile(), date(2026, 11, 19))
        self.assertEqual(stats["daily"][DAY]["calories"], entry["calories"])
        self.assertEqual(stats["daily"][DAY]["calorie_meals"], 1)

    def test_ai_cardio_and_meals_require_approval_and_keep_both_nutrients(self):
        coach = Coach(self.store, Connections(Path(self.temp.name)))
        for kind, data in [("cardio", self.cardio()), ("meal", self.meal())]:
            reply = {"action": kind, "message": "Review", "proposal": data, "calculation": "10+5"}
            with patch.object(coach, "generate", return_value=copy.deepcopy(reply)):
                result = coach.chat("Log my " + kind, True, DAY, logging_kind=kind)
            self.assertIn("draft", result)
            self.assertEqual(self.store.entries(), [])
            self.assertIn("250 kcal" if kind == "meal" else "Badminton: 30 min", result["text"])
            self.store.dismiss(result["draft"]["id"])
        bad = self.meal()
        bad.pop("calories")
        with patch.object(
            coach,
            "generate",
            return_value={
                "action": "meal",
                "message": "Review",
                "proposal": bad,
                "calculation": "10+5",
            },
        ):
            result = coach.chat("Log my meal", True, DAY)
        self.assertNotIn("draft", result)
        self.assertIn("calories", " ".join(result["notices"]))

    def test_local_model_computes_protein_and_calories_from_separate_expressions(self):
        import json

        data = {
            "action": "meal",
            "message": "Review",
            "proposal": {
                "date": DAY,
                "description": "Synthetic foods",
                "items": [
                    {
                        "name": "Food A",
                        "portion": "2 portions",
                        "calculation": "2*10",
                        "calorie_calculation": "2*150",
                        "notes": "Assumed portions",
                    },
                    {
                        "name": "Food B",
                        "portion": "1 portion",
                        "calculation": "5",
                        "calorie_calculation": "100",
                        "notes": "Label",
                    },
                ],
            },
        }
        response = {
            "message": {"content": json.dumps(data)},
            "done_reason": "stop",
            "prompt_eval_count": 100,
        }
        with patch("fitness_tracker.local_model.request", side_effect=[{}, response]):
            result, _ = generate(
                [{"role": "system", "content": "Meal: estimate both nutrients."}],
                "qwen3:8b",
                {},
                5000,
                direct=True,
                response_kind="meal",
            )
        self.assertEqual(result["proposal"]["protein"], 25)
        self.assertEqual(result["proposal"]["calories"], 400)
        self.assertEqual(validate("meal", result["proposal"])["items"][0]["calories"], 300)
        item_schema = response_schema(meal=True)["properties"]["proposal"]["properties"]["items"][
            "items"
        ]
        self.assertIn("calorie_calculation", item_schema["required"])
