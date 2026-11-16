import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.chat_actions import draft_message
from fitness_tracker.coach import Coach, Connections
from fitness_tracker.store import Store, validate


def meal():
    return {
        "date": "2026-02-01",
        "description": "Food A, Food B and topping",
        "protein": 15,
        "low": 13,
        "high": 17,
        "notes": "Synthetic portion assumptions.",
        "items": [
            {"name": "Food A", "portion": "100 g cooked", "protein": 4},
            {"name": "Food B", "portion": "1 piece", "protein": 5},
            {"name": "Topping", "portion": "20 g", "protein": 6, "notes": "Assumed type."},
        ],
    }


class MealBreakdownTests(unittest.TestCase):
    def test_qwen_prints_persists_and_revises_each_item_before_approval(self):
        for provider in ("ollama",):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                store = Store(tmp)
                connections = Connections(Path(tmp))
                connections.save({"provider": provider, provider + "_key": "synthetic"})
                coach = Coach(store, connections)

                def payload(data, calculation):
                    return {
                        "action": "meal",
                        "message": "Review",
                        "proposal": data,
                        "calculation": calculation,
                    }

                with patch(
                    "fitness_tracker.coach.Coach.generate", return_value=payload(meal(), "4+5+6")
                ) as request:
                    result = coach.chat("Log my meal for 2026-02-01", True, "2026-02-01")
                self.assertIn(
                    "items:[{name,portion,protein,notes}]", str(request.call_args.args[0])
                )
                for food in meal()["items"]:
                    self.assertIn(
                        f"{food['name']} ({food['portion']}): ≈{food['protein']} g protein",
                        result["text"],
                    )
                self.assertIn("Total: ≈15 g protein", result["text"])
                self.assertIn("Assumed type.", result["text"])
                self.assertEqual(store.entries(), [])
                changed = copy.deepcopy(meal())
                changed.update(protein=18, low=16, high=20)
                changed["items"][2]["protein"] = 9
                with patch(
                    "fitness_tracker.coach.Coach.generate", return_value=payload(changed, "4+5+9")
                ):
                    revision = coach.chat("Change the topping estimate to 9g protein", True)
                self.assertEqual(len(store.drafts()), 1)
                self.assertEqual(
                    revision["draft"]["data"]["items"][:2], result["draft"]["data"]["items"][:2]
                )
                self.assertIn("Total: ≈18 g protein", revision["text"])
                saved = store.approve(revision["draft"]["id"])
                self.assertEqual(saved["items"], revision["draft"]["data"]["items"])

    def test_inconsistent_or_malformed_item_breakdown_is_rejected(self):
        data = meal()
        data["items"][0]["protein"] = 40
        with self.assertRaisesRegex(ValueError, "do not add up"):
            validate("meal", data)
        for items in ([], "food", [None], [{"name": "Food", "protein": 15}]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                validate("meal", {**meal(), "items": items})

    def test_rounded_totals_and_legacy_entries_remain_supported(self):
        data = meal()
        data["items"][0]["protein"] = 4.2
        self.assertEqual(validate("meal", data)["protein"], 15)
        legacy = meal()
        legacy.pop("items")
        clean = validate("meal", legacy)
        self.assertNotIn("items", clean)
        self.assertIn(
            "Synthetic portion assumptions.", draft_message({"kind": "meal", "data": clean})
        )
