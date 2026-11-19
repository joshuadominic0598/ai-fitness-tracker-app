import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.coach import Coach, Connections, ProviderError
from fitness_tracker.store import Store


class DirectChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.connections = Connections(Path(self.tmp.name))
        self.connections.save({"ollama_model": "qwen3:8b"})
        self.coach = Coach(self.store, self.connections)

    def test_normal_chat_is_one_generation_without_tools_and_remembers_corrections(self):
        self.store.message("user", {"text": "Bread protein is 8 g, peanut butter protein is 6 g."})
        self.store.message("assistant", {"text": "Understood."})
        with (
            patch.object(
                self.coach,
                "generate",
                return_value={"action": "answer", "message": "That is 14 g."},
            ) as generate,
            patch.object(self.coach, "run_tool") as tools,
        ):
            reply = self.coach.chat("Total for those two?", True)
        generate.assert_called_once()
        self.assertTrue(generate.call_args.kwargs["direct"])
        self.assertIn("Bread protein is 8 g", str(generate.call_args.args[0]))
        tools.assert_not_called()
        self.assertEqual(reply["agent"]["architecture"], "Direct chat")
        self.assertEqual(reply["papers"], [])
        self.assertEqual(self.store.entries(), [])

    def test_meal_proposal_uses_local_math_and_still_requires_approval(self):
        proposal = {
            "action": "meal",
            "message": "Review this 14 g estimate.",
            "calculation": "8+6",
            "proposal": {
                "date": "2026-11-10",
                "description": "Bread and peanut butter",
                "protein": 14,
            },
        }
        with patch.object(self.coach, "generate", return_value=proposal) as generate:
            reply = self.coach.chat("Log my meal for Nov 10", True)
        generate.assert_called_once()
        self.assertEqual(reply["draft"]["data"]["protein"], 14)
        self.assertEqual(self.store.entries(), [])
        self.store.reset()
        with patch.object(self.coach, "generate", return_value={**proposal, "calculation": "1+2"}):
            reply = self.coach.chat("Log my meal", True)
        self.assertNotIn("draft", reply)
        self.assertEqual(self.store.drafts(), [])

    def test_failed_direct_request_is_not_automatically_retried(self):
        with patch.object(
            self.coach, "generate", side_effect=ProviderError("Quota reached")
        ) as generate:
            result = self.coach.chat("Hi", True)
            self.assertTrue(result["recovered"])
        generate.assert_called_once()
        self.assertEqual(self.store.messages()[0]["status"], "sent")

    def test_older_messages_remain_available_to_scroll(self):
        for index in range(45):
            self.store.message("user", {"text": f"Message {index}"})
        messages = self.store.messages()
        self.assertEqual(len(messages), 45)
        self.assertEqual(messages[0]["text"], "Message 0")
        self.assertEqual(messages[-1]["text"], "Message 44")
