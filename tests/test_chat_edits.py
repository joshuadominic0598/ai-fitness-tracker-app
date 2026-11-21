import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.chat_actions import draft_message
from fitness_tracker.coach import Coach, Connections
from fitness_tracker.store import Store

DAY = "2026-11-21"


class ChatEditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.coach = Coach(self.store, Connections(Path(self.tmp.name)))

    def seed(self, kind, data, source):
        draft = self.store.draft(kind, {"date": DAY, **data})
        user_id = self.store.message(
            "user",
            {
                "text": source,
                "logging_kind": kind,
                "context_date": DAY,
                "status": "sent",
                "request_id": "original-request",
            },
        )
        answer_id = self.store.message(
            "assistant",
            {
                "text": draft_message(draft),
                "action": kind,
                "draft": draft,
                "request_id": "original-request",
            },
        )
        self.store.coach_state(value={"draft_id": draft["id"], "kind": kind, "date": DAY})
        return user_id, answer_id, draft

    def test_every_log_type_updates_the_same_exchange_and_approval_adds_no_turn(self):
        cases = [
            (
                "meal",
                {
                    "description": "Milk and bread",
                    "protein": 18.2,
                    "items": [
                        {"name": "Milk", "portion": "400ml", "protein": 13.2},
                        {"name": "Bread", "portion": "1 slice", "protein": 5},
                    ],
                },
                {
                    "description": "Milk",
                    "protein": 13.2,
                    "items": [
                        {"name": "Milk", "portion": "400ml", "protein": 13.2},
                    ],
                },
                "Log my food: 400ml milk",
            ),
            (
                "creatine",
                {"name": "Creatine", "amount": 5, "unit": "g"},
                {"name": "Creatine", "amount": 3, "unit": "g"},
                "Log my creatine: 3g",
            ),
            (
                "supplement",
                {"name": "Vitamin C", "amount": 1, "unit": "tablet"},
                {"name": "Vitamin C", "amount": 2, "unit": "tablet"},
                "Log my supplement: 2 Vitamin C tablets",
            ),
            (
                "sleep",
                {"hours": 7, "period": "night"},
                {"hours": 8, "period": "night"},
                "Log my sleep: night 8hrs",
            ),
            ("body", {"weight_kg": 70}, {"weight_kg": 71}, "Log my body weight: 71kg"),
            (
                "workout",
                {
                    "exercises": [
                        {
                            "exercise_id": "Plank",
                            "sets": [
                                {"weight": 0, "reps": 0, "seconds": 60},
                                {"weight": 0, "reps": 0, "seconds": 40},
                            ],
                        }
                    ]
                },
                {
                    "exercises": [
                        {
                            "exercise_id": "Plank",
                            "sets": [
                                {"weight": 0, "reps": 0, "seconds": 40},
                            ],
                        }
                    ]
                },
                "Log my workout: Plank 40s",
            ),
        ]
        for kind, old, new, source in cases:
            with self.subTest(kind=kind):
                self.store.reset()
                user_id, answer_id, draft = self.seed(kind, old, "Original logging details")
                reply = {"action": kind, "message": "Review", "proposal": {"date": DAY, **new}}
                if kind == "meal":
                    reply["calculation"] = "13.2"
                with patch.object(self.coach, "generate", return_value=reply):
                    result = self.coach.chat(
                        source, True, edit_message_id=user_id, request_id="edited-request"
                    )
                messages = self.store.messages()
                self.assertEqual([m["id"] for m in messages], [user_id, answer_id])
                self.assertEqual(messages[0]["text"], source)
                self.assertEqual(messages[1]["draft"], result["draft"])
                self.assertEqual(len(self.store.drafts()), 1)
                self.assertNotEqual(result["draft"]["id"], draft["id"])
                self.assertEqual(self.store.entries(), [])
                if kind == "meal":
                    self.assertEqual(
                        [i["name"] for i in result["draft"]["data"]["items"]], ["Milk"]
                    )
                if kind == "workout":
                    self.assertEqual(len(result["draft"]["data"]["exercises"][0]["sets"]), 1)
                cached = self.coach.chat(
                    source, True, edit_message_id=user_id, request_id="edited-request"
                )
                self.assertEqual(cached["draft"], result["draft"])
                approved = self.coach.chat(
                    "I approve",
                    True,
                    approve_draft_id=result["draft"]["id"],
                    request_id="approval-request",
                )
                self.assertIn("approved", approved)
                self.assertEqual(len(self.store.entries()), 1)
                self.assertEqual([m["id"] for m in self.store.messages()], [user_id, answer_id])
                self.assertEqual(self.store.messages()[0]["text"], source)
                self.assertIn("approved", self.store.messages()[1])
                with self.assertRaisesRegex(ValueError, "unresolved"):
                    self.coach.chat(source, True, edit_message_id=user_id)

    def test_clarification_is_replaced_without_reintroducing_old_details(self):
        user_id, answer_id, _ = self.seed(
            "meal",
            {
                "description": "Bread",
                "protein": 5,
                "items": [{"name": "Bread", "portion": "1 slice", "protein": 5}],
            },
            "Log my food: bread",
        )
        with patch.object(
            self.coach, "generate", return_value={"action": "clarify", "message": "How much milk?"}
        ):
            self.coach.chat("Log my food: milk", True, edit_message_id=user_id)
        self.assertEqual(self.store.drafts(), [])
        self.assertEqual(len(self.store.messages()), 2)
        self.assertEqual(self.store.messages()[1]["action"], "clarify")
        coach = Coach(Store(self.tmp.name), self.coach.connections)
        with patch.object(
            coach,
            "generate",
            return_value={
                "action": "meal",
                "message": "Review",
                "calculation": "13.2",
                "proposal": {
                    "date": DAY,
                    "description": "Milk",
                    "protein": 13.2,
                    "items": [{"name": "Milk", "portion": "400ml", "protein": 13.2}],
                },
            },
        ) as model:
            result = coach.chat("Log my food: 400ml milk", True, edit_message_id=user_id)
        self.assertNotIn("Bread", str(model.call_args.args[0]))
        self.assertEqual([m["id"] for m in self.store.messages()], [user_id, answer_id])
        self.assertEqual(result["draft"]["data"]["protein"], 13.2)

    def test_failed_edit_can_retry_after_restart_without_duplicate_messages(self):
        user_id, answer_id, _ = self.seed("body", {"weight_kg": 70}, "Log my body weight: 70kg")
        with patch.object(self.coach, "generate", side_effect=ValueError("Interrupted")):
            with self.assertRaises(ValueError):
                self.coach.chat(
                    "Log my body weight: 71kg",
                    True,
                    edit_message_id=user_id,
                    request_id="failed-edit-request",
                )
        self.assertEqual(self.store.messages()[0]["status"], "failed")
        coach = Coach(Store(self.tmp.name), self.coach.connections)
        with patch.object(
            coach,
            "generate",
            return_value={
                "action": "body",
                "message": "Review",
                "proposal": {"date": DAY, "weight_kg": 71},
            },
        ):
            coach.chat(
                "Log my body weight: 71kg",
                True,
                edit_message_id=user_id,
                request_id="failed-edit-request",
            )
        self.assertEqual([m["id"] for m in self.store.messages()], [user_id, answer_id])
        self.assertEqual(self.store.entries(), [])

    def test_archived_or_invalid_edit_targets_cannot_modify_a_message(self):
        user_id, _, _ = self.seed("body", {"weight_kg": 70}, "Log my body weight: 70kg")
        self.store.start_chat()
        for target in (user_id, True, "1", 0):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.coach.chat("Log my body weight: 71kg", True, edit_message_id=target)
        self.assertEqual(self.store.messages(), [])
