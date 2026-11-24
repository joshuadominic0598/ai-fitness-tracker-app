import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.coach import Coach, Connections
from fitness_tracker.local_model import response_schema
from fitness_tracker.meal_estimate import normalize_meal_estimate
from fitness_tracker.store import Store

DAY = "2026-11-23"


def estimate(**changes):
    return {
        "date": DAY,
        "description": "Mutton biryani, chicken with chapathis, and a small bowl of plain noodles across three meals.",
        "protein": 85,
        "low": 65,
        "high": 110,
        "calories": 2200,
        **changes,
    }


class MealEstimateTests(unittest.TestCase):
    def test_requested_schema_has_only_whole_meal_fields(self):
        properties = response_schema(meal=True)["properties"]["proposal"]["properties"]
        self.assertEqual(
            set(properties), {"date", "description", "protein", "low", "high", "calories"}
        )

    def test_uncertain_meals_persist_without_item_ledger_or_calculator(self):
        samples = [
            (
                "Went to a party, had prawns tofu, chicken and parotha; quantities unsure but filled my stomach.",
                estimate(
                    description="A filling party meal of prawns, tofu, chicken and parotha; portions are estimated.",
                    protein=60,
                    low=35,
                    high=90,
                    calories=1400,
                ),
            ),
            (
                "Had 3 meals: full bowl mutton biryani with 4 medium boneless mutton pieces; 3 medium bone-in chicken pieces with 3 chapathis; a small bowl of plain packet noodles.",
                estimate(),
            ),
        ]
        for source, data in samples:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as tmp:
                store = Store(tmp)
                coach = Coach(store, Connections(Path(tmp)))
                # The obsolete expression and ingredient split cannot reject a useful total.
                payload = {
                    "action": "meal",
                    "message": "Review",
                    "proposal": {
                        **data,
                        "items": [{"name": "Wrong old detail", "protein": 999}],
                        "calculation": "1+1",
                    },
                    "calculation": "1+1",
                }
                with (
                    patch.object(coach, "generate", return_value=payload) as model,
                    patch(
                        "fitness_tracker.agent_tools.calculator",
                        side_effect=AssertionError("No calculator needed"),
                    ),
                ):
                    result = coach.chat(
                        "Log my food for " + DAY + ". I ate: " + source,
                        True,
                        DAY,
                        logging_kind="meal",
                    )
                self.assertEqual(model.call_count, 1)
                self.assertEqual(result["draft"]["data"], {**data, "source": "ai", "notes": ""})
                self.assertNotIn("Wrong old detail", result["text"])
                self.assertIn("kcal", result["text"])
                self.assertIn("range", result["text"])
                self.assertNotIn("1.", result["text"])
                self.assertEqual(store.entries(), [])
                saved = store.approve(result["draft"]["id"])
                self.assertEqual(saved["protein"], data["protein"])
                self.assertEqual(saved["calories"], data["calories"])
                self.assertNotIn("items", saved)

    def test_range_order_edges_and_missing_range_are_normalized(self):
        for raw in [
            estimate(low=110, high=65),
            estimate(protein=200),
            estimate(protein=65),
            estimate(low=85, high=85),
            estimate(low=None, high=None),
        ]:
            with self.subTest(raw=raw):
                data = normalize_meal_estimate(raw, DAY)
                self.assertLess(data["low"], data["protein"])
                self.assertLess(data["protein"], data["high"])
                self.assertEqual(data["calories"], 2200)

    def test_incomplete_estimate_is_completed_once_without_blocking_over_portions(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            coach = Coach(store, Connections(Path(tmp)))
            with patch.object(
                coach,
                "generate",
                side_effect=[
                    {"action": "meal", "message": "Review", "proposal": estimate(calories=None)},
                    {"action": "meal", "message": "Review", "proposal": estimate()},
                ],
            ) as model:
                result = coach.chat(
                    "Log my food: a full bowl of biryani, quantity unsure",
                    True,
                    DAY,
                    logging_kind="meal",
                )
            self.assertEqual(model.call_count, 2)
            self.assertEqual(result["draft"]["data"]["calories"], 2200)
            self.assertEqual(store.entries(), [])

    def test_mixed_log_keeps_totals_without_calculation_for_each_meal(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            coach = Coach(store, Connections(Path(tmp)))
            reply = {
                "action": "batch",
                "message": "Review",
                "proposal": {
                    "entries": [
                        {"kind": "meal", "data": estimate()},
                        {"kind": "creatine", "data": {"date": DAY, "amount": 3, "unit": "g"}},
                    ]
                },
            }
            with patch.object(coach, "generate", return_value=reply):
                result = coach.chat("Log my food: biryani and chicken; also 3g creatine", True, DAY)
            entries = result["draft"]["data"]["entries"]
            self.assertEqual(entries[0]["data"]["calories"], 2200)
            self.assertEqual(entries[1]["data"]["amount"], 3)
            self.assertNotIn("items", entries[0]["data"])
