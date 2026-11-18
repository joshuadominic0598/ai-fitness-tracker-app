import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.agent_tools import TOOLS, calculator, public_query
from fitness_tracker.coach import SYSTEM, Coach, Connections
from fitness_tracker.coach_skills import MANIFEST, select_skills
from fitness_tracker.prompt_budget import build_messages, input_tokens
from fitness_tracker.store import Store


class AgentGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.connections = Connections(Path(self.temp.name))
        self.connections.save(
            {
                "ollama_model": "qwen3:8b",
                "provider": "ollama",
            }
        )
        self.coach = Coach(self.store, self.connections)

    def tearDown(self):
        self.temp.cleanup()

    def test_calculator_rejects_code_and_bounds_operations(self):
        self.assertEqual(calculator("98/100*100")["value"], 98)
        self.assertEqual(calculator("(1.4*70 + 2*70)/2")["value"], 119)
        for value in (
            "__import__('os').getcwd()",
            "open('x')",
            "2**999",
            "1/0",
            "True+2",
            "[1,2]",
            "1e999",
        ):
            with self.assertRaises(ValueError):
                calculator(value)

    def test_skills_cover_training_topics_and_have_sources(self):
        self.assertGreaterEqual(len(MANIFEST), 7)
        self.assertNotIn("full_body", {skill["id"] for skill in MANIFEST})
        for question, expected in (
            ("cardio running endurance", "cardio"),
            ("grow my biceps and triceps", "muscle_focus"),
            ("protein meal portions", "nutrition"),
            ("creatine supplement", "supplements"),
            ("busy full body workout", "strength"),
        ):
            selected = select_skills(question)
            self.assertIn(expected, [s["id"] for s in selected])
            self.assertEqual(selected[0]["id"], "safety")
            self.assertTrue(all(s["sources"] and s["content"] for s in selected))

    def test_mandatory_search_calculator_and_final_evidence(self):
        source = {
            "url": "https://www.who.int/example",
            "title": "Activity guide",
            "abstract": "Guidance",
        }
        replies = [
            {
                "action": "tool",
                "message": "Checking",
                "tool_calls": [{"name": "calculator", "args": {"expression": "98/112*100"}}],
            },
            {
                "action": "answer",
                "message": "The calculator gives 87.5%.",
                "citations": [source["url"], "https://invented.example/"],
            },
        ]
        with (
            patch.object(self.coach, "generate", side_effect=replies),
            patch("fitness_tracker.coach.web_search", return_value=[source]) as search,
        ):
            result = self.coach.chat(
                "What percentage is 98 of my 112 g goal?", True, research_mode=True
            )
        search.assert_called_once()
        self.assertEqual(result["citations"], [source["url"]])
        self.assertEqual(
            [t["tool"] for t in result["agent"]["trace"] if t["node"] == "tool"],
            ["web_search", "calculator"],
        )
        self.assertTrue(all(t <= 5000 for t in result["agent"]["input_token_estimates"]))
        self.assertEqual(self.store.entries(), [])
        self.assertEqual(result["agent"]["architecture"], "LangGraph")

    def test_search_failure_and_loop_limit_are_visible(self):
        reply = {
            "action": "tool",
            "message": "Again",
            "tool_calls": [{"name": "calculator", "args": {"expression": "1+1"}}],
        }
        with (
            patch.object(self.coach, "generate", return_value=reply) as generate,
            patch("fitness_tracker.coach.web_search", side_effect=ValueError("Search unavailable")),
        ):
            result = self.coach.chat("Help me train", True, research_mode=True)
        self.assertEqual(generate.call_count, 4)
        self.assertTrue(any("unavailable" in n for n in result["notices"]))
        self.assertNotIn("draft", result)
        self.assertEqual(self.store.entries(), [])

    def test_budget_includes_tools_skills_context_and_preserves_constraints(self):
        self.store.save_profile(
            {"constraints": "Cannot train through shoulder pain", "focus": "Build stronger arms"}
        )
        context = self.coach.context()
        skills = select_skills("strength arms workout", context["profile"]["focus"])
        history = [{"role": "user", "text": "old history " * 2000} for _ in range(10)]
        messages, tokens = build_messages(
            SYSTEM,
            TOOLS,
            skills,
            context,
            self.coach.exercise_context("arms", context),
            history,
            "Plan a manageable session",
            [],
            5000,
            "qwen3:8b",
        )
        self.assertLessEqual(tokens, 5000)
        self.assertIn("Cannot train through shoulder pain", messages[0]["content"])
        self.assertIn("TOOLS=", messages[0]["content"])
        self.assertIn("COACHING SKILLS", messages[0]["content"])
        self.assertEqual(messages[-1]["content"], "Plan a manageable session")
        with self.assertRaises(ValueError):
            build_messages(
                SYSTEM, TOOLS, skills, context, [], [], "x " * 10000, [], 5000, "qwen3:8b"
            )
        self.assertLessEqual(input_tokens(messages, "qwen3:8b"), 5000)

    def test_meal_draft_must_match_calculator_result(self):
        reply = {
            "action": "meal",
            "message": "Estimate",
            "proposal": {"date": "2026-11-09", "description": "Eggs and bread", "protein": 20},
        }

        def calc(expression):
            return {
                "action": "tool",
                "message": "Calculate",
                "tool_calls": [{"name": "calculator", "args": {"expression": expression}}],
            }

        with patch.object(
            self.coach, "generate", side_effect=[calc("12+16"), reply, calc("12+8"), reply]
        ):
            result = self.coach.chat("Prepare a food draft", True, research_mode=True)
        self.assertEqual(result["draft"]["data"]["protein"], 20)
        self.assertEqual(self.store.entries(), [])
        self.store.reset()
        with patch.object(self.coach, "generate", side_effect=[calc("12+16"), reply, reply, reply]):
            result = self.coach.chat("Prepare a food draft", True, research_mode=True)
        self.assertNotIn("draft", result)
        self.assertEqual(self.store.drafts(), [])

    def test_math_question_cannot_bypass_calculator(self):
        with (
            patch.object(
                self.coach, "generate", return_value={"action": "answer", "message": "87.5%"}
            ) as generate,
            patch("fitness_tracker.coach.web_search", return_value=[]),
        ):
            result = self.coach.chat("What percentage is 98 of 112?", True, research_mode=True)
        self.assertEqual(generate.call_count, 4)
        self.assertNotEqual(result["text"], "87.5%")
        self.assertNotIn("draft", result)

    def test_live_search_fallback_is_labelled(self):
        from fitness_tracker.agent_tools import web_search

        paper = {
            "title": "Trial",
            "url": "https://europepmc.org/article/MED/1",
            "abstract": "Summary",
        }
        with (
            patch("ddgs.DDGS") as engine,
            patch("fitness_tracker.coach.research", return_value=[paper]),
        ):
            engine.return_value.text.side_effect = RuntimeError("Search blocked")
            result = web_search("muscle training")
        self.assertIn("metasearch unavailable", result[0]["kind"])

    def test_public_queries_remove_private_names_and_numbers(self):
        query = public_query(
            "Joshua private@example.com weighs 73.5 kg and wants biceps hypertrophy"
        )
        self.assertNotIn("Joshua", query)
        self.assertNotIn("example", query)
        self.assertNotIn("73", query)
        self.assertIn("biceps", query)
