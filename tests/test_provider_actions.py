import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.chat_actions import check_meal_calculation, claims_saved, requested_log_kind
from fitness_tracker.coach import Coach, Connections
from fitness_tracker.store import Store


class ProviderActionTests(unittest.TestCase):
    def test_log_intent_follows_the_recent_conversation_without_extra_model_calls(self):
        history = [
            {"role": "user", "text": "Estimate protein in milk and a boiled egg."},
            {"role": "assistant", "text": "About 18 g protein."},
            {"role": "user", "text": "how did you estimate that?"},
            {"role": "assistant", "text": "Based on the milk and egg protein."},
        ]
        for message in ("ya add this 18g now", "prepare a preview'", "Can you log it?"):
            self.assertEqual(requested_log_kind(message, history), "meal")
        for message in ("Don't log that", "How do I add food?", "Estimate my protein"):
            self.assertIsNone(requested_log_kind(message, history))

    def test_natural_logging_followup_has_real_preview_amounts(self):
        for provider in ("ollama",):
            coach, store = self.make_coach(provider)
            store.message("user", {"text": "Estimate protein in milk and a boiled egg."})
            store.message("assistant", {"text": "About 18 g protein.", "action": "answer"})
            reply = {
                "action": "meal",
                "message": "Your entry was saved.",
                "proposal": {
                    "date": "2026-11-12",
                    "description": "Milk and egg",
                    "protein": 18,
                    "calories": 250,
                    "calculation": "3+6.5+6.3+2",
                },
            }
            with patch(
                "fitness_tracker.coach.Coach.generate", return_value=self.payload(provider, reply)
            ) as request:
                result = coach.chat("ya add this 18g now", True, "2026-11-12")
                request.assert_called_once()
                payload = request.call_args.args[0]
                self.assertIn("not answer or a prose-only preview", str(payload))
            self.assertEqual(result["draft"]["data"]["protein"], 18)
            self.assertIn("18 g protein", result["text"])
            self.assertNotIn("Opening Track", result["text"])
            self.assertIn("approve it here", result["text"])
            self.assertEqual(store.entries(), [])
            self.assertEqual(len(store.drafts()), 1)
            self.assertIn("18 g protein", result["preview_summary"])
            self.assertEqual(store.messages()[-1]["preview_summary"], result["preview_summary"])

    def test_estimate_rounding_is_valid_but_incorrect_math_is_rejected(self):
        check_meal_calculation({"protein": 18}, "3+6.5+6.3+2")
        check_meal_calculation({"protein": 17.8}, "3+6.5+6.3+2")
        with self.assertRaises(ValueError):
            check_meal_calculation({"protein": 18}, "3+6")
        with self.assertRaises(ValueError):
            check_meal_calculation({"protein": 17.8}, "17.3")

    def test_failed_calculation_never_announces_a_preview_or_redirect(self):
        for provider in ("ollama",):
            coach, store = self.make_coach(provider)
            reply = {
                "action": "meal",
                "message": "Here's your preview of 18 g.",
                "proposal": {
                    "date": "2026-11-12",
                    "description": "Toast",
                    "protein": 18,
                    "calories": 250,
                    "calculation": "1+2",
                },
            }
            with patch(
                "fitness_tracker.coach.Coach.generate", return_value=self.payload(provider, reply)
            ):
                result = coach.chat("Log 18g protein from toast", True)
            self.assertNotIn("draft", result)
            self.assertEqual(result["action"], "clarify")
            self.assertIn("couldn't create a valid preview", result["text"])
            self.assertEqual(store.drafts(), [])
            self.assertEqual(store.entries(), [])

    def test_prose_only_preview_is_not_passed_off_as_real(self):
        coach, store = self.make_coach("ollama")
        with patch.object(
            coach,
            "generate",
            return_value={"action": "answer", "message": "Here's your preview of 18 g protein."},
        ):
            result = coach.chat("Prepare a preview of 18 g protein", True)
        self.assertNotIn("draft", result)
        self.assertEqual(result["action"], "clarify")
        self.assertIn("couldn't prepare a structured preview", result["text"])
        self.assertEqual(store.entries(), [])

    def make_coach(self, provider):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Store(tmp.name)
        connections = Connections(Path(tmp.name))
        connections.save(
            {
                "provider": provider,
                provider + "_key": "synthetic",
                provider + "_model": "qwen3:8b",
            }
        )
        return Coach(store, connections), store

    def payload(self, provider, reply):
        import copy

        reply = copy.deepcopy(reply)
        if reply.get("action") == "meal" and isinstance(reply.get("proposal"), dict):
            reply["calculation"] = reply["proposal"].pop("calculation", reply.get("calculation"))
        return reply

    def test_qwen_logging_actions_require_approval(self):
        day = "2026-11-11"
        workout = {
            "date": day,
            "exercises": [
                {
                    "exercise_id": "Pushups",
                    "tracking": "reps",
                    "load_mode": "bodyweight",
                    "sets": [{"weight": 0, "reps": 12, "seconds": 0}],
                }
            ],
        }
        cases = {
            "meal": {
                "date": day,
                "description": "Toast",
                "protein": 8,
                "calories": 200,
                "calculation": "4+4",
            },
            "workout": workout,
            "plan": {"date": day, "exercises": [{"exercise_id": "Pushups"}]},
            "creatine": {"date": day, "amount": 5, "unit": "g"},
            "supplement": {"date": day, "name": "Vitamin D", "amount": 1, "unit": "tablet"},
            "sleep": {"date": day, "hours": 7, "period": "night"},
            "body": {"date": day, "weight_kg": 70},
            "batch": {
                "entries": [
                    {"kind": "workout", "data": workout},
                    {
                        "kind": "meal",
                        "data": {
                            "date": day,
                            "description": "Toast",
                            "protein": 8,
                            "calories": 200,
                        },
                        "calculation": "4+4",
                    },
                ]
            },
        }
        for provider in ("ollama",):
            for kind, proposal in cases.items():
                with self.subTest(provider=provider, kind=kind):
                    coach, store = self.make_coach(provider)
                    reply = {
                        "action": kind,
                        "message": "Your entry is saved.",
                        "proposal": proposal,
                    }
                    with patch(
                        "fitness_tracker.coach.Coach.generate",
                        return_value=self.payload(provider, reply),
                    ) as request:
                        result = coach.chat(
                            "Prepare the requested entry",
                            True,
                            day,
                            logging_kind=kind if kind != "batch" else "any",
                        )
                        request.assert_called_once()
                    self.assertEqual(result["draft"]["kind"], kind)
                    expected_summary = {
                        "meal": "8 g protein",
                        "workout": "1 exercise, 1 set",
                        "plan": "1 exercise",
                        "creatine": "Creatine: 5 g",
                        "supplement": "Vitamin D: 1 tablet",
                        "sleep": "7 h night sleep",
                        "body": "70 kg body weight",
                        "batch": "8 g protein",
                    }[kind]
                    self.assertIn(expected_summary, result["preview_summary"])
                    self.assertEqual(store.entries(), [])
                    self.assertIn("Nothing is saved", result["text"])
                    with patch.object(coach, "generate") as generate:
                        saved = coach.chat("I approve", True, day, request_id="approve-request")
                        generate.assert_not_called()
                    self.assertIn("approved", saved)
                    self.assertIn(expected_summary, saved["text"])
                    self.assertEqual(len(store.entries()), 2 if kind == "batch" else 1)
                    again = coach.chat("I approve", True, day, request_id="approve-request")
                    self.assertEqual(again["approved"], saved["approved"])
                    coach.chat("I approve", True, day)
                    self.assertEqual(len(store.entries()), 2 if kind == "batch" else 1)

    def test_all_pending_action_types_can_be_corrected_and_approved_in_chat(self):
        day = "2026-11-11"
        movement = {
            "exercise_id": "Pushups",
            "tracking": "reps",
            "load_mode": "bodyweight",
            "sets": [{"weight": 0, "reps": 12, "seconds": 0}],
        }
        cases = {
            "meal": {
                "date": day,
                "description": "Toast",
                "protein": 8,
                "calories": 200,
                "calculation": "4+4",
            },
            "workout": {"date": day, "exercises": [movement]},
            "plan": {"date": day, "exercises": [{"exercise_id": "Pushups"}]},
            "creatine": {"date": day, "amount": 5, "unit": "g"},
            "supplement": {"date": day, "name": "Vitamin D", "amount": 1, "unit": "tablet"},
            "sleep": {"date": day, "hours": 7, "period": "night"},
            "body": {"date": day, "weight_kg": 70},
            "batch": {
                "entries": [
                    {"kind": "sleep", "data": {"date": day, "hours": 7, "period": "night"}},
                    {
                        "kind": "supplement",
                        "data": {"date": day, "name": "Creatine", "amount": 5, "unit": "g"},
                    },
                ]
            },
        }
        for provider in ("ollama",):
            for kind, data in cases.items():
                with self.subTest(provider=provider, kind=kind):
                    coach, store = self.make_coach(provider)
                    original = store.draft(kind, data)
                    store.message(
                        "assistant", {"text": "Review these proposed amounts", "draft": original}
                    )
                    revised = json.loads(json.dumps(data))
                    target = revised["entries"][0]["data"] if kind == "batch" else revised
                    target["notes"] = "Corrected in chat"
                    reply = {
                        "action": kind,
                        "message": "Review the correction",
                        "proposal": revised,
                    }
                    with patch(
                        "fitness_tracker.coach.Coach.generate",
                        return_value=self.payload(provider, reply),
                    ) as request:
                        response = coach.chat(
                            "Actually, change the notes to Corrected in chat", True, "2026-11-13"
                        )
                        request.assert_called_once()
                        self.assertIn(
                            '"selected_date":"2026-11-11"', str(request.call_args.args[0])
                        )
                    self.assertEqual(len(store.drafts()), 1)
                    self.assertNotEqual(response["draft"]["id"], original["id"])
                    self.assertEqual(store.entries(), [])
                    self.assertNotIn("Opening Track", response["text"])
                    with patch.object(coach, "generate") as generation:
                        result = coach.chat(
                            "I approve", True, approve_draft_id=response["draft"]["id"]
                        )
                        generation.assert_not_called()
                    self.assertIn("approved", result)
                    self.assertTrue(all(entry["date"] == day for entry in store.entries()))
                    self.assertEqual(store.drafts(), [])
                    self.assertEqual(len(store.entries()), 2 if kind == "batch" else 1)

    def test_unrelated_changes_do_not_attach_to_pending_food(self):
        from fitness_tracker.chat_actions import pending_revision

        coach, store = self.make_coach("ollama")
        draft = store.draft(
            "meal", {"date": "2026-11-11", "description": "Toast", "protein": 8, "calories": 200}
        )
        history = [{"role": "assistant", "draft": draft}]
        self.assertIsNone(pending_revision("Change my sleep to 8 hours", history, store.drafts()))
        self.assertIsNone(
            pending_revision("Change my protein goal to 120", history, store.drafts())
        )
        self.assertEqual(
            pending_revision("Actually, change it to 10 g", history, store.drafts()), draft["id"]
        )

    def test_no_preview_and_unrelated_previews_cannot_be_approved(self):
        for provider in ("ollama",):
            coach, store = self.make_coach(provider)
            store.draft("meal", {"date": "2026-11-11", "description": "Unrelated", "protein": 8})
            with patch.object(coach, "generate") as generate:
                result = coach.chat("I approve", True)
                generate.assert_not_called()
            self.assertIn("Nothing was saved", result["text"])
            self.assertEqual(store.entries(), [])

    def test_model_cannot_claim_a_save_without_an_app_action(self):
        self.assertFalse(claims_saved("Nothing has been logged yet."))
        self.assertFalse(claims_saved("Review it before it is saved."))
        self.assertTrue(claims_saved("Your meal is approved and recorded."))
        for provider in ("ollama",):
            coach, store = self.make_coach(provider)
            with patch.object(
                coach,
                "generate",
                return_value={
                    "action": "answer",
                    "message": "Great! Your meal is approved and recorded.",
                },
            ):
                result = coach.chat("What happened to my meal?", True)
            self.assertEqual(store.entries(), [])
            self.assertIn("No entry was saved", result["text"])

    def test_clicked_approval_saves_the_specific_linked_preview_even_outside_recent_context(self):
        for provider in ("ollama",):
            coach, store = self.make_coach(provider)
            older = store.draft(
                "meal", {"date": "2026-11-11", "description": "Toast", "protein": 18}
            )
            store.message("assistant", {"text": "18 g preview", "draft": older})
            newer = store.draft("meal", {"date": "2026-11-12", "description": "Milk", "protein": 8})
            for _ in range(4):
                store.message("user", {"text": "Hello"})
                store.message("assistant", {"text": "Hello"})
            store.message("assistant", {"text": "8 g preview", "draft": newer})
            with patch.object(coach, "generate") as generate:
                saved = coach.chat(
                    "I approve", True, approve_draft_id=older["id"], request_id="clicked-approval"
                )
                generate.assert_not_called()
            self.assertEqual(saved["approved"]["draft_id"], older["id"])
            self.assertEqual(store.entries()[0]["protein"], 18)
            self.assertEqual(store.drafts()[0]["id"], newer["id"])
            again = coach.chat(
                "I approve", True, approve_draft_id=older["id"], request_id="clicked-approval"
            )
            self.assertEqual(again["approved"], saved["approved"])
            self.assertEqual(len(store.entries()), 1)
            unlinked = store.draft(
                "meal", {"date": "2026-11-13", "description": "Unlinked", "protein": 5}
            )
            with patch.object(coach, "generate") as generate:
                result = coach.chat("I approve", True, approve_draft_id=unlinked["id"])
                generate.assert_not_called()
            self.assertNotIn("approved", result)
            self.assertEqual(len(store.entries()), 1)

    def test_stale_preview_cannot_be_saved_through_chat(self):
        coach, store = self.make_coach("ollama")
        draft = store.draft(
            "meal", {"date": "2026-11-11", "description": "Toast", "protein": 8, "calories": 200}
        )
        store.message("assistant", {"text": "Preview ready", "draft": draft})
        store.save("meal", {"date": "2026-11-11", "description": "Intervening edit", "protein": 10})
        with patch.object(coach, "generate") as generate:
            with self.assertRaises(ValueError):
                coach.chat("I approve", True)
            generate.assert_not_called()
        self.assertEqual(len(store.entries()), 1)
