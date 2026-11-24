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
        "calories": 300,
        "low": 13,
        "high": 17,
        "notes": "Synthetic portion assumptions.",
        "items": [
            {"name": "Food A", "portion": "100 g cooked", "protein": 4, "calories": 100},
            {"name": "Food B", "portion": "1 piece", "protein": 5, "calories": 120},
            {
                "name": "Topping",
                "portion": "20 g",
                "protein": 6,
                "calories": 80,
                "notes": "Assumed type.",
            },
        ],
    }


class MealBreakdownTests(unittest.TestCase):
    def test_revision_retries_commentary_and_saves_only_after_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            coach = Coach(store, Connections(Path(tmp)))
            original = store.draft("meal", {**meal(), "low": 15})
            store.message("assistant", {"draft": original, "text": "Review", "action": "meal"})
            changed = meal()
            changed["items"].append(
                {
                    "name": "Milk",
                    "portion": "400 ml",
                    "protein": 13.2,
                    "calories": 240,
                    "notes": "Assumed dairy milk.",
                }
            )
            changed.update(protein=28.2, low=28.2, high=30.2)
            with patch.object(
                coach,
                "generate",
                side_effect=[
                    {"action": "answer", "message": "Added milk, now 14.2g."},
                    {
                        "action": "meal",
                        "message": "Updated",
                        "proposal": changed,
                        "calculation": "4+5+6+13.2",
                    },
                ],
            ) as model:
                result = coach.chat(
                    "Suggest changes to my pending preview: add 400ml milk and keep it lower range",
                    True,
                    "2026-11-21",
                    revise_draft_id=original["id"],
                )
            self.assertEqual(model.call_count, 2)
            self.assertEqual(model.call_args.kwargs["response_kind"], "meal_revision")
            revised = result["draft"]["data"]
            self.assertEqual(revised["date"], meal()["date"])
            self.assertNotIn("items", revised)
            self.assertLess(revised["low"], revised["protein"])
            self.assertLess(revised["protein"], revised["high"])
            self.assertNotIn("14.2", result["text"])
            self.assertEqual(len(store.drafts()), 1)
            self.assertEqual(store.entries(), [])
            coach.chat("I approve", True)
            self.assertEqual(store.entries()[0]["protein"], revised["protein"])

    def test_unsuccessful_revision_never_claims_the_old_preview_was_updated(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            coach = Coach(store, Connections(Path(tmp)))
            original = store.draft("meal", meal())
            store.message("assistant", {"draft": original, "text": "Review", "action": "meal"})
            with patch.object(
                coach, "generate", return_value={"action": "answer", "message": "Added 400ml milk."}
            ):
                result = coach.chat("Add 400ml milk", True, revise_draft_id=original["id"])
            self.assertEqual(result["action"], "clarify")
            self.assertNotIn("Added 400ml", result["text"])
            self.assertIn("unchanged", result["text"])
            self.assertEqual(result["draft"], original)
            self.assertEqual(store.drafts(), [original])
            self.assertEqual(store.entries(), [])

    def test_explicit_preview_selection_takes_priority_over_active_chat_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            coach = Coach(store, Connections(Path(tmp)))
            selected = store.draft("meal", meal())
            active = store.draft("meal", {**meal(), "date": "2026-11-21"})
            store.coach_state(value={"draft_id": active["id"], "kind": "meal"})
            changed = meal()
            changed.update(protein=18, low=16, high=20)
            changed["items"][2]["protein"] = 9
            with patch.object(
                coach,
                "generate",
                return_value={
                    "action": "meal",
                    "message": "Review",
                    "proposal": changed,
                    "calculation": "4+5+9",
                },
            ) as model:
                result = coach.chat(
                    "Change the topping estimate to 9g protein",
                    True,
                    revise_draft_id=selected["id"],
                )
            self.assertIn(selected["id"], str(model.call_args.args[0]))
            self.assertEqual(result["draft"]["data"]["date"], "2026-02-01")
            self.assertIn(active["id"], [draft["id"] for draft in store.drafts()])
            self.assertNotIn(selected["id"], [draft["id"] for draft in store.drafts()])

    def test_partial_meal_update_preserves_foods_and_other_batch_entries(self):
        from fitness_tracker.coach_workflow import merge_revision

        original = {
            "kind": "batch",
            "data": {
                "entries": [
                    {"kind": "meal", "data": meal()},
                    {
                        "kind": "sleep",
                        "data": {"date": "2026-02-01", "hours": 7, "period": "night"},
                    },
                ]
            },
        }
        patch_data = {
            "date": "2026-02-01",
            "description": "Meal with milk",
            "protein": 13.2,
            "items": [{"name": "Milk", "portion": "400 ml", "protein": 13.2, "calories": 240}],
        }
        result = merge_revision(original, "meal", patch_data, "Add 400ml milk")
        self.assertEqual(result["entries"][1], original["data"]["entries"][1])
        updated = validate("meal", result["entries"][0]["data"])
        self.assertEqual(len(updated["items"]), 4)
        self.assertEqual(updated["protein"], 28.2)

    def test_milk_addition_preserves_existing_food_estimates_and_range(self):
        from fitness_tracker.coach_workflow import merge_revision

        original = meal()
        original.update(protein=13, low=13, high=17)
        original["items"][0]["protein"] = 2
        proposed = meal()
        proposed["items"][1]["protein"] = 3  # Unrequested model drift.
        proposed["items"].append(
            {"name": "Milk", "portion": "400 ml", "protein": 13.2, "calories": 240}
        )
        proposed.update(protein=26.2, low=20, high=27)
        proposed.pop("low")
        proposed.pop("high")
        result = merge_revision(
            {"kind": "meal", "data": original},
            "meal",
            proposed,
            "Suggest changes to my pending preview. Change: add 400ml milk and keep it lower range",
        )
        self.assertEqual(result["items"][:3], original["items"])
        self.assertEqual(result["protein"], 26.2)
        self.assertEqual(result["low"], 26.2)
        self.assertEqual(result["high"], 30.2)

    def test_qwen_revises_whole_meal_totals_before_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            coach = Coach(store, Connections(Path(tmp)))
            with patch.object(
                coach,
                "generate",
                return_value={"action": "meal", "message": "Review", "proposal": meal()},
            ):
                result = coach.chat("Log my meal", True, "2026-02-01")
            self.assertNotIn("items", result["draft"]["data"])
            self.assertNotIn("1.", result["text"])
            changed = {
                "date": "2026-02-01",
                "description": "The meal with extra topping.",
                "protein": 18,
                "low": 16,
                "high": 20,
                "calories": 350,
            }
            with patch.object(
                coach,
                "generate",
                return_value={"action": "meal", "message": "Review", "proposal": changed},
            ):
                revision = coach.chat("Change the meal to include extra topping", True)
            self.assertEqual(len(store.drafts()), 1)
            self.assertEqual(revision["draft"]["data"]["protein"], 18)
            self.assertEqual(store.entries(), [])
            saved = store.approve(revision["draft"]["id"])
            self.assertEqual(saved["calories"], 350)

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
        self.assertIn("Food A, Food B and topping", draft_message({"kind": "meal", "data": clean}))
        self.assertEqual(clean["notes"], "Synthetic portion assumptions.")
