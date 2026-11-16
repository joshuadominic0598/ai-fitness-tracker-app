import tempfile
import unittest
from datetime import date

from fitness_tracker.consistency import consistency
from fitness_tracker.store import Store
from fitness_tracker.supplement_goals import daily_values


class SupplementGoalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_legacy_routine_is_frequency_not_invented_dose(self):
        p = self.store.save_profile({"consistency_supplements": ["Creatine", "Vitamin D"]})
        self.assertEqual(
            p["supplement_goals"]["Vitamin D"],
            {"amount": 1, "measure": "days", "period": 1, "unit": "day"},
        )
        self.assertNotIn("Creatine", p["supplement_goals"])

    def test_custom_persistent_targets_and_preserved_deselection(self):
        self.store.add_supplement("Magnesium")
        target = {"amount": 2, "measure": "capsules", "period": 1, "unit": "day"}
        p = self.store.save_profile(
            {
                "consistency_supplements": ["Creatine", "Magnesium"],
                "supplement_goals": {"magnesium": target},
            }
        )
        self.assertEqual(p["supplement_goals"]["Magnesium"]["measure"], "capsule")
        self.store.save_profile({"consistency_supplements": ["Creatine"], "supplement_goals": {}})
        reopened = Store(self.temp.name).profile()
        self.assertEqual(reopened["supplement_goals"]["Magnesium"]["amount"], 2)
        self.assertEqual(self.store.entries(), [])

    def test_invalid_or_missing_goals_are_atomic(self):
        before = self.store.profile()
        for target in (
            {"amount": 0, "measure": "g", "period": 1, "unit": "day"},
            {"amount": 8, "measure": "days", "period": 1, "unit": "week"},
            {"amount": 1, "measure": "IU", "period": 0, "unit": "day"},
            {"amount": True, "measure": "capsule", "period": 1, "unit": "day"},
        ):
            with self.assertRaises(ValueError):
                self.store.save_profile(
                    {
                        "consistency_supplements": ["Vitamin D"],
                        "supplement_goals": {"Vitamin D": target},
                    }
                )
            self.assertEqual(self.store.profile(), before)
        with self.assertRaises(ValueError):
            self.store.save_profile(
                {"consistency_supplements": ["Vitamin D"], "supplement_goals": {}}
            )
        with self.assertRaises(ValueError):
            self.store.save_profile(
                {
                    "supplement_goals": {
                        "Creatine": {"amount": 5, "measure": "g", "period": 1, "unit": "day"}
                    }
                }
            )

    def test_quantity_conversion_and_frequency_are_distinct(self):
        records = [
            {
                "kind": "supplement",
                "name": "Collagen",
                "date": "2026-11-09",
                "amount": 500,
                "unit": "mg",
            },
            {
                "kind": "supplement",
                "name": "Collagen",
                "date": "2026-11-09",
                "amount": 0.5,
                "unit": "g",
            },
            {
                "kind": "supplement",
                "name": "Collagen",
                "date": "2026-11-09",
                "amount": 1,
                "unit": "capsule",
            },
        ]
        self.assertEqual(daily_values(records, "Collagen", {"measure": "g"}), {"2026-11-09": 1})
        self.assertEqual(daily_values(records, "Collagen", {"measure": "days"}), {"2026-11-09": 1})
        self.assertEqual(daily_values(records, "Collagen", {"measure": "doses"}), {"2026-11-09": 3})
        self.assertEqual(daily_values(records, "Collagen", {"measure": "IU"}), {})

    def test_independent_creatine_and_quantity_based_supplement_scores(self):
        p = self.store.save_profile(
            {
                "consistency_supplements": ["Creatine", "Fish Oil", "Vitamin D"],
                "supplement_goals": {
                    "Fish Oil": {"amount": 2, "measure": "capsule", "period": 1, "unit": "day"},
                    "Vitamin D": {"amount": 3, "measure": "days", "period": 1, "unit": "week"},
                },
            }
        )
        records = [
            {
                "kind": "supplement",
                "name": "Creatine",
                "date": "2026-11-09",
                "amount": 5,
                "unit": "g",
            },
            {
                "kind": "supplement",
                "name": "Fish Oil",
                "date": "2026-11-09",
                "amount": 1,
                "unit": "capsule",
            },
        ]
        result = consistency(records, p, date(2026, 11, 10))
        self.assertEqual(result["categories"]["creatine"]["score"], 100)
        self.assertEqual(result["categories"]["supplements"]["score"], 80)
        self.assertEqual(result["categories"]["supplements"]["attainment"], 50)
        self.assertIsNone(result["categories"]["supplements"]["items"][1]["score"])
        self.assertEqual(result["overall"], 90)
