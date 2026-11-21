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
            self.assertEqual(revised["items"][:3], original["data"]["items"])
            self.assertEqual(revised["protein"], revised["low"])
            self.assertEqual(revised["protein"], 28.2)
            self.assertIn("400 ml", result["text"])
            self.assertNotIn("14.2", result["text"])
            self.assertEqual(len(store.drafts()), 1)
            self.assertEqual(store.entries(), [])
            coach.chat("I approve", True)
            self.assertEqual(store.entries()[0]["items"], revised["items"])

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
                    "items:[{name,portion,protein,calories,notes}]", str(request.call_args.args[0])
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
