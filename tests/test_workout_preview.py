import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.coach import Coach, Connections, ProviderError
from fitness_tracker.exercise_matching import rank_exercises
from fitness_tracker.store import EXERCISES, Store
from fitness_tracker.workout_notes import inventory

SCREENSHOT_NOTE = """Log my workout for 2026-11-16. Keep every exercise and set; ask me if anything is unclear. Here is what I did:
warm up 8 pushups
1. tricep pushdown 15kg 7 reps then 6 reps
2. tricep single arm cable pulldown 5kg 6 reps and then 2.5kg 8 reps,
3. then tripcep both arm rope pushdown 1 set 7.5kg 8 reps.
4. Bench press 50kg 8 reps, 50kg 6 reps, 10kg 12reps.
5. low cable fly push upward cable machine 5kg (2.5 either side) 2 sets - did like 12 reps 10 reps.
6. then chest fly machine 10kg 4 reps, 7.5kg 3 reps.
7. then legpress 100kg - 20 reps, 15 reps"""

MOVEMENTS = [
    "Barbell_Squat",
    "Romanian_Deadlift",
    "Goblet_Squat",
    "Barbell_Hip_Thrust",
    "Dumbbell_Shoulder_Press",
    "Seated_Cable_Rows",
    "Leg_Press",
    "Leg_Extensions",
    "Lying_Leg_Curls",
    "Hammer_Curls",
    "Standing_Biceps_Cable_Curl",
    "Front_Dumbbell_Raise",
    "Side_Lateral_Raise",
    "Cable_Rear_Delt_Fly",
    "Reverse_Barbell_Curl",
    "Butterfly",
    "Low_Cable_Crossover",
    "Triceps_Pushdown",
    "Cable_One_Arm_Tricep_Extension",
    "Cable_Rope_Overhead_Triceps_Extension",
    "Dumbbell_Bench_Press",
    "Incline_Dumbbell_Press",
    "Dumbbell_Floor_Press",
    "Dumbbell_Shrug",
    "Barbell_Curl",
    "Concentration_Curls",
    "Dumbbell_Lunges",
    "Standing_Calf_Raises",
    "Ab_Crunch_Machine",
    "Bent_Over_Barbell_Row",
]


class WorkoutPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.connections = Connections(Path(self.tmp.name))
        self.connections.save({})
        self.coach = Coach(self.store, self.connections)

    def test_screenshot_survives_invalid_ids_and_wrong_model_quantities(self):
        reply = {
            "action": "workout",
            "proposal": {
                "exercises": [
                    {"exercise_id": "not_in_library", "sets": [{"weight": 999, "reps": 1}]}
                ]
            },
        }
        with patch.object(self.coach, "generate", return_value=reply) as generate:
            result = self.coach.chat(SCREENSHOT_NOTE, True, "2026-11-15")
        self.assertEqual(generate.call_count, 2)
        data = result["draft"]["data"]
        self.assertEqual(data["date"], "2026-11-16")
        self.assertEqual(
            [e["exercise_id"] for e in data["exercises"]],
            [
                "Pushups",
                "Triceps_Pushdown",
                "Cable_One_Arm_Tricep_Extension",
                "Triceps_Pushdown_-_Rope_Attachment",
                "Barbell_Bench_Press_-_Medium_Grip",
                "Low_Cable_Crossover",
                "Butterfly",
                "Leg_Press",
            ],
        )
        self.assertEqual(
            [[(s["weight"], s["reps"]) for s in e["sets"]] for e in data["exercises"]],
            [
                [(0, 8)],
                [(15, 7), (15, 6)],
                [(5, 6), (2.5, 8)],
                [(7.5, 8)],
                [(50, 8), (50, 6), (10, 12)],
                [(5, 12), (5, 10)],
                [(10, 4), (7.5, 3)],
                [(100, 20), (100, 15)],
            ],
        )
        self.assertNotIn("workout_incomplete", result)
        self.assertEqual(self.store.entries(), [])
        self.assertEqual(result["text"].count("   Set "), 15)

    def test_ten_twenty_thirty_movements_have_bounded_batches_and_one_preview(self):
        for count in (10, 20, 30):
            with self.subTest(count=count):
                note = "Log my workout:\n" + "\n".join(
                    f"{EXERCISES[eid]['name']} 10kg 8 reps then 8 reps" for eid in MOVEMENTS[:count]
                )
                with patch.object(
                    self.coach, "generate", side_effect=ProviderError("HTTP 503")
                ) as generate:
                    result = self.coach.chat(note, True, "2026-11-16")
                self.assertEqual(generate.call_count, count // 5)
                self.assertEqual(len(result["draft"]["data"]["exercises"]), count)
                self.assertEqual(
                    sum(len(e["sets"]) for e in result["draft"]["data"]["exercises"]), count * 2
                )
                for call in generate.call_args_list:
                    summary = json.loads(
                        call.args[0][0]["content"].split("EXPLICIT SET INVENTORY:")[1]
                    )
                    self.assertLessEqual(len(summary), 5)
                self.assertEqual(self.store.entries(), [])

    def test_failed_middle_batch_does_not_discard_successes(self):
        note = "Log my workout:\n" + "\n".join(
            f"{EXERCISES[eid]['name']} 10kg 8 reps" for eid in MOVEMENTS[:15]
        )
        with patch.object(
            self.coach,
            "generate",
            side_effect=[
                {"action": "clarify", "proposal": None},
                ProviderError("offline"),
                {"action": "workout", "proposal": {"exercises": []}},
            ],
        ):
            result = self.coach.chat(note, True, "2026-11-16")
        self.assertEqual(len(result["draft"]["data"]["exercises"]), 15)
        self.assertTrue(result["notices"])

    def test_unmatched_and_missing_quantities_are_visible_beside_valid_sets(self):
        note = "Log my workout:\nHammer curl 10kg 8 reps\nMystery zorble machine 12kg 9 reps\nBench press 20kg"
        with patch.object(self.coach, "generate", side_effect=ProviderError("offline")):
            result = self.coach.chat(note, True, "2026-11-16")
        self.assertTrue(result["workout_incomplete"])
        self.assertEqual(len(result["draft"]["data"]["exercises"]), 1)
        self.assertIn("Mystery zorble machine 12kg 9 reps", result["text"])
        self.assertIn("Bench press 20kg", result["text"])
        self.assertIn("Partial workout preview", result["text"])
        self.assertEqual(self.store.entries(), [])

    def test_entirely_unknown_workout_still_shows_a_source_preview(self):
        with patch.object(self.coach, "generate") as generate:
            result = self.coach.chat("Log my workout:\nZorble wobble 10kg 8 reps", True)
        generate.assert_not_called()
        self.assertEqual(result["action"], "clarify")
        self.assertIn("Workout preview", result["text"])
        self.assertIn("Zorble wobble 10kg 8 reps", result["text"])
        self.assertNotIn("draft", result)

    def test_equipment_variations_and_timed_sets_stay_separate(self):
        note = "Log my workout:\nBench press 20kg 8 reps\nDumbbell bench press 10kg 8 reps\nMachine chest fly 15kg 8 reps\nDumbbell fly 5kg 10 reps\nPlank 45 seconds"
        with patch.object(self.coach, "generate", side_effect=ProviderError("offline")):
            result = self.coach.chat(note, True)
        exercises = result["draft"]["data"]["exercises"]
        self.assertEqual(len(exercises), 5)
        self.assertEqual(exercises[-1]["tracking"], "time")
        self.assertEqual(exercises[-1]["sets"], [{"weight": 0, "reps": 0, "seconds": 45}])

    def test_fuzzy_matching_uses_names_aliases_and_movement_equipment(self):
        for query, expected in [
            ("dumbell shoulder press", "Dumbbell_Shoulder_Press"),
            ("pec deck", "Butterfly"),
            ("legpress", "Leg_Press"),
            ("seated row", "Seated_Cable_Rows"),
        ]:
            self.assertEqual(rank_exercises(query)[0], expected)
        self.assertNotIn("Dumbbell_Bench_Press", rank_exercises("dumbell shoulder press"))
        self.assertEqual(rank_exercises("zorble wobble machine"), [])

    def test_repeated_equal_sets_and_continuations_survive(self):
        source = inventory(
            "Dumbbell shoulder press 12kg 8 reps\nThen 12kg 8 reps\nDumbbell shoulder press 12kg 8 reps"
        )
        self.assertEqual(len(source["groups"]), 1)
        self.assertEqual(len(source["groups"][0]["sets"]), 3)

    def test_missing_reps_answer_completes_the_same_preview(self):
        with patch.object(self.coach, "generate", side_effect=ProviderError("offline")):
            partial = self.coach.chat(
                "Log my workout:\nHammer curl 10kg 8 reps\nBench press 20kg", True, "2026-11-15"
            )
            corrected = self.coach.chat("Bench press was 6 reps", True, "2026-11-16")
        self.assertNotIn("workout_incomplete", corrected)
        self.assertEqual(corrected["draft"]["data"]["date"], "2026-11-15")
        self.assertEqual(corrected["draft"]["data"]["exercises"][-1]["sets"][0]["reps"], 6)
        self.assertNotEqual(corrected["draft"]["id"], partial["draft"]["id"])
        self.assertEqual(len(self.store.drafts()), 1)
        self.assertEqual(self.store.entries(), [])

    def test_unrelated_question_does_not_rewrite_a_partial_workout(self):
        with patch.object(self.coach, "generate", side_effect=ProviderError("offline")):
            self.coach.chat("Log my workout:\nHammer curl 10kg 8 reps\nBench press 20kg", True)
        with patch.object(
            self.coach,
            "generate",
            return_value={
                "action": "answer",
                "message": "A plate is a machine setting.",
                "proposal": None,
            },
        ):
            answer = self.coach.chat("What is a machine plate?", True)
        self.assertNotIn("draft", answer)
        self.assertEqual(len(self.store.drafts()), 1)

    def test_small_input_budget_subdivides_batches_without_losing_sets(self):
        self.connections.save({"context_budget_tokens": 2500})
        note = "Log my workout:\n" + "\n".join(
            f"{EXERCISES[eid]['name']} 10kg 8 reps" for eid in MOVEMENTS[:10]
        )
        with patch.object(self.coach, "generate", side_effect=ProviderError("offline")):
            result = self.coach.chat(note, True)
        self.assertEqual(len(result["draft"]["data"]["exercises"]), 10)
        self.assertTrue(all(tokens <= 2500 for tokens in result["agent"]["input_token_estimates"]))

    def test_malformed_provider_response_still_produces_source_preview(self):
        with patch.object(self.coach, "generate", return_value=["bad response"]):
            result = self.coach.chat(SCREENSHOT_NOTE, True)
        self.assertEqual(len(result["draft"]["data"]["exercises"]), 8)
        self.assertEqual(self.store.entries(), [])
