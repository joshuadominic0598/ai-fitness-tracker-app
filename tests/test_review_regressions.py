import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.coach import Coach, Connections
from fitness_tracker.coach_workflow import merge_revision
from fitness_tracker.store import Store

DAY = "2026-11-21"


def meal(items):
    return {
        "date": DAY,
        "description": ", ".join(i["name"] for i in items),
        "items": items,
        "protein": sum(i["protein"] for i in items),
    }


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.connections = Connections(Path(self.temp.name))
        self.coach = Coach(self.store, self.connections)

    def seed(self, data, text="Log my meal"):
        draft = self.store.draft("meal", data)
        user = self.store.message(
            "user", {"text": text, "logging_kind": "meal", "context_date": DAY, "status": "sent"}
        )
        self.store.message("assistant", {"text": "Review", "draft": draft, "action": "meal"})
        return user, draft

    def test_full_source_edit_does_not_inherit_another_pending_revision(self):
        _, unrelated = self.seed(meal([{"name": "Bread", "portion": "1 slice", "protein": 5}]))
        user, target = self.seed(meal([{"name": "Milk", "portion": "200ml", "protein": 6}]))
        self.store.coach_state(value={"draft_id": unrelated["id"], "kind": "meal"})
        with patch.object(
            self.coach,
            "generate",
            return_value={
                "action": "meal",
                "message": "Review",
                "calculation": "12",
                "proposal": {
                    **meal([{"name": "Eggs", "portion": "2", "protein": 12, "calories": 140}]),
                    "calories": 140,
                },
            },
        ):
            result = self.coach.chat(
                "Change my meal to eggs",
                True,
                edit_message_id=user,
                request_id="full-edit-regression",
            )
        self.assertEqual([i["name"] for i in result["draft"]["data"]["items"]], ["Eggs"])
        pending = {d["id"] for d in self.store.drafts()}
        self.assertIn(unrelated["id"], pending)
        self.assertNotIn(target["id"], pending)
        self.assertEqual(self.store.entries(), [])

    def test_named_removals_work_in_single_and_batch_previews(self):
        milk = {"name": "Milk", "portion": "200ml", "protein": 6, "notes": ""}
        bread = {"name": "Bread", "portion": "1 slice", "protein": 5}
        original = {"kind": "meal", "data": meal([milk, bread])}
        for proposed_items in ([milk], [milk, bread]):
            revised = merge_revision(
                original, "meal", meal(proposed_items), "Remove Bread and keep the Milk"
            )
            self.assertEqual(revised["items"], [milk])
            self.assertEqual(revised["protein"], 6)
        unchanged = merge_revision(
            original, "meal", meal([milk]), "Don't remove Bread; change Milk to 200ml"
        )
        self.assertEqual(unchanged["items"], [milk, bread])
        omitted = merge_revision(original, "meal", meal([milk]), "Change Milk to 200ml")
        self.assertEqual(omitted["items"], [milk, bread])
        sleep = {"kind": "sleep", "data": {"date": DAY, "period": "night", "hours": 7}}
        batch = {"kind": "batch", "data": {"entries": [original, sleep]}}
        revised = merge_revision(batch, "meal", meal([milk]), "Remove Bread")
        self.assertEqual(revised["entries"][1], sleep)
        draft = self.store.draft("batch", revised)
        saved = self.store.approve(draft["id"])
        self.assertEqual(next(e for e in saved["entries"] if e["kind"] == "meal")["items"], [milk])
        self.assertEqual(len(saved["entries"]), 2)

    def test_completed_requests_survive_multiple_edits_approval_and_restart(self):
        def answer(weight):
            return {
                "action": "body",
                "message": "Review",
                "proposal": {"date": DAY, "weight_kg": weight},
            }

        with patch.object(self.coach, "generate", return_value=answer(70)):
            first = self.coach.chat(
                "Log my body weight: 70kg", True, DAY, request_id="original-request"
            )
        user_id = self.store.messages()[0]["id"]
        snapshots = [("original-request", "Log my body weight: 70kg", first)]
        for weight, request in [(71, "first-edit-request"), (72, "second-edit-request")]:
            source = f"Log my body weight: {weight}kg"
            with patch.object(self.coach, "generate", return_value=answer(weight)):
                result = self.coach.chat(
                    source, True, DAY, request_id=request, edit_message_id=user_id
                )
            snapshots.append((request, source, result))
        approved = self.coach.chat(
            "I approve",
            True,
            DAY,
            request_id="approval-request",
            approve_draft_id=result["draft"]["id"],
        )
        snapshots.append(("approval-request", "I approve", approved))
        self.assertEqual(len(self.store.messages()), 2)
        self.assertEqual(len(self.store.entries()), 1)
        coach = Coach(Store(self.temp.name), self.connections)
        before = (coach.store.messages(), coach.store.entries(), coach.store.drafts())
        with patch.object(coach, "generate") as model:
            for request, source, expected in snapshots:
                replay = coach.chat(
                    source,
                    True,
                    DAY,
                    request_id=request,
                    edit_message_id=user_id if "edit" in request else None,
                )
                for key, value in expected.items():
                    self.assertEqual(replay[key], value)
            model.assert_not_called()
        self.assertEqual(
            (coach.store.messages(), coach.store.entries(), coach.store.drafts()), before
        )

    def test_completed_legacy_exchange_is_cached_before_mutation(self):
        user = self.store.message(
            "user", {"text": "Original", "status": "sent", "request_id": "legacy-request"}
        )
        self.store.message("assistant", {"text": "Original answer", "request_id": "legacy-request"})
        self.store.update_message(
            user, {"text": "Edited", "status": "pending", "request_id": "new-request"}
        )
        self.assertEqual(self.store.chat_request("legacy-request")[1]["text"], "Original answer")
        self.assertEqual(
            Store(self.temp.name).chat_request("legacy-request")[1]["text"], "Original answer"
        )
        self.store.start_chat()
        self.assertTrue(self.store.chat_request("legacy-request"))
        self.store.reset()
        self.assertEqual(self.store.chat_request("legacy-request"), [])

    def test_followup_correction_cannot_be_submitted_as_full_source(self):
        data = meal(
            [
                {"name": "Milk", "portion": "400ml", "protein": 12},
                {"name": "Bread", "portion": "1 slice", "protein": 5},
            ]
        )
        user, draft = self.seed(data, "Change the milk to 400ml")
        self.store.update_message(
            user, {**self.store.messages()[0], "revise_draft_id": "previous-preview"}
        )
        with patch.object(self.coach, "generate") as model:
            with self.assertRaisesRegex(ValueError, "correction"):
                self.coach.chat("Change the milk to 600ml", True, edit_message_id=user)
            model.assert_not_called()
        self.assertEqual(self.store.drafts()[0]["id"], draft["id"])
        self.assertEqual(len(self.store.drafts()[0]["data"]["items"]), 2)
