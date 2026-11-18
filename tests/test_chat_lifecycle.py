import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.coach import Coach, Connections, ProviderError
from fitness_tracker.store import Store


class ChatLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.connections = Connections(Path(self.temp.name))
        self.connections.save({"ollama_model": "qwen3:8b"})
        self.coach = Coach(self.store, self.connections)

    def test_persistent_agreement_revocation_and_reset(self):
        self.assertFalse(self.store.coach_consent()["accepted"])
        self.store.set_coach_consent(True, 1)
        self.assertTrue(Store(self.temp.name).coach_consent()["accepted"])
        self.assertEqual(self.store.coach_consent()["providers"], ["ollama"])
        self.store.set_coach_consent(False, 1)
        self.assertFalse(self.store.coach_consent()["accepted"])
        self.store.set_coach_consent(True, 1)
        self.store.reset()
        self.assertFalse(self.store.coach_consent()["accepted"])
        with self.assertRaises(ValueError):
            self.store.set_coach_consent(True, 2)

    def test_user_message_is_stored_before_generation_and_replay_is_cached(self):
        started = threading.Event()
        release = threading.Event()

        def generate(*args, **kwargs):
            started.set()
            release.wait(3)
            return {"action": "answer", "message": "A considered answer."}

        with (
            patch.object(self.coach, "generate", side_effect=generate) as model,
            patch("fitness_tracker.coach.web_search", return_value=[]),
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            pending = pool.submit(self.coach.chat, "A test question", True, None, "request-id-123")
            self.assertTrue(started.wait(2))
            messages = self.store.messages()
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["status"], "pending")
            self.assertEqual(messages[0]["text"], "A test question")
            release.set()
            result = pending.result(timeout=3)
            count = model.call_count
            cached = self.coach.chat("A test question", True, None, "request-id-123")
            self.assertEqual(cached["text"], result["text"])
            self.assertEqual(model.call_count, count)
        self.assertEqual(len(self.store.messages()), 2)
        self.assertEqual(self.store.messages()[0]["status"], "sent")
        self.assertEqual(self.store.entries(), [])

    def test_model_recovery_and_interrupted_turn_stay_visible_without_fitness_writes(self):
        with patch.object(self.coach, "generate", side_effect=ProviderError("Quota reached")):
            result = self.coach.chat("My meal", True)
            self.assertTrue(result["recovered"])
        self.assertEqual(self.store.messages()[0]["status"], "sent")
        self.assertEqual(self.store.entries(), [])
        self.store.message(
            "user", {"text": "Interrupted", "status": "pending", "request_id": "old-request"}
        )
        self.store.recover_chat_requests()
        self.assertEqual(self.store.messages()[-1]["status"], "failed")
