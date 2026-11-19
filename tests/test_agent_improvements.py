import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.coach import Coach, Connections
from fitness_tracker.coach_workflow import simple_intake
from fitness_tracker.semantic_index import EMBED_MODEL, SemanticIndex, scope_for
from fitness_tracker.server import AppServer
from fitness_tracker.store import CATALOG, Store

DAY = "2026-11-18"
SAMPLE = (Path(__file__).parent / "fixtures" / "workout_revision.txt").read_text()


class AgentImprovementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.coach = Coach(self.store, Connections(Path(self.temp.name)))

    def test_transcript_preserves_all_sets_through_clarification_restart_and_approval(self):
        with patch.object(self.coach, "generate") as model:
            first = self.coach.chat(SAMPLE, True, DAY)
            self.assertTrue(first["workout_incomplete"])
            self.assertEqual(first["text"].count("**Needs clarification**"), 1)
            self.assertNotIn("set name, weight", first["text"])
            self.assertIn("1. Dumbbell Bicep Curl; 2. Barbell Curl; 3.", first["text"])
            with self.assertRaisesRegex(ValueError, "Resolve"):
                self.store.approve(first["draft"]["id"])
            coach = Coach(Store(self.temp.name), self.coach.connections)
            second = coach.chat(
                "Suggest changes to my pending preview for 2026-11-18, preserving the other entries. Change:\n"
                "its hanging leg raises\nexcercise is plank - each set is a time (1min) and (40s) 2 sets",
                True,
                "2026-11-19",
                revise_draft_id=first["draft"]["id"],
            )
            self.assertTrue(second["workout_incomplete"])
            final = coach.chat("option 1", True, "2026-11-19")
            model.assert_not_called()
        data = final["draft"]["data"]
        self.assertEqual(data["date"], DAY)
        self.assertEqual(sum(len(e["sets"]) for e in data["exercises"]), 23)
        rows = next(e for e in data["exercises"] if e["exercise_id"] == "Seated_Cable_Rows")
        self.assertEqual([s["reps"] for s in rows["sets"]], [9, 7, 7, 9, 7, 7])
        plank = next(e for e in data["exercises"] if e["exercise_id"] == "Plank")
        self.assertEqual([s["seconds"] for s in plank["sets"]], [60, 40])
        self.assertNotIn("workout_incomplete", final)
        self.assertEqual(len(self.store.drafts()), 1)
        self.assertEqual(self.store.entries(), [])
        result = coach.chat("I approve", True)
        self.assertIn("approved", result)
        self.assertEqual(len(self.store.entries()), 1)

    def test_exact_log_plan_starter_with_any_mode_uses_workout_stages_for_november_17(self):
        source = "Help me log or plan my workout.\n" + SAMPLE[SAMPLE.index("1. lat") :]
        self.store.coach_state(value={"awaiting_mode": True, "date": "2026-11-19"})
        stages = []
        with patch.object(
            self.coach,
            "generate",
            side_effect=AssertionError("Workout source must not need generative copying"),
        ):
            reply = self.coach.chat(
                source, True, "2026-11-17", logging_kind="any", progress=stages.append
            )
        self.assertEqual(reply["draft"]["kind"], "workout")
        self.assertEqual(reply["draft"]["data"]["date"], "2026-11-17")
        self.assertEqual(sum(len(e["sets"]) for e in reply["draft"]["data"]["exercises"]), 19)
        self.assertTrue(reply["workout_incomplete"])
        self.assertNotIn("Help me log or plan", reply["text"])
        self.assertTrue(any("retrieval batch" in e["message"] for e in stages))
        self.assertEqual(self.store.entries(), [])

    def test_both_confirmed_movements_update_together_and_keep_twenty_three_sets(self):
        source = "Help me log or plan my workout.\n" + SAMPLE[SAMPLE.index("1. lat") :]
        first = self.coach.chat(source, True, "2026-11-17", logging_kind="any")
        result = self.coach.chat(
            "Standing biceps curls used dumbbells. The leg raises were hanging leg raises.",
            True,
            "2026-11-19",
            revise_draft_id=first["draft"]["id"],
        )
        self.assertEqual(result["draft"]["data"]["date"], "2026-11-17")
        self.assertNotIn("workout_incomplete", result)
        ids = {ex["exercise_id"] for ex in result["draft"]["data"]["exercises"]}
        self.assertIn("Dumbbell_Bicep_Curl", ids)
        self.assertIn("Hanging_Leg_Raise", ids)
        self.assertEqual(sum(len(ex["sets"]) for ex in result["draft"]["data"]["exercises"]), 23)
        self.assertEqual(self.store.entries(), [])

    def test_semantic_shortlist_cannot_substitute_a_shoulder_press_for_leg_raises(self):
        from fitness_tracker.exercise_matching import rank_exercises

        fake = unittest.mock.Mock()
        fake.search.return_value = [
            {
                "id": "exercise:Standing_Dumbbell_Press",
                "retrieval": "semantic + keyword",
                "score": 0.9,
            },
            {"id": "exercise:Hanging_Leg_Raise", "retrieval": "semantic + keyword", "score": 0.6},
        ]
        choices = rank_exercises("standing leg raise", retriever=fake)
        self.assertIn("Hanging_Leg_Raise", choices)
        self.assertNotIn("Standing_Dumbbell_Press", choices)

    def test_failed_workout_request_resumes_without_duplicate_user_or_journal_entries(self):
        source = "Help me log or plan my workout.\n" + SAMPLE[SAMPLE.index("1. lat") :]
        self.store.message(
            "user",
            {
                "text": source,
                "status": "failed",
                "request_id": "failed-workout-17",
                "logging_kind": "any",
            },
        )
        reply = self.coach.chat(source, True, "2026-11-17", "failed-workout-17", logging_kind="any")
        self.assertEqual(reply["draft"]["data"]["date"], "2026-11-17")
        self.assertEqual(len(self.store.messages()), 2)
        self.assertEqual(self.store.messages()[0]["status"], "sent")
        replay = self.coach.chat(
            source, True, "2026-11-17", "failed-workout-17", logging_kind="any"
        )
        self.assertEqual(replay["draft"]["id"], reply["draft"]["id"])
        self.assertEqual(len(self.store.drafts()), 1)
        self.assertEqual(self.store.entries(), [])

    def test_named_date_preserves_the_seventeenth_instead_of_selected_day(self):
        with patch.object(self.coach, "generate") as model:
            reply = self.coach.chat(
                "Log my workout for 17th Nov: Plank 1min + 40s",
                True,
                "2026-11-19",
                logging_kind="any",
            )
            model.assert_not_called()
        self.assertEqual(reply["draft"]["data"]["date"], "2026-11-17")
        self.assertEqual(
            [s["seconds"] for s in reply["draft"]["data"]["exercises"][0]["sets"]], [60, 40]
        )

    def test_unavailable_local_model_returns_a_recoverable_chat_turn(self):
        from fitness_tracker.coach import ProviderError

        with patch.object(
            self.coach, "generate", side_effect=ProviderError("Local connection unavailable")
        ):
            reply = self.coach.chat("Help me with this meal", True, DAY)
        self.assertTrue(reply["recovered"])
        self.assertEqual(reply["action"], "clarify")
        self.assertEqual(self.store.messages()[0]["status"], "sent")
        self.assertEqual(self.store.entries(), [])

    def test_failed_embedding_batch_falls_back_once_for_all_terms(self):
        index = SemanticIndex(self.store)
        index.enabled = True
        with self.store.connect() as con:
            con.execute("UPDATE coach_chunks SET vector='[1,0]',model=?", (EMBED_MODEL,))
        with patch.object(
            index, "embed", side_effect=ValueError("Temporarily unavailable")
        ) as embed:
            index.prefetch(["plank", "hammer curl", "plank"])
            index.search("plank", category="exercise")
            index.search("hammer curl", category="exercise")
            embed.assert_called_once()

    def test_workout_starter_clarifies_mode_before_collecting_sets(self):
        with patch.object(self.coach, "generate") as model:
            response = self.coach.chat("Help me log or plan my workout.", True, DAY)
            model.assert_not_called()
        self.assertEqual(response["action"], "clarify")
        self.assertIn("completed workout or planning", response["text"])
        self.assertTrue(self.store.coach_state()["awaiting_mode"])
        with patch.object(
            self.coach,
            "generate",
            return_value={
                "action": "plan",
                "message": "Review.",
                "proposal": {"date": DAY, "exercises": [{"exercise_id": "Plank"}]},
            },
        ):
            planned = self.coach.chat("It is a plan: plank", True, DAY)
        self.assertEqual(planned["draft"]["kind"], "plan")
        self.assertNotIn("sets", planned["draft"]["data"]["exercises"][0])
        self.assertEqual(self.store.entries(), [])

    def test_conversation_recall_outlives_short_window_and_resets_with_new_chat(self):
        with patch.object(
            self.coach, "generate", return_value={"action": "answer", "message": "Understood."}
        ):
            self.coach.chat("The protein on my bread label is 7 grams per slice.", True, DAY)
            for index in range(5):
                self.coach.chat(f"Thanks, unrelated exchange {index}", True, DAY)
        with patch.object(
            self.coach,
            "generate",
            return_value={"action": "answer", "message": "You said 7 grams."},
        ) as model:
            self.coach.chat("What did I say about the bread label?", True, DAY)
        self.assertIn("7 grams per slice", str(model.call_args.args[0]))
        self.assertEqual(self.coach.retrieval.search("bread"), [])
        self.store.start_chat()
        self.assertEqual(self.coach.retrieval.search("bread", category="conversation"), [])

    def test_topic_change_dismisses_preview_and_cannot_approve_stale_reference(self):
        draft = self.coach.chat("Log my workout: Plank 40s", True, DAY)["draft"]
        with (
            patch.object(
                self.coach, "generate", return_value={"action": "answer", "message": "A form cue."}
            ),
            patch("fitness_tracker.tutorial_search.find_tutorial", return_value=[]),
        ):
            response = self.coach.chat("Help me learn this exercise: hammer curls", True, DAY)
        self.assertIn("Reverted", response["text"])
        self.assertEqual(self.store.drafts(), [])
        self.assertEqual(self.store.entries(), [])
        with self.assertRaises(ValueError):
            self.store.approve(draft["id"])

    def test_estimate_does_not_authorize_a_meal_draft(self):
        with patch.object(
            self.coach,
            "generate",
            return_value={
                "action": "meal",
                "message": "About 10 g protein.",
                "calculation": "10",
                "proposal": {"date": DAY, "description": "Food", "protein": 10},
            },
        ):
            response = self.coach.chat("Estimate protein in my food", True, DAY)
        self.assertEqual(response["action"], "answer")
        self.assertNotIn("draft", response)
        self.assertEqual(self.store.drafts(), [])

    def test_goal_aware_shorthand_and_optional_sleep_data(self):
        names = ["Vitamin C", "Vitamin D", "Vitamin B12"]
        self.store.save_profile(
            {
                "supplement_goals": {
                    name: {"amount": 1, "measure": "tablet", "period": 1, "unit": "day"}
                    for name in names
                }
            }
        )
        with patch.object(self.coach, "generate") as model:
            result = self.coach.chat("I took vitc, d and b12", True, DAY)
            model.assert_not_called()
        entries = result["draft"]["data"]["entries"]
        self.assertEqual({e["data"]["name"] for e in entries}, set(names))
        self.assertTrue(
            all(e["data"]["unit"] == "tablet" and e["data"]["amount"] == 1 for e in entries)
        )
        for message, hours, continuous in [("nap 2hrs", 2, None), ("night 7hrs 5 uniter", 7, 5)]:
            reply = simple_intake(message, DAY, self.store.profile())
            self.assertEqual(reply["proposal"]["hours"], hours)
            self.assertEqual(reply["proposal"].get("continuous_hours"), continuous)
            self.store.start_chat()
            with patch.object(self.coach, "generate") as model:
                chat_reply = self.coach.chat(message, True, DAY)
                model.assert_not_called()
            self.assertEqual(chat_reply["draft"]["data"]["hours"], hours)
            self.assertEqual(chat_reply["draft"]["data"].get("continuous_hours"), continuous)
        reply = simple_intake("I took vitc 2 tablets and vitamin D", DAY, self.store.profile())
        self.assertEqual([e["data"]["amount"] for e in reply["proposal"]["entries"]], [1, 2])
        self.assertIsNone(simple_intake("I took vitc and creatine", DAY, self.store.profile()))

    def test_assessment_observations_cannot_inherit_false_goal_claims(self):
        from fitness_tracker.coach_workflow import format_assessment, scope_statistics

        self.store.save("meal", {"date": DAY, "description": "Meal", "protein": 30})
        context = self.coach.context(DAY, {"start": DAY, "end": DAY})
        context["scope_totals"] = scope_statistics(self.store.entries())
        result = format_assessment(
            context,
            {
                "protein": ["You met your goal; maintain current intake."],
                "supplements": ["Consider adding targeted support."],
            },
        )
        self.assertIn("30 g", result)
        self.assertIn("120 g per day", result)
        self.assertNotIn("met your goal", result)
        self.assertNotIn("adding targeted support", result)

    def test_assessment_yes_uses_date_category_scope_and_older_records(self):
        self.store.save("meal", {"date": "2026-01-01", "description": "Tofu", "protein": 20})
        self.store.save("meal", {"date": DAY, "description": "Eggs", "protein": 12})
        self.store.save("sleep", {"date": DAY, "hours": 7, "period": "night"})
        start = self.coach.chat("Assess my progress", True, DAY)
        self.assertIn("How shall we begin?", start["text"])
        with patch.object(
            self.coach,
            "generate",
            return_value={"action": "answer", "message": "**Protein:** 20 g on January 1."},
        ) as model:
            result = self.coach.chat("Yes, protein on 2026-01-01", True, DAY)
        prompt = str(model.call_args.args[0])
        self.assertIn("Tofu", prompt)
        self.assertIn('"protein_g_per_logged_day":20.0', prompt)
        self.assertNotIn('"description":"Eggs"', prompt)
        self.assertEqual(
            result["evidence_scope"],
            {"start": "2026-01-01", "end": "2026-01-01", "kinds": ["meal"]},
        )
        self.assertEqual({e["kind"] for e in result["retrieved_entries"]}, {"meal"})
        self.assertEqual(
            scope_for("more detail", DAY, result["evidence_scope"]), result["evidence_scope"]
        )
        self.assertNotIn("start", scope_for("overall", DAY, result["evidence_scope"]))

    def test_index_tracks_saves_edits_deletes_and_never_indexes_pending_drafts(self):
        index = SemanticIndex(self.store)
        with self.store.connect() as con:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM coach_chunks").fetchone()[0], len(CATALOG)
            )
        draft = self.store.draft("meal", {"date": DAY, "description": "Tofu", "protein": 20})
        self.assertEqual(index.search("tofu"), [])
        saved = self.store.approve(draft["id"])
        self.assertIn("Tofu", index.search("tofu")[0]["content"])
        self.store.save("meal", {**saved, "description": "Paneer"}, saved["id"])
        self.assertIn("Paneer", index.search("paneer")[0]["content"])
        with patch.object(index, "embed", return_value=[[1.0, 0.0]] * 16):
            self.assertEqual(index.index_pending(), 16)
        index.enabled = True
        with patch.object(index, "embed", return_value=[[1.0, 0.0]]):
            results = index.search("exercise", category="exercise", limit=3)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r["retrieval"] == "semantic + keyword" for r in results))
        self.store.delete(saved["id"])
        self.assertEqual(index.search("paneer"), [])
        self.store.reset()
        self.assertEqual(index.search("food"), [])

    def test_index_does_not_restore_an_entry_deleted_during_embedding(self):
        entry = self.store.save("meal", {"date": DAY, "description": "Tofu", "protein": 20})
        index = SemanticIndex(self.store)
        with self.store.connect() as con:
            con.execute(
                "UPDATE coach_chunks SET vector='[1,0]',model=? WHERE category='exercise'",
                (EMBED_MODEL,),
            )

        def embed(texts, timeout):
            self.store.delete(entry["id"])
            return [[1.0, 0.0]]

        with patch.object(index, "embed", side_effect=embed):
            index.index_pending()
        self.assertEqual(index.search("tofu"), [])


class StreamingTests(unittest.TestCase):
    def test_first_stage_arrives_before_slow_answer_and_final_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = AppServer(("127.0.0.1", 0), tmp)
            server.store.set_coach_consent(True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:

                def generate(*args, **kwargs):
                    time.sleep(0.2)
                    return {"action": "answer", "message": "Ready."}

                body = {"message": "Hello", "stream": True, "request_id": "stream-test-1119"}
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/chat",
                    json.dumps(body).encode(),
                    headers={"Content-Type": "application/json", "X-App-Token": server.token},
                )
                with (
                    patch.object(server.coach, "generate", side_effect=generate),
                    urllib.request.urlopen(request) as response,
                ):
                    self.assertIn("ndjson", response.headers["Content-Type"])
                    first = json.loads(response.readline())
                    self.assertEqual(first["type"], "stage")
                    self.assertFalse(any(m["role"] == "assistant" for m in server.store.messages()))
                    events = [json.loads(line) for line in response]
                self.assertEqual(events[-1]["type"], "final")
                self.assertEqual(events[-1]["response"]["text"], "Ready.")
                self.assertEqual(server.store.entries(), [])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
