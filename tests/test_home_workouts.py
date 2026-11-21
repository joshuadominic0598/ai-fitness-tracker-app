import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.chat_actions import requested_log_kind
from fitness_tracker.coach import Coach, Connections
from fitness_tracker.coach_workflow import scope_statistics
from fitness_tracker.consistency import consistency
from fitness_tracker.semantic_index import SemanticIndex, scope_for
from fitness_tracker.store import CATALOG, Store, insights, validate

DAY = "2026-11-21"


def session(exercise="Pushups", reps=10, weight=0, day=DAY):
    return {
        "date": day,
        "exercises": [
            {
                "exercise_id": exercise,
                "tracking": "reps",
                "load_mode": "weighted" if weight else "bodyweight",
                "sets": [{"weight": weight, "reps": reps, "seconds": 0}],
            }
        ],
    }


class HomeWorkoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def test_multiple_home_sessions_never_replace_gym_or_each_other(self):
        gym = self.store.save("workout", session())
        first = self.store.save("home_workout", session("Sit-Up", 20))
        second = self.store.save("home_workout", session("Dumbbell_Bicep_Curl", 10, 5))
        self.assertEqual(len({gym["id"], first["id"], second["id"]}), 3)
        reopened = Store(self.temp.name)
        self.assertEqual(len(reopened.entries()), 3)
        revised = reopened.save("home_workout", session("Sit-Up", 25), first["id"])
        self.assertEqual(revised["exercises"][0]["sets"][0]["reps"], 25)
        self.assertEqual(next(e for e in reopened.entries() if e["id"] == gym["id"]), gym)
        reopened.delete(first["id"])
        self.assertEqual({e["id"] for e in reopened.entries()}, {gym["id"], second["id"]})
        with self.assertRaisesRegex(ValueError, "own category"):
            reopened.save("home_workout", session(), gym["id"])
        self.assertEqual(next(e for e in reopened.entries() if e["id"] == gym["id"]), gym)

    def test_home_sets_count_for_training_records_but_not_gym_or_cardio(self):
        home = self.store.save("home_workout", session("Dumbbell_Bicep_Curl", 10, 5))
        stats = insights([home], self.store.profile(), date(2026, 11, 21))
        self.assertEqual(stats["workouts"], 0)
        self.assertEqual(stats["weekly_days"], [])
        self.assertEqual(stats["home_workouts"], 1)
        self.assertEqual(stats["daily"][DAY]["home_workouts"], 1)
        self.assertEqual(stats["daily"][DAY]["workouts"], 0)
        self.assertEqual(stats["daily"][DAY]["sets"], 1)
        self.assertEqual(stats["body_parts"]["Biceps"], 1)
        self.assertEqual(stats["prs"]["Dumbbell_Bicep_Curl"]["weight"], 5)
        self.assertEqual(stats["frequency"]["Dumbbell_Bicep_Curl"], 1)
        self.assertEqual(stats["cardio_week"]["minutes"], 0)
        self.assertIsNone(stats["consistency"]["categories"]["exercise"]["score"])
        future = {**home, "date": "2026-11-22"}
        self.assertEqual(insights([future], self.store.profile(), date(2026, 11, 21))["prs"], {})

    def test_gym_score_unchanged_by_home_workouts_and_scoped_totals_distinguish_them(self):
        gym = self.store.save("workout", session(day="2026-11-18"))
        home = self.store.save("home_workout", session("Sit-Up", 20))
        profile = self.store.profile()
        before = consistency([gym], profile, date(2026, 11, 21))
        after = consistency([gym, home], profile, date(2026, 11, 21))
        self.assertEqual(before, after)
        stats = scope_statistics([gym, home])
        self.assertEqual(
            (stats["gym_days"], stats["home_workout_days"], stats["workout_sets"]), (1, 1, 2)
        )
        self.assertEqual(
            scope_for("Review my home workouts", date(2026, 11, 21))["kinds"], ["home_workout"]
        )
        self.assertEqual(
            scope_for("Review my gym workouts", date(2026, 11, 21))["kinds"], ["workout"]
        )

    def test_home_approval_adds_sessions_and_keeps_gym_previews_independent(self):
        gym = self.store.save("workout", session())
        pending_gym = self.store.draft("workout", session(reps=12))
        for data in [session("Sit-Up", 20), session("Dumbbell_Bicep_Curl", 10, 5)]:
            draft = self.store.draft("home_workout", data)
            saved = self.store.approve(draft["id"])
            self.assertEqual(saved["kind"], "home_workout")
        self.assertEqual(len(self.store.entries()), 3)
        self.assertIn(pending_gym["id"], {d["id"] for d in self.store.drafts()})
        self.assertEqual(next(e for e in self.store.entries() if e["kind"] == "workout"), gym)

    def test_cardio_exercises_are_rejected_and_strength_tracking_modes_remain_available(self):
        cardio = next(e for e in CATALOG if e.get("category") == "cardio")
        with self.assertRaisesRegex(ValueError, "separately in Cardio"):
            validate("home_workout", session(cardio["id"]))
        for exercise, reps, weight in [
            ("Pushups", 10, 0),
            ("Sit-Up", 20, 0),
            ("Dumbbell_Shoulder_Press", 10, 5),
        ]:
            self.assertEqual(
                validate("home_workout", session(exercise, reps, weight))["exercises"][0]["sets"][
                    0
                ]["weight"],
                weight,
            )
        timed = session("Plank")
        timed["exercises"][0].update(
            tracking="time", sets=[{"weight": 0, "reps": 0, "seconds": 30}]
        )
        self.assertEqual(validate("home_workout", timed)["exercises"][0]["tracking"], "time")

    def test_ai_home_preview_and_approval_never_turn_into_gym_sessions(self):
        gym = self.store.save("workout", session(day="2026-11-18"))
        coach = Coach(self.store, Connections(Path(self.temp.name)))
        with patch.object(coach, "generate") as model:
            result = coach.chat(
                "Log my home workout: Pushups 10 reps bodyweight",
                True,
                DAY,
                logging_kind="home_workout",
            )
        model.assert_not_called()
        self.assertEqual(result["draft"]["kind"], "home_workout")
        self.assertIn("not a gym day", result["text"])
        self.assertEqual(self.store.entries(), [gym])
        saved = coach.chat("I approve", True, DAY)
        self.assertEqual(saved["approved"]["entries"][0]["kind"], "home_workout")
        self.assertEqual(len(self.store.entries()), 2)
        self.assertEqual(requested_log_kind("Log 10 pushups at home"), "home_workout")
        index = SemanticIndex(self.store, coach.connections.effective)
        with patch.object(index, "search", return_value=[]):
            self.assertTrue(index.search_exercises("pushups", tracked=True))

    def test_home_shorthand_preserves_pushups_situps_and_dumbbell_quantities(self):
        from fitness_tracker.workout_notes import inventory

        short = inventory("Log my home workout: 10 pushups and 20 situps")
        self.assertEqual(
            [(g["candidates"][0], g["sets"][0]["reps"]) for g in short["groups"]],
            [("Pushups", 10), ("Sit-Up", 20)],
        )
        weighted = inventory("Home workout: dumbbell bicep curl 5kg 10 reps")
        self.assertEqual(weighted["groups"][0]["candidates"][0], "Dumbbell_Bicep_Curl")
        self.assertEqual(weighted["groups"][0]["sets"][0]["weight"], 5)
        self.assertEqual(weighted["groups"][0]["sets"][0]["reps"], 10)
        coach = Coach(self.store, Connections(Path(self.temp.name)))
        with patch.object(coach, "generate") as model:
            result = coach.chat("Log my home workout: 10 pushups and 20 situps", True, DAY)
        model.assert_not_called()
        self.assertEqual(result["draft"]["kind"], "home_workout")
        self.assertEqual(len(result["draft"]["data"]["exercises"]), 2)
