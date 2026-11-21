import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.coach import Coach, Connections
from fitness_tracker.store import Store, validate

DAY = "2026-11-10"
EX = "Dumbbell_Shoulder_Press"


def workout(eid=EX, reps=10):
    return {
        "date": DAY,
        "exercises": [
            {
                "exercise_id": eid,
                "tracking": "reps",
                "load_mode": "weighted",
                "sets": [{"weight": 12.5, "reps": reps}],
            }
        ],
    }


class AILoggingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.connections = Connections(Path(self.tmp.name))
        self.connections.save({})
        self.coach = Coach(self.store, self.connections)

    def test_plans_store_only_exercise_selections(self):
        entry = self.store.save("plan", workout())
        self.assertEqual(entry["exercises"], [{"exercise_id": EX}])
        self.assertNotIn("duration", entry)
        self.assertEqual(
            validate("plan", {"date": DAY, "exercises": [{"exercise_id": "Plank"}]})["exercises"],
            [{"exercise_id": "Plank"}],
        )

    def test_existing_exercise_only_plan_can_be_shared_with_coach(self):
        self.store.save("plan", {"date": DAY, "exercises": [{"exercise_id": "Plank"}]})
        with patch.object(
            self.coach, "generate", return_value={"action": "answer", "message": "Plan received."}
        ):
            response = self.coach.chat("Review my planned session", True, DAY)
        self.assertEqual(response["text"], "Plan received.")

    def test_batch_preview_rolls_back_and_approval_is_once(self):
        draft = self.store.draft(
            "batch",
            {
                "entries": [
                    {"kind": "workout", "data": workout()},
                    {"kind": "meal", "data": {"date": DAY, "description": "Eggs", "protein": 12}},
                    {
                        "kind": "supplement",
                        "data": {"date": DAY, "name": "Creatine", "amount": 5, "unit": "g"},
                    },
                ]
            },
        )
        preview = self.store.preview(draft["id"])
        self.assertEqual(len(preview["entries"]), 3)
        self.assertEqual(self.store.entries(), [])
        self.assertEqual(len(self.store.drafts()), 1)
        self.store.approve(draft["id"])
        self.assertEqual(len(self.store.entries()), 3)
        with self.assertRaises(ValueError):
            self.store.approve(draft["id"])

    def test_workout_merge_preserves_other_exercises_and_replaces_supplied_sets(self):
        old = workout()
        old["exercises"] += workout("Hammer_Curls")["exercises"]
        saved = self.store.save("workout", old)
        draft = self.store.draft("workout", workout(reps=8))
        preview = self.store.preview(draft["id"])["entries"][0]
        self.assertEqual(preview["id"], saved["id"])
        self.assertEqual(len(preview["exercises"]), 2)
        self.assertEqual(preview["exercises"][0]["sets"][0]["reps"], 8)
        self.assertEqual(self.store.entries()[0]["exercises"][0]["sets"][0]["reps"], 10)
        self.store.approve(draft["id"])
        self.assertEqual(len(self.store.entries()), 1)
        self.assertEqual(self.store.entries()[0]["exercises"][0]["sets"][0]["reps"], 8)

    def test_chat_approval_supersedes_older_workout_proposals_only(self):
        old = self.store.draft("workout", workout(reps=6))
        food = self.store.draft("meal", {"date": DAY, "description": "Eggs", "protein": 12})
        other_day = self.store.draft("workout", {**workout(), "date": "2026-11-09"})
        plan = self.store.draft("plan", workout())
        mixed = self.store.draft(
            "batch",
            {
                "entries": [
                    {"kind": "workout", "data": workout()},
                    {"kind": "meal", "data": {"date": DAY, "description": "Rice", "protein": 4}},
                ]
            },
        )
        latest = self.store.draft("workout", workout(reps=8))
        self.store.message("assistant", {"text": "Review this workout", "draft": latest})
        # Merely looking at the latest preview cannot retire the older one.
        self.store.preview(latest["id"])
        self.assertIn(old["id"], {d["id"] for d in self.store.drafts()})
        with patch.object(self.coach, "generate") as generate:
            response = self.coach.chat("I approve", True, DAY)
            generate.assert_not_called()
        self.assertEqual(response["approved"]["draft_id"], latest["id"])
        self.assertEqual(self.store.entries()[0]["exercises"][0]["sets"][0]["reps"], 8)
        self.assertEqual(
            {d["id"] for d in self.store.drafts()},
            {food["id"], other_day["id"], plan["id"], mixed["id"]},
        )
        with self.store.connect() as con:
            self.assertEqual(
                con.execute("SELECT status FROM drafts WHERE id=?", (old["id"],)).fetchone()[0],
                "superseded",
            )
        newer = self.store.draft("workout", workout(reps=12))
        reopened = Store(self.tmp.name)
        self.assertIn(newer["id"], {d["id"] for d in reopened.drafts()})
        with self.assertRaises(ValueError):
            reopened.approve(old["id"])

    def test_startup_repairs_existing_superseded_preview_without_changing_workout(self):
        old = self.store.draft("workout", workout(reps=6))
        latest = self.store.draft("workout", workout(reps=8))
        self.store.approve(latest["id"])
        # Reproduce a database written before superseding older previews was implemented.
        with self.store.connect() as con:
            con.execute("UPDATE drafts SET status='pending' WHERE id=?", (old["id"],))
        before = self.store.entries()
        reopened = Store(self.tmp.name)
        self.assertEqual(reopened.drafts(), [])
        self.assertEqual(reopened.entries(), before)
        self.assertEqual(Store(self.tmp.name).entries(), before)

    def test_approval_uses_edited_workout_date_when_superseding(self):
        original = self.store.draft("workout", workout())
        other = self.store.draft("workout", {**workout(), "date": "2026-11-09"})
        latest = self.store.draft("workout", workout(reps=8))
        self.store.approve(latest["id"], {**latest["data"], "date": "2026-11-09"})
        self.assertEqual([d["id"] for d in self.store.drafts()], [original["id"]])
        self.assertNotIn(other["id"], {d["id"] for d in Store(self.tmp.name).drafts()})

    def test_stale_preview_cannot_overwrite_intervening_changes(self):
        draft = self.store.draft("workout", workout())
        self.store.save("meal", {"date": DAY, "description": "Lunch", "protein": 20})
        with self.assertRaisesRegex(ValueError, "day changed"):
            self.store.approve(draft["id"])
        self.assertEqual(len(self.store.entries()), 1)
        self.assertEqual(len(self.store.drafts()), 1)

    def test_batch_failure_cannot_partially_save_or_register_supplements(self):
        self.store.save("sleep", {"date": DAY, "hours": 20, "period": "night"})
        draft = self.store.draft(
            "batch",
            {
                "entries": [
                    {
                        "kind": "supplement",
                        "data": {
                            "date": DAY,
                            "name": "New Test Supplement",
                            "amount": 1,
                            "unit": "tablet",
                        },
                    },
                    {"kind": "sleep", "data": {"date": DAY, "hours": 5, "period": "afternoon"}},
                ]
            },
        )
        with self.assertRaises(ValueError):
            self.store.approve(draft["id"])
        self.assertEqual(len(self.store.entries()), 1)
        self.assertNotIn("New Test Supplement", self.store.profile()["supplements"])

    def test_revert_does_not_change_completed_logs(self):
        self.store.save("workout", workout())
        before = self.store.entries()
        draft = self.store.draft("workout", workout(reps=6))
        self.store.preview(draft["id"])
        self.store.dismiss(draft["id"])
        self.assertEqual(self.store.entries(), before)

    def test_model_batch_logs_and_revision_remain_pending(self):
        reply = {
            "action": "batch",
            "message": "Review this day.",
            "proposal": {
                "entries": [
                    {"kind": "workout", "data": workout()},
                    {
                        "kind": "meal",
                        "calculation": "6+6",
                        "data": {
                            "date": DAY,
                            "description": "Eggs",
                            "protein": 12,
                            "calories": 150,
                        },
                    },
                ]
            },
        }
        with patch.object(self.coach, "generate", return_value=reply):
            original = self.coach.chat("Prepare a reviewable log for this day", True, DAY)["draft"]
        self.assertEqual(self.store.entries(), [])
        reply["proposal"]["entries"][1]["data"]["protein"] = 14
        reply["proposal"]["entries"][1]["calculation"] = "8+6"
        with patch.object(self.coach, "generate", return_value=reply) as model:
            revised = self.coach.chat(
                "Revise the pending preview", True, DAY, revise_draft_id=original["id"]
            )["draft"]
        self.assertIn("pending_draft", model.call_args.args[0][0]["content"])
        self.assertEqual([d["id"] for d in self.store.drafts()], [revised["id"]])
        self.assertEqual(self.store.entries(), [])
