import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.coach import Coach, Connections, ProviderError, videos
from fitness_tracker.store import Store


class CoachTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.connections = Connections(Path(self.temp.name))
        self.connections.save({"provider": "ollama", "ollama_model": "qwen3:8b"})
        self.coach = Coach(self.store, self.connections)
        search = patch("fitness_tracker.coach.web_search", return_value=[])
        search.start()
        self.addCleanup(search.stop)

    def tearDown(self):
        self.temp.cleanup()

    def test_consent_required_before_provider_call(self):
        with patch.object(self.coach, "generate") as generate:
            with self.assertRaises(ValueError):
                self.coach.chat("What should I eat?", False, research_mode=True)
            generate.assert_not_called()

    def test_food_draft_does_not_write_log(self):
        reply = {
            "action": "meal",
            "message": "Estimated 25–35 g.",
            "proposal": {
                "date": date.today().isoformat(),
                "description": "Dal and eggs",
                "protein": 30,
                "calories": 450,
                "low": 25,
                "high": 35,
            },
        }
        with patch.object(
            self.coach,
            "generate",
            side_effect=[
                {
                    "action": "tool",
                    "message": "Calculating",
                    "tool_calls": [{"name": "calculator", "args": {"expression": "15+15"}}],
                },
                reply,
            ],
        ):
            result = self.coach.chat("Log my meal: dal and eggs", True, research_mode=True)
        self.assertEqual(result["draft"]["kind"], "meal")
        self.assertEqual(self.store.entries(), [])
        self.assertEqual(len(self.store.drafts()), 1)

    def test_clarification_has_no_proposal(self):
        with patch.object(
            self.coach,
            "generate",
            return_value={"action": "clarify", "message": "How large was the bowl?"},
        ):
            result = self.coach.chat("I ate a bowl of dal", True, research_mode=True)
        self.assertEqual(result["action"], "clarify")
        self.assertEqual(self.store.drafts(), [])

    def test_research_loop_and_allowed_citations(self):
        paper = {
            "title": "Trial",
            "url": "https://europepmc.org/article/MED/123",
            "abstract": "Study",
        }
        replies = [
            {
                "action": "research",
                "message": "Looking up evidence.",
                "research_query": "protein training",
            },
            {
                "action": "answer",
                "message": "Here is what the trial suggests.",
                "citations": [paper["url"], "https://invented.example/"],
            },
        ]
        with (
            patch.object(self.coach, "generate", side_effect=replies) as generate,
            patch("fitness_tracker.coach.research", return_value=[paper]),
        ):
            result = self.coach.chat("What does research say?", True, research_mode=True)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result["citations"], [paper["url"]])

    def test_invalid_proposal_cannot_create_log(self):
        with patch.object(
            self.coach,
            "generate",
            return_value={"action": "plan", "message": "Try this", "proposal": {"date": "bad"}},
        ):
            result = self.coach.chat("Plan something", True, research_mode=True)
        self.assertTrue(result["notices"])
        self.assertEqual(self.store.entries(), [])
        self.assertEqual(self.store.drafts(), [])

    def test_no_key_video_search_returns_real_search_link(self):
        result = videos("bicep curl form", self.connections)
        self.assertEqual(result["items"], [])
        self.assertIn("youtube.com/results?search_query=bicep+curl+form", result["search_url"])

    def test_legacy_video_key_never_triggers_a_youtube_api_request(self):
        self.connections.save({"youtube_key": "synthetic-unused-key"})
        with patch("fitness_tracker.coach.request_json") as request:
            result = videos("Plank exercise proper form tutorial", self.connections)
        request.assert_not_called()
        self.assertEqual(result["items"], [])
        self.assertIn("youtube.com/results?", result["search_url"])

    def test_provider_failure_recovers_in_chat_without_switching_or_logging_fitness(self):
        with patch.object(
            self.coach, "generate", side_effect=ProviderError("Rate limit")
        ) as generate:
            result = self.coach.chat("Estimate my lunch", True, research_mode=True)
            self.assertTrue(result["recovered"])
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(self.store.entries(), [])
        messages = self.store.messages()
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["status"], "sent")
        self.assertEqual(messages[0]["text"], "Estimate my lunch")

    def test_connection_probe_has_no_private_context_or_writes(self):
        before = self.connections.read()
        with patch.object(
            self.coach, "generate", return_value={"action": "answer", "message": "Connected"}
        ) as generate:
            result = self.coach.test_connection("ollama")
        self.assertTrue(result["ok"])
        self.assertEqual(result["model"], "qwen3:8b")
        self.assertNotIn("PRIVATE JOURNAL", str(generate.call_args.args[0]))
        self.assertEqual(self.store.entries(), [])
        self.assertEqual(self.store.messages(), [])
        self.assertEqual(self.connections.read(), before)
        self.assertFalse(self.coach.lock.locked())
        with self.assertRaises(ValueError):
            self.coach.test_connection("invalid")
        with patch.object(self.coach, "generate", side_effect=ProviderError("Test failure")):
            with self.assertRaises(ProviderError):
                self.coach.test_connection("ollama")
        self.assertFalse(self.coach.lock.locked())

    def test_catalog_context_is_bounded_and_relevant(self):
        ctx = self.coach.context()
        chosen = self.coach.exercise_context("I want bigger arms", ctx)
        self.assertLessEqual(len(chosen), 32)
        self.assertTrue(any("biceps" in e["muscles"] for e in chosen))
        self.assertTrue(any("triceps" in e["muscles"] for e in chosen))
        self.assertLessEqual(len(ctx["insights"]["daily"]), 28)

    def test_research_uses_supported_query_parameters(self):
        from urllib.parse import parse_qs, urlsplit

        from fitness_tracker.coach import research

        with patch(
            "fitness_tracker.coach.request_json", return_value={"resultList": {"result": []}}
        ) as request:
            self.assertEqual(research("protein resistance training"), [])
        params = parse_qs(urlsplit(request.call_args[0][0]).query)
        self.assertNotIn("sort", params)
        self.assertEqual(params["resultType"], ["core"])

    def test_context_and_draft_use_the_selected_journal_date(self):
        ctx = self.coach.context("2026-11-05")
        self.assertEqual(ctx["selected_date"], "2026-11-05")
        reply = {
            "action": "meal",
            "message": "Estimate for your selected day.",
            "proposal": {
                "date": "2026-11-05",
                "description": "Lunch",
                "protein": 30,
                "calories": 400,
            },
        }
        with patch.object(
            self.coach,
            "generate",
            side_effect=[
                {
                    "action": "tool",
                    "message": "Calculating",
                    "tool_calls": [{"name": "calculator", "args": {"expression": "15+15"}}],
                },
                reply,
            ],
        ):
            result = self.coach.chat("Log lunch", True, "2026-11-05", research_mode=True)
        self.assertEqual(result["draft"]["data"]["date"], "2026-11-05")
