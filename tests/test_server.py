import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date

from fitness_tracker.server import AppServer


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = AppServer(("127.0.0.1", 0), self.temp.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def post(self, path, data, token=True, origin=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-App-Token"] = self.server.token
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(
            self.url + "/api/" + path, json.dumps(data).encode(), headers
        )
        return urllib.request.urlopen(request)

    def test_mutations_require_token_and_same_origin(self):
        for token, origin in [(False, None), (True, "https://other.example")]:
            with self.assertRaises(urllib.error.HTTPError) as e:
                self.post("profile", {}, token, origin)
            self.assertEqual(e.exception.code, 403)

    def test_transcription_is_session_protected_and_never_sends_or_saves(self):
        from unittest.mock import patch

        before = (
            self.server.store.entries(),
            self.server.store.messages(),
            self.server.store.drafts(),
        )
        with (
            patch.object(
                self.server.transcriber, "transcribe", return_value={"text": "Eight pushups"}
            ) as transcribe,
            patch.object(self.server.coach, "chat") as chat,
        ):
            for token, origin in [(False, None), (True, "https://other.example")]:
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    self.post("transcribe", {"audio": "YWJj"}, token, origin)
                self.assertEqual(caught.exception.code, 403)
            transcribe.assert_not_called()
            with self.post("transcribe", {"audio": "YWJj"}) as response:
                self.assertEqual(json.load(response), {"text": "Eight pushups"})
            chat.assert_not_called()
        self.assertEqual(
            (self.server.store.entries(), self.server.store.messages(), self.server.store.drafts()),
            before,
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post("transcribe", {"audio": "invalid"})
        self.assertEqual(caught.exception.code, 400)

    def test_new_chat_stays_empty_after_reload_and_preserves_journal(self):
        store = self.server.store
        entry = store.save(
            "meal", {"date": "2026-11-16", "description": "Test food", "protein": 10}
        )
        draft = store.draft(
            "meal", {"date": "2026-11-16", "description": "Test preview", "protein": 5}
        )
        store.message("user", {"text": "Old conversation"})
        store.message("assistant", {"text": "Old preview", "draft": draft})
        with self.post("new-chat", {}) as response:
            self.assertTrue(json.load(response)["ok"])
        for endpoint in ("state", "chat-state"):
            with urllib.request.urlopen(self.url + "/api/" + endpoint) as response:
                snapshot = json.load(response)
            self.assertEqual(snapshot["messages"], [])
            self.assertEqual(snapshot["chat_hidden_drafts"], [draft["id"]])
        self.assertEqual(store.entries(), [entry])
        self.assertEqual(store.drafts(), [draft])
        store.message("user", {"text": "New conversation"})
        self.assertEqual([m["text"] for m in store.messages()], ["New conversation"])
        with urllib.request.urlopen(self.url + "/api/export") as response:
            self.assertEqual(len(json.load(response)["messages"]), 3)

    def test_new_chat_cannot_interrupt_an_active_reply(self):
        self.server.store.message("user", {"text": "Keep this conversation"})
        with self.server.coach.lock:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.post("new-chat", {})
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(len(self.server.store.messages()), 1)

    def test_stale_session_is_rejected_before_dispatch_and_can_be_renewed(self):
        from unittest.mock import patch

        original = self.server.token
        self.server.token = "after-restart"
        req = urllib.request.Request(
            self.url + "/api/entry",
            json.dumps({"kind": "meal"}).encode(),
            {"Content-Type": "application/json", "X-App-Token": original},
        )
        with patch.object(self.server.store, "save") as save:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(req)
            self.assertEqual(json.load(caught.exception)["code"], "session_expired")
            save.assert_not_called()
        with urllib.request.urlopen(self.url + "/api/session") as response:
            self.assertEqual(json.load(response), {"token": "after-restart"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post("entry", {}, origin="https://other.example")
        self.assertNotIn("code", json.load(caught.exception))

    def test_connection_test_uses_saved_provider_without_saving_journal(self):
        from unittest.mock import patch

        result = {"ok": True, "provider": "ollama", "model": "saved-model", "latency_ms": 25}
        with patch.object(self.server.coach, "test_connection", return_value=result) as check:
            with self.post("connection-test", {"provider": "ollama"}) as response:
                self.assertEqual(json.load(response), result)
            check.assert_called_once_with("ollama", None)
        self.assertEqual(self.server.store.entries(), [])
        self.assertEqual(self.server.store.messages(), [])

    def test_chat_agreement_is_persistent_and_not_bypassed_by_request_tick(self):
        from unittest.mock import patch

        with patch.object(self.server.coach, "generate") as generate:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post("chat", {"message": "Hello", "consent": True})
            self.assertEqual(error.exception.code, 400)
            generate.assert_not_called()
        with self.post("coach-consent", {"accepted": True, "version": 1}) as response:
            self.assertTrue(json.load(response)["accepted"])
        with urllib.request.urlopen(self.url + "/api/state") as response:
            self.assertTrue(json.load(response)["coach_consent"]["accepted"])
        with patch.object(self.server.coach, "chat", return_value={"text": "Test"}) as chat:
            with self.post(
                "chat", {"message": "Hello", "consent": False, "request_id": "test-request-1"}
            ):
                pass
            self.assertIs(chat.call_args.args[1], True)
        self.server.coach.lock.acquire()
        try:
            with self.assertRaises(urllib.error.HTTPError):
                self.post("coach-consent", {"accepted": False, "version": 1})
        finally:
            self.server.coach.lock.release()
        with self.post("coach-consent", {"accepted": False, "version": 1}):
            pass
        self.assertFalse(self.server.store.coach_consent()["accepted"])

    def test_existing_server_reuse_does_not_mark_active_chat_as_failed(self):
        self.server.store.message(
            "user", {"text": "Still working", "status": "pending", "request_id": "running-chat"}
        )
        with self.assertRaises(OSError):
            AppServer(("127.0.0.1", self.server.server_port), self.temp.name)
        self.assertEqual(self.server.store.messages()[0]["status"], "pending")

    def test_invalid_host_rejected(self):
        req = urllib.request.Request(self.url + "/api/state", headers={"Host": "attacker.example"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 403)

    def test_create_edit_and_export_excludes_keys(self):
        self.server.connections.save({"ollama_model": "qwen3:4b"})
        with self.post(
            "entry",
            {
                "kind": "meal",
                "date": date.today().isoformat(),
                "description": "Lunch",
                "protein": 30,
            },
        ) as response:
            item = json.load(response)
        with self.post("entry", {**item, "protein": 35}) as response:
            self.assertEqual(json.load(response)["protein"], 35)
        with urllib.request.urlopen(self.url + "/api/export") as response:
            data = json.load(response)
        self.assertEqual(len(data["entries"]), 1)
        self.assertNotIn("private-test-key", json.dumps(data))
        with urllib.request.urlopen(self.url + "/api/state") as response:
            self.assertNotIn("private-test-key", response.read().decode())

    def test_goals_profile_api_persists_periods_and_preserves_context(self):
        with self.post("profile", {"name": "Preserved"}):
            pass
        goals = self.server.store.profile()["goals"]
        goals["protein"] = {"amount": 700, "period": 1, "unit": "week"}
        goals["workout"] = {"amount": 9, "period": 3, "unit": "week"}
        with self.post("profile", {"goals": goals}) as response:
            saved = json.load(response)
        self.assertEqual(saved["name"], "Preserved")
        with urllib.request.urlopen(self.url + "/api/state") as response:
            state = json.load(response)
        self.assertEqual(state["profile"]["goals"], goals)
        self.assertIsNone(state["insights"]["consistency"]["overall"])
        goals["workout"]["amount"] = 100
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("profile", {"goals": goals})
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(self.server.store.profile()["goals"]["workout"]["amount"], 9)

    def test_sleep_crud_and_fresh_goal_units(self):
        goals = self.server.store.profile()["supplement_goals"]
        goals["Collagen"] = {"amount": 1, "measure": "tablet", "period": 1, "unit": "day"}
        with self.post(
            "profile", {"supplement_goals": goals, "sleep_goal": 7, "night_sleep_goal": 6}
        ):
            pass
        with urllib.request.urlopen(self.url + "/api/profile") as response:
            profile = json.load(response)
        self.assertEqual(profile["supplement_goals"]["Collagen"]["measure"], "tablet")
        with self.post(
            "entry",
            {
                "kind": "sleep",
                "date": "2026-11-09",
                "hours": 7,
                "period": "night",
                "continuous_hours": 6,
            },
        ) as response:
            entry = json.load(response)
        with self.post("entry", {**entry, "hours": 8}) as response:
            self.assertEqual(json.load(response)["hours"], 8)
        self.assertEqual(len(self.server.store.entries()), 1)
        with self.post("delete", {"id": entry["id"]}):
            pass
        self.assertEqual(self.server.store.entries(), [])

    def test_path_traversal_and_security_headers(self):
        with urllib.request.urlopen(self.url + "/") as response:
            self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.url + "/%2e%2e/store.py")

    def test_invalid_values_are_client_errors(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post("entry", {"kind": "meal", "date": "bad"})
        self.assertEqual(e.exception.code, 400)

    def test_api_saves_workout_and_food_on_same_chosen_date(self):
        from test_store import workout

        for kind, raw in [
            ("workout", workout("2026-11-05")),
            ("meal", {"date": "2026-11-05", "description": "Lunch", "protein": 30}),
        ]:
            with self.post("entry", {**raw, "kind": kind}) as response:
                self.assertEqual(json.load(response)["date"], "2026-11-05")
        self.assertEqual(len(self.server.store.entries()), 2)

    def test_reset_requires_confirmation_and_keeps_keys_by_default(self):
        self.server.store.save(
            "meal", {"date": date.today().isoformat(), "description": "Lunch", "protein": 30}
        )
        self.server.connections.save({"ollama_model": "qwen3:4b"})
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("reset", {})
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(len(self.server.store.entries()), 1)
        with self.post("reset", {"confirm": "RESET"}) as response:
            self.assertTrue(json.load(response)["ok"])
        self.assertEqual(self.server.store.entries(), [])
        self.assertEqual(self.server.connections.public()["ollama_model"], "qwen3:4b")
        with self.post("reset", {"confirm": "RESET", "clear_connections": True}) as response:
            self.assertTrue(json.load(response)["ok"])
        self.assertEqual(self.server.connections.public()["ollama_model"], "qwen3:8b")

    def test_reset_waits_for_active_coach(self):
        self.server.store.save(
            "meal", {"date": date.today().isoformat(), "description": "Lunch", "protein": 30}
        )
        self.server.coach.lock.acquire()
        try:
            with self.assertRaises(urllib.error.HTTPError):
                self.post("reset", {"confirm": "RESET"})
            self.assertEqual(len(self.server.store.entries()), 1)
        finally:
            self.server.coach.lock.release()

    def test_delete_entry_removes_it_and_recalculates_progress(self):
        from test_store import workout

        entry = self.server.store.save("workout", workout())
        with self.post("delete", {"id": entry["id"]}) as response:
            self.assertTrue(json.load(response)["ok"])
        with urllib.request.urlopen(self.url + "/api/state") as response:
            state = json.load(response)
        self.assertEqual(state["entries"], [])
        self.assertEqual(state["insights"]["prs"], {})
        self.assertEqual(state["insights"]["workouts"], 0)

    def test_add_supplement_option_endpoint(self):
        with self.post("supplements", {"name": "Magnesium"}) as response:
            data = json.load(response)
        self.assertEqual(data["name"], "Magnesium")
        with urllib.request.urlopen(self.url + "/api/state") as response:
            state = json.load(response)
        self.assertIn("Magnesium", state["profile"]["supplements"])
        self.assertEqual(state["entries"], [])
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("supplements", {"name": ""})
        self.assertEqual(error.exception.code, 400)
