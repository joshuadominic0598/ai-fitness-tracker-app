import tempfile
import unittest
from datetime import date
from pathlib import Path

from fitness_tracker.chat_policy import BASE_CHAT_SYSTEM, task_policy
from fitness_tracker.coach import CHAT_SYSTEM, Coach, Connections
from fitness_tracker.prompt_budget import (
    build_chat_messages,
    recent_exchanges,
    scoped_context,
)
from fitness_tracker.store import Store


class PromptBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.connections = Connections(Path(self.tmp.name))
        self.connections.save({"ollama_model": "qwen3:8b"})
        self.coach = Coach(self.store, self.connections)
        self.store.save_profile(
            {"focus": "Build arms", "constraints": "Avoid painful shoulder movements"}
        )
        self.store.save(
            "workout",
            {
                "date": date.today().isoformat(),
                "exercises": [
                    {
                        "exercise_id": "Pushups",
                        "tracking": "reps",
                        "load_mode": "bodyweight",
                        "sets": [{"weight": 0, "reps": 12, "seconds": 0}],
                    }
                ],
            },
        )
        self.context = self.coach.context("2026-02-01")

    def test_meal_and_general_chat_do_not_attach_training_or_metrics(self):
        for question in ("Log my food: two eggs and toast", "Hello there"):
            ctx = scoped_context(self.context, question)
            self.assertEqual(ctx["metrics"], {})
            self.assertEqual(ctx["recent_entries"], [])
            self.assertNotIn("constraints", ctx["profile"])
            messages, _ = build_chat_messages(
                CHAT_SYSTEM,
                self.context,
                [{"id": "Pushups"}],
                [],
                question,
                5000,
                "qwen3:8b",
                "ollama",
            )
            self.assertNotIn("Pushups", messages[0]["content"])
            self.assertNotIn("EXERCISE IDS:", messages[0]["content"])

    def test_standing_prompt_is_small_and_only_loads_task_instructions(self):
        self.assertLess(len(BASE_CHAT_SYSTEM.split()), 260)
        general = task_policy(BASE_CHAT_SYSTEM, set())
        meal = task_policy(BASE_CHAT_SYSTEM, {"meal"})
        self.assertNotIn("Completed workout:", meal)
        self.assertNotIn("Supplement:", meal)
        self.assertNotIn("Meal:", general)
        self.assertIn("calculation", meal)
        pending = {"kind": "batch", "data": {"entries": [{"kind": "meal"}, {"kind": "workout"}]}}
        revision = task_policy(BASE_CHAT_SYSTEM, set(), pending)
        self.assertIn("Completed workout:", revision)
        self.assertIn("Meal:", revision)
        self.assertIn("preserve untouched entries", revision)

    def test_ordinary_chat_targets_three_thousand_tokens_even_with_larger_ceiling(self):
        history = [
            {"role": role, "text": "meal correction " * 300}
            for _ in range(3)
            for role in ("user", "assistant")
        ]
        messages, tokens = build_chat_messages(
            CHAT_SYSTEM,
            self.context,
            [],
            history,
            "Estimate protein in two eggs",
            5000,
            "qwen3:8b",
            "ollama",
        )
        self.assertLessEqual(tokens, 3000)
        self.assertEqual(messages[-1]["content"], "Estimate protein in two eggs")

    def test_assessment_receives_journal_while_routine_only_receives_constraints(self):
        assessment = scoped_context(self.context, "Assess my workouts, nutrition and progress")
        self.assertTrue(assessment["metrics"]["top_exercises"])
        self.assertEqual(assessment["recent_entries"][0]["exercises"][0]["exercise_id"], "Pushups")
        routine = scoped_context(self.context, "Suggest an arm routine")
        self.assertIn("painful shoulder", routine["profile"]["constraints"])
        self.assertEqual(routine["recent_entries"], [])
        recall = scoped_context(self.context, "Log the same workout as last time")
        self.assertEqual(recall["recent_entries"][0]["kind"], "workout")

    def test_last_three_exchanges_are_sent_but_saved_history_is_untouched(self):
        history = []
        for i in range(6):
            history += [
                {"role": "user", "text": f"Question {i}"},
                {"role": "assistant", "text": f"Answer {i}"},
            ]
        selected = recent_exchanges(history)
        self.assertEqual(len(selected), 6)
        self.assertEqual(selected[0]["content"], "Question 3")
        self.assertEqual(selected[-1]["content"], "Answer 5")
        self.assertEqual(len(history), 12)

    def test_budget_can_drop_old_exchanges_without_splitting_current_request(self):
        history = [
            {"role": role, "text": f"Turn {i} " + "detail " * 500}
            for i in range(3)
            for role in ("user", "assistant")
        ]
        for provider, model in (
            ("ollama", "qwen3:8b"),
            ("ollama", "qwen3:8b"),
        ):
            with self.subTest(provider=provider):
                _, base = build_chat_messages(
                    CHAT_SYSTEM, self.context, [], [], "Hello", 5000, model, provider
                )
                messages, tokens = build_chat_messages(
                    CHAT_SYSTEM, self.context, [], history, "Hello", base + 1050, model, provider
                )
                self.assertLessEqual(tokens, base + 1050)
                self.assertLess(len(messages), 8)
                self.assertGreater(len(messages), 2)
                self.assertEqual(messages[1]["role"], "user")
                self.assertEqual(messages[-1]["content"], "Hello")
                self.assertIn("Turn 2", str(messages))

    def test_short_followup_keeps_only_relevant_goals_and_pending_revision(self):
        history = [
            {"role": "user", "text": "I took vitamin D"},
            {"role": "assistant", "text": "How many tablets?"},
        ]
        ctx = scoped_context(self.context, "One tablet", history)
        self.assertIn("supplement_goals", ctx["profile"])
        self.assertEqual(ctx["recent_entries"], [])
        draft = {"kind": "meal", "data": {"description": "Toast", "protein": 8}}
        context = {**self.context, "pending_draft": draft}
        self.assertEqual(scoped_context(context, "Change to 10 g")["pending_draft"], draft)
