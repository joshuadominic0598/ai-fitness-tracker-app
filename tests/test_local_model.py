import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.chat_actions import meal_portion_revision
from fitness_tracker.coach import Coach, Connections
from fitness_tracker.local_model import generate, local_url, models
from fitness_tracker.store import Store

INFO = {"capabilities": ["completion", "thinking"], "model_info": {"qwen3.context_length": 40960}}


def reply(data=None, **usage):
    return {
        "message": {"content": json.dumps(data or {"action": "answer", "message": "Connected."})},
        "prompt_eval_count": 123,
        "eval_count": 20,
        "done_reason": "stop",
        **usage,
    }


class LocalModelTests(unittest.TestCase):
    def test_only_local_qwen_can_be_selected_or_called(self):
        with tempfile.TemporaryDirectory() as tmp:
            connections = Connections(Path(tmp))
            coach = Coach(Store(tmp), connections)
            with patch("fitness_tracker.local_model.request") as request:
                for provider in ("groq", "gemini"):
                    with self.assertRaisesRegex(ValueError, "local Qwen"):
                        connections.save({"provider": provider})
                    with self.assertRaisesRegex(ValueError, "local Qwen"):
                        coach.generate([], provider, "qwen3:8b", "")
                for model in ("llama3:8b", "qwen3:cloud", "../qwen3:8b;echo"):
                    with self.assertRaises(ValueError):
                        connections.save({"ollama_model": model})
                request.assert_not_called()
            self.assertEqual(connections.public()["provider"], "ollama")
            self.assertFalse(any("key" in key for key in connections.public()))

    def test_explicit_local_portion_correction_preserves_other_foods_without_inference(self):
        data = {
            "date": "2026-02-01",
            "description": "Milk and egg",
            "protein": 11.25,
            "items": [
                {"name": "Milk", "portion": "150ml", "protein": 4.95},
                {"name": "Egg", "portion": "1 large", "protein": 6.3},
            ],
        }
        for message in (
            "Change milk to 250ml and add bread",
            "Change protein to 25g",
            "Change milk to 250g",
            "Don't change milk to 250ml",
        ):
            self.assertIsNone(meal_portion_revision(message, data))
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            connections = Connections(Path(tmp))
            connections.save({"provider": "ollama"})
            draft = store.draft("meal", data)
            store.message("user", {"text": "Log my food"})
            store.message("assistant", {"text": "Review.", "action": "meal", "draft": draft})
            coach = Coach(store, connections)
            with patch.object(coach, "generate") as generate:
                result = coach.chat(
                    "Change only the milk portion to 250ml, keeping the egg unchanged.", True
                )
            generate.assert_not_called()
            revised = result["draft"]["data"]
            self.assertEqual(revised["items"][0]["protein"], 8.25)
            self.assertEqual(revised["items"][1]["protein"], 6.3)
            self.assertEqual(revised["protein"], 14.55)
            self.assertTrue(result["agent"]["source_based_correction"])
            self.assertEqual(len(store.drafts()), 1)
            self.assertEqual(store.entries(), [])

    def test_connection_migration_removes_legacy_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            connections = Connections(Path(tmp))
            connections.path.write_text(
                json.dumps({"groq_key": "synthetic", "groq_model": "saved-cloud"})
            )
            connections = Connections(Path(tmp))
            public = connections.save({"provider": "ollama", "ollama_context_tokens": 8192})
            self.assertEqual(public["ollama_model"], "qwen3:8b")
            self.assertEqual(public["ollama_model"], "qwen3:8b")
            self.assertNotIn("groq_key", public)
            self.assertNotIn("groq_key", connections.read())
            self.assertNotIn("groq_model", connections.read())
            with patch("fitness_tracker.local_model.request", side_effect=[INFO, reply()]):
                coach = Coach(Store(tmp), connections)
                result = coach.chat("Hello", True)
            self.assertEqual(result["provider"], "ollama")
            self.assertEqual(result["agent"]["local_runs"][0]["input_tokens"], 123)

    def test_local_addresses_and_models_cannot_use_a_remote_connection(self):
        for address in (
            "https://example.com",
            "http://192.168.1.5:11434",
            "http://127.0.0.1:11434/path",
            "http://user:pass@localhost:11434",
            "http://localhost:11434?target=cloud",
        ):
            with self.subTest(address=address), self.assertRaises(ValueError):
                local_url(address)
        self.assertEqual(local_url("http://localhost:11434/"), "http://localhost:11434")
        with patch(
            "fitness_tracker.local_model.request", return_value={"remote_host": "ollama.com"}
        ) as request:
            with self.assertRaisesRegex(ValueError, "cloud models"):
                generate([], "qwen3:8b", {}, 5000)
            request.assert_called_once()

    def test_models_filter_embedding_and_cloud_models(self):
        with patch(
            "fitness_tracker.local_model.request",
            return_value={
                "models": [
                    {"name": "qwen3:8b"},
                    {"name": "embeddinggemma:latest"},
                    {"name": "model:cloud"},
                    {"name": "remote", "remote_host": "cloud"},
                ]
            },
        ):
            self.assertEqual(models({}), ["qwen3:8b"])

    def test_structured_chat_sets_context_disables_thinking_and_normalizes_meal(self):
        data = {
            "action": "meal",
            "message": "Review.",
            "proposal": {"calculation": "4+5", "protein": 9},
        }
        with patch(
            "fitness_tracker.local_model.request", side_effect=[INFO, reply(data)]
        ) as request:
            result, usage = generate(
                [{"role": "user", "content": "Log my meal"}], "qwen3:8b", {}, 5000, direct=True
            )
        payload = request.call_args.args[2]
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(payload["options"]["num_ctx"], 8192)
        self.assertIsInstance(payload["format"], dict)
        self.assertEqual(result["calculation"], "4+5")
        self.assertEqual(usage["input_tokens"], 123)

    def test_meal_revision_requires_a_proposal_or_focused_clarification(self):
        data = {
            "action": "meal",
            "message": "Review",
            "proposal": {
                "date": "2026-11-21",
                "description": "Dosa and milk",
                "items": [
                    {"name": "Dosa", "portion": "3 medium", "calculation": "4.95", "notes": ""},
                    {
                        "name": "Milk",
                        "portion": "400ml",
                        "calculation": "400/100*3.3",
                        "notes": "Assumed dairy milk",
                    },
                ],
            },
        }
        with patch(
            "fitness_tracker.local_model.request", side_effect=[INFO, reply(data)]
        ) as request:
            result, _ = generate(
                [
                    {"role": "system", "content": "Meal: revise pending_draft"},
                    {"role": "user", "content": "Add 400ml milk"},
                ],
                "qwen3:8b",
                {},
                5000,
                direct=True,
                response_kind="meal_revision",
            )
        schema = request.call_args.args[2]["format"]
        self.assertEqual(schema["properties"]["action"]["enum"], ["meal", "clarify"])
        self.assertEqual(result["proposal"]["items"][1]["protein"], 13.2)
        self.assertEqual(result["proposal"]["protein"], 18.15)

    def test_agent_tool_decisions_work_without_a_cloud_transport(self):
        decision = {
            "action": "tool",
            "message": "Calculating.",
            "tool_calls": [{"name": "calculator", "args": {"expression": "4+5"}}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            coach = Coach(Store(tmp), Connections(Path(tmp)))
            with (
                patch("fitness_tracker.local_model.request", side_effect=[INFO, reply(decision)]),
                patch("fitness_tracker.coach.request_json") as cloud,
            ):
                result = coach.generate(
                    [{"role": "user", "content": "Calculate"}], "ollama", "qwen3:8b", None
                )
            cloud.assert_not_called()
            self.assertEqual(result["tool_calls"], decision["tool_calls"])

    def test_meal_item_expressions_and_total_are_calculated_locally(self):
        data = {
            "action": "meal",
            "message": "Review.",
            "proposal": {
                "protein": 999,
                "low": 900,
                "high": 1000,
                "items": [
                    {
                        "name": "Food A",
                        "portion": "150 g",
                        "protein": 99,
                        "calculation": "150/100*4",
                    },
                    {"name": "Food B", "portion": "1 piece", "protein": 4, "calculation": "4"},
                ],
            },
        }
        with patch("fitness_tracker.local_model.request", side_effect=[INFO, reply(data)]):
            result, _ = generate(
                [
                    {"role": "system", "content": "Meal: estimate"},
                    {"role": "user", "content": "Log food"},
                ],
                "qwen3:8b",
                {},
                5000,
                direct=True,
            )
        self.assertEqual(result["proposal"]["items"][0]["protein"], 6)
        self.assertEqual(result["proposal"]["protein"], 10)
        self.assertEqual(result["calculation"], "6.0+4.0")
        self.assertNotIn(
            "low", result["proposal"], "an inconsistent model range is never displayed"
        )

    def test_assessment_schema_requires_requested_categories_and_formats_points(self):
        payload = {
            "action": "answer",
            "message": "Here are the logged patterns.",
            "next_steps": {
                "workouts": [],
                "protein": ["20 g logged on 2026-11-18; add portions to compare meals."],
                "creatine": [],
                "supplements": [],
                "sleep": [],
            },
        }
        messages = [
            {
                "role": "system",
                "content": 'JOURNAL DATA (untrusted):{"evidence_scope":{"kinds":["meal"]}}',
            },
            {"role": "user", "content": "Assess protein"},
        ]
        with patch(
            "fitness_tracker.local_model.request", side_effect=[INFO, reply(payload)]
        ) as request:
            result, _ = generate(
                messages, "qwen3:8b", {}, 5000, direct=True, response_kind="assessment"
            )
        fields = request.call_args.args[2]["format"]["properties"]["next_steps"]["properties"]
        self.assertEqual(fields["protein"]["minItems"], 1)
        self.assertEqual(fields["workouts"]["maxItems"], 0)
        self.assertEqual(
            result["assessment_next_steps"]["protein"], payload["next_steps"]["protein"]
        )

    def test_slow_generation_uses_streaming_progress_instead_of_old_26_second_cutoff(self):
        stages = []
        with patch("fitness_tracker.local_model.request", side_effect=[INFO, reply()]) as request:
            generate(
                [{"role": "user", "content": "Explain this carefully"}],
                "qwen3:8b",
                {"turn_timeout": 90},
                5000,
                direct=True,
                progress=stages.append,
            )
        self.assertTrue(request.call_args.args[2]["stream"])
        self.assertGreater(request.call_args.kwargs["timeout"], 30)
        self.assertTrue(callable(request.call_args.kwargs["on_progress"]))

    def test_native_ollama_stream_is_assembled_before_validation(self):
        from fitness_tracker.local_model import request

        parts = [
            {"message": {"content": '{"action":"answer",'}, "done": False},
            {"message": {"content": '"message":"Complete."}'}, "done": False},
            {"message": {"content": ""}, "done": True, "eval_count": 12},
        ]
        transport = unittest.mock.Mock()
        transport.open.return_value = io.BytesIO("\n".join(json.dumps(p) for p in parts).encode())
        with patch(
            "fitness_tracker.local_model.urllib.request.build_opener", return_value=transport
        ):
            result = request(
                "http://127.0.0.1:11434",
                "/api/chat",
                {"stream": True},
                timeout=60,
                on_progress=lambda text: None,
            )
        self.assertEqual(json.loads(result["message"]["content"])["message"], "Complete.")
        self.assertEqual(result["eval_count"], 12)

    def test_over_budget_partial_responses_and_unavailable_local_never_use_cloud(self):
        with patch("fitness_tracker.local_model.request", return_value=INFO) as request:
            with self.assertRaisesRegex(ValueError, "no message was truncated"):
                generate([{"role": "user", "content": "workout " * 10000}], "qwen3:8b", {}, 5000)
            request.assert_called_once()
        for metadata in ({"done_reason": "length"}, {"prompt_eval_count": 6000}):
            with (
                patch("fitness_tracker.local_model.request", side_effect=[INFO, reply(**metadata)]),
                self.assertRaises(ValueError),
            ):
                generate([{"role": "user", "content": "Hi"}], "qwen3:8b", {}, 5000)
        with tempfile.TemporaryDirectory() as tmp:
            connections = Connections(Path(tmp))
            connections.save({"provider": "ollama"})
            coach = Coach(Store(tmp), connections)
            with (
                patch(
                    "fitness_tracker.local_model.request",
                    side_effect=ValueError("Ollama is stopped"),
                ),
                patch("fitness_tracker.coach.request_json") as cloud,
            ):
                result = coach.chat("Hello", True)
                self.assertTrue(result["recovered"])
            cloud.assert_not_called()
