import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from fitness_tracker.anatomy import (
    BODY_PARTS,
    REVERSE_CURL_IDS,
    SECONDARY_MUSCLE_ADDITIONS,
    classify,
)
from fitness_tracker.store import EXERCISES, Store, insights


class TrainingGroupsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def save(self, items, day=None):
        return self.store.save(
            "workout",
            {
                "date": day or date.today().isoformat(),
                "exercises": [
                    {
                        "exercise_id": exercise,
                        "sets": [
                            {
                                "weight": 0,
                                "reps": 0 if exercise == "Plank" else 10,
                                "seconds": 45 if exercise == "Plank" else 0,
                            }
                            for _ in range(count)
                        ],
                    }
                    for exercise, count in items
                ],
            },
        )

    def test_reverse_curls_tally_forearms_and_keep_biceps_as_assisting(self):
        for exercise_id in REVERSE_CURL_IDS:
            self.assertEqual(EXERCISES[exercise_id]["primaryMuscles"], ["forearms"])
            self.assertIn("biceps", EXERCISES[exercise_id]["secondaryMuscles"])
        self.save([("Reverse_Cable_Curl", 2), ("Barbell_Curl", 3)])
        result = insights(self.store.entries(), self.store.profile())
        self.assertEqual(result["body_parts"], {"Forearms": 2, "Biceps": 3})
        self.assertEqual(result["area_details"]["Forearms"]["areas"], {"Reverse curls": 2})

    def test_catalog_has_mapped_primary_and_known_assisting_muscles(self):
        for exercise in EXERCISES.values():
            with self.subTest(exercise=exercise["id"]):
                self.assertTrue(exercise["primaryMuscles"])
                self.assertTrue(exercise["bodyParts"])
                for muscle in exercise["primaryMuscles"] + exercise["secondaryMuscles"]:
                    self.assertIn(muscle, BODY_PARTS)

    def test_reviewed_assisting_groups_preserve_existing_mappings(self):
        for identifier, additions in SECONDARY_MUSCLE_ADDITIONS.items():
            with self.subTest(exercise=identifier):
                self.assertTrue(set(additions) <= set(EXERCISES[identifier]["secondaryMuscles"]))
        original = {
            "id": "Butterfly",
            "primaryMuscles": ["chest"],
            "secondaryMuscles": ["biceps"],
        }
        mapped = classify(original)
        self.assertEqual(mapped["primaryMuscles"], ["chest"])
        self.assertEqual(mapped["secondaryMuscles"], ["biceps", "shoulders"])
        self.assertEqual(classify(mapped), mapped)
        self.assertEqual(original["secondaryMuscles"], ["biceps"])
        self.assertEqual(EXERCISES["Triceps_Pushdown"]["secondaryMuscles"], [])

    def test_flys_and_crossovers_count_as_primary_chest_alongside_presses(self):
        self.save(
            [
                ("Pushups", 1),
                ("Barbell_Bench_Press_-_Medium_Grip", 3),
                ("Low_Cable_Crossover", 2),
                ("Butterfly", 2),
            ]
        )
        result = insights(self.store.entries(), self.store.profile())
        self.assertEqual(result["body_parts"]["Chest"], 8)
        self.assertEqual(
            result["area_details"]["Chest"]["exercises"],
            {
                "Pushups": 1,
                "Barbell_Bench_Press_-_Medium_Grip": 3,
                "Low_Cable_Crossover": 2,
                "Butterfly": 2,
            },
        )

    def test_high_level_groups_keep_area_detail(self):
        self.save(
            [
                ("Leg_Press", 3),
                ("Lying_Leg_Curls", 2),
                ("Plank", 1),
                ("Flat_Bench_Lying_Leg_Raise", 2),
                ("Incline_Dumbbell_Press", 2),
                ("Barbell_Bench_Press_-_Medium_Grip", 3),
            ]
        )
        result = insights(self.store.entries(), self.store.profile())
        self.assertEqual(result["body_parts"], {"Quads": 3, "Hamstrings": 2, "Abs": 3, "Chest": 5})
        self.assertEqual(result["area_details"]["Quads"]["areas"], {"Quads": 3})
        self.assertEqual(result["area_details"]["Hamstrings"]["areas"], {"Hamstrings": 2})
        self.assertEqual(
            result["area_details"]["Chest"]["areas"],
            {"Incline movements": 2, "Flat / general chest": 3},
        )
        self.assertEqual(
            result["area_details"]["Abs"]["areas"],
            {"Holds / stability": 1, "Leg / knee raises & reverse crunches": 2},
        )
        self.assertNotIn("abdominals", result["body_parts"])
        self.assertNotIn("quadriceps", result["body_parts"])

    def test_same_body_part_is_not_double_counted(self):
        exercise = classify(
            {
                "id": "test_abs",
                "name": "Test abs",
                "primaryMuscles": ["upper abs", "lower abs", "abdominals"],
                "secondaryMuscles": [],
            }
        )
        self.assertEqual(exercise["bodyParts"], ["Abs"])
        with patch.dict(EXERCISES, {"test_abs": exercise}):
            self.save([("test_abs", 3)])
            result = insights(self.store.entries(), self.store.profile())
        self.assertEqual(result["body_parts"], {"Abs": 3})

    def test_old_and_future_workouts_do_not_enter_current_focus(self):
        self.save([("Reverse_Cable_Curl", 3)], (date.today() - timedelta(days=28)).isoformat())
        self.save([("Leg_Press", 3)], (date.today() + timedelta(days=1)).isoformat())
        result = insights(self.store.entries(), self.store.profile())
        self.assertEqual(result["body_parts"], {})
        self.assertEqual(result["area_details"], {})
