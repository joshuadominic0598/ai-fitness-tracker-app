"""Regression coverage for mixed session previews and scoped nutrition/cardio reviews."""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.cardio import ACTIVITY_NAMES
from fitness_tracker.chat_actions import (
    meal_portion_revision,
    requested_log_kind,
    require_meal_calories,
)
from fitness_tracker.coach import Coach, Connections
from fitness_tracker.coach_workflow import merge_revision, strength_categories
from fitness_tracker.local_model import generate
from fitness_tracker.prompt_budget import chat_topics
from fitness_tracker.semantic_index import scope_for
from fitness_tracker.store import Store, insights, validate

DAY = "2026-11-21"


def session(reps=10, exercise="Pushups"):
    return {
        "date": DAY,
        "exercises": [{"exercise_id": exercise, "sets": [{"weight": 0, "reps": reps}]}],
    }


def cardio(minutes, intensity="moderate", activity="Running"):
    return {"date": DAY, "activity": activity, "minutes": minutes, "intensity": intensity}


class PR3ReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(temp.name)
        self.coach = Coach(self.store, Connections(Path(temp.name)))

    def mixed_preview(self):
        return self.store.draft(
            "batch",
            {
                "entries": [
                    {"kind": "cardio", "data": cardio(20)},
                    {"kind": "cardio", "data": cardio(10, "high")},
                    {"kind": "home_workout", "data": session(10)},
                    {"kind": "home_workout", "data": session(20)},
                ]
            },
        )

    def test_mixed_home_and_creatine_model_batch_cannot_change_gym_records(self):
        gym = self.store.save("workout", session(5))
        reply = {
            "action": "batch",
            "message": "Review",
            "proposal": {
                "entries": [
                    {"kind": "workout", "data": session(10)},
                    {"kind": "creatine", "data": {"date": DAY, "amount": 3, "unit": "g"}},
                ]
            },
        }
        with patch.object(self.coach, "generate", return_value=reply):
            result = self.coach.chat(
                "Log home pushups 10 reps and creatine 3g",
                True,
                DAY,
                logging_kind="home_workout",
            )
        self.assertEqual(
            [item["kind"] for item in result["draft"]["data"]["entries"]],
            ["home_workout", "creatine"],
        )
        self.coach.chat("I approve", True, DAY)
        self.assertEqual(next(e for e in self.store.entries() if e["kind"] == "workout"), gym)
        self.assertEqual(len([e for e in self.store.entries() if e["kind"] == "home_workout"]), 1)
        self.assertEqual(insights(self.store.entries(), self.store.profile())["workouts"], 1)

    def test_explicit_gym_and_home_sessions_keep_their_categories(self):
        proposal = {
            "entries": [
                {"kind": "workout", "data": session(10)},
                {"kind": "workout", "data": session(20, "Sit-Up")},
            ]
        }
        kind, corrected = strength_categories(
            "batch",
            proposal,
            "Log at home: Pushups 10 reps; gym workout: Sit-Up 20 reps",
            "home_workout",
        )
        draft = self.store.draft(kind, corrected)
        saved = self.store.approve(draft["id"])["entries"]
        self.assertEqual([e["kind"] for e in saved], ["home_workout", "workout"])
        with patch.object(
            self.coach,
            "generate",
            return_value={"action": "batch", "message": "Review", "proposal": proposal},
        ) as model:
            result = self.coach.chat(
                "Log at home: Pushups 10 reps; gym workout: Sit-Up 20 reps",
                True,
                DAY,
                logging_kind="home_workout",
            )
        model.assert_called_once()
        self.assertEqual(
            [e["kind"] for e in result["draft"]["data"]["entries"]], ["home_workout", "workout"]
        )
        with self.assertRaisesRegex(ValueError, "clearly labelled"):
            strength_categories("batch", proposal, "Log home and gym workout today", "home_workout")

    def test_reordered_corrections_preserve_all_repeated_sessions_and_ids(self):
        gym = self.store.save("workout", session(5))
        original = self.mixed_preview()
        reopened = Store(self.store.directory)
        self.assertEqual(reopened.drafts()[0], original)
        entries = original["data"]["entries"]
        self.assertEqual(len({e["item_id"] for e in entries}), 4)
        updates = deepcopy(entries)
        updates[0]["data"]["minutes"] = 25
        updates[1]["data"]["minutes"] = 15
        updates[2]["data"]["exercises"][0]["sets"][0]["reps"] = 12
        updates[3]["data"]["exercises"][0]["sets"][0]["reps"] = 22
        revised = merge_revision(
            original, "batch", {"entries": list(reversed(updates))}, "Update sessions"
        )
        new_draft = reopened.draft("batch", revised)
        self.assertEqual(
            [e["item_id"] for e in new_draft["data"]["entries"]], [e["item_id"] for e in entries]
        )
        saved = reopened.approve(new_draft["id"])["entries"]
        self.assertEqual(
            [(e["minutes"], e["intensity"]) for e in saved if e["kind"] == "cardio"],
            [(25, "moderate"), (15, "high")],
        )
        self.assertEqual(
            [e["exercises"][0]["sets"][0]["reps"] for e in saved if e["kind"] == "home_workout"],
            [12, 22],
        )
        self.assertEqual(next(e for e in reopened.entries() if e["kind"] == "workout"), gym)

    def test_partial_session_correction_keeps_other_sessions_and_original_category(self):
        original = self.mixed_preview()
        update = deepcopy(original["data"]["entries"][3])
        update["kind"] = (
            "workout"  # The model must not turn an existing home session into gym work.
        )
        update["data"]["exercises"][0]["sets"][0]["reps"] = 25
        kind, proposal = strength_categories(
            "batch", {"entries": [update]}, "Change second home session to 25 reps", "any", original
        )
        revised = merge_revision(original, kind, proposal, "Change second home session to 25 reps")
        self.assertEqual(revised["entries"][:3], original["data"]["entries"][:3])
        self.assertEqual(revised["entries"][3]["kind"], "home_workout")
        self.assertEqual(revised["entries"][3]["data"]["exercises"][0]["sets"][0]["reps"], 25)

    def test_ambiguous_unknown_and_duplicate_session_updates_are_rejected(self):
        original = self.mixed_preview()
        update = deepcopy(original["data"]["entries"][1])
        for item, pattern in [
            ({k: v for k, v in update.items() if k != "item_id"}, "Several sessions"),
            ({**update, "item_id": "f" * 32}, "does not match"),
        ]:
            with self.subTest(pattern=pattern), self.assertRaisesRegex(ValueError, pattern):
                merge_revision(
                    original, "batch", {"entries": [item]}, "Change running to 30 minutes"
                )
        with self.assertRaisesRegex(ValueError, "corrected twice"):
            merge_revision(original, "batch", {"entries": [update, update]}, "Update running")
        with self.assertRaisesRegex(ValueError, "included twice"):
            self.store.draft("batch", {"entries": [update, update]})
        self.assertEqual(self.store.drafts()[0], original)

    def test_legacy_batches_receive_stable_ids_without_rewriting_saved_data(self):
        original = self.mixed_preview()
        legacy = deepcopy(original["data"])
        for item in legacy["entries"]:
            item.pop("item_id")
        with self.store.connect() as con:
            con.execute("UPDATE drafts SET data=? WHERE id=?", (json.dumps(legacy), original["id"]))
        first = self.store.drafts()[0]
        self.assertEqual(first, self.store.drafts()[0])
        with self.store.connect() as con:
            raw = json.loads(
                con.execute("SELECT data FROM drafts WHERE id=?", (original["id"],)).fetchone()[0]
            )
        self.assertNotIn("item_id", raw["entries"][0])

    def test_chat_correction_uses_session_ids_and_keeps_ambiguous_preview_pending(self):
        original = self.mixed_preview()
        self.store.message(
            "user", {"text": "Log my running and home sessions", "logging_kind": "any"}
        )
        self.store.message("assistant", {"text": "Review", "action": "batch", "draft": original})
        update = deepcopy(original["data"]["entries"][1])
        update["data"]["minutes"] = 18
        with patch.object(
            self.coach,
            "generate",
            return_value={
                "action": "batch",
                "message": "Review",
                "proposal": {"entries": [update]},
            },
        ) as model:
            result = self.coach.chat(
                "Change the second running session to 18 minutes",
                True,
                DAY,
                revise_draft_id=original["id"],
            )
        prompt = model.call_args.args[0][0]["content"]
        self.assertIn(update["item_id"], prompt)
        self.assertIn("Copy its exact item_id", prompt)
        revised = result["draft"]
        self.assertEqual([e["data"]["minutes"] for e in revised["data"]["entries"][:2]], [20, 18])
        update.pop("item_id")
        with patch.object(
            self.coach,
            "generate",
            return_value={
                "action": "batch",
                "message": "Review",
                "proposal": {"entries": [update]},
            },
        ):
            failed = self.coach.chat(
                "Change running to 19 minutes", True, DAY, revise_draft_id=revised["id"]
            )
        self.assertEqual(failed["draft"], revised)
        self.assertEqual(failed["action"], "clarify")
        self.assertEqual(self.store.drafts(), [revised])
        self.assertEqual(self.store.entries(), [])

    def test_explicit_addition_retains_repeated_original_sessions(self):
        original = self.mixed_preview()
        added = {"kind": "cardio", "data": cardio(5)}
        revised = merge_revision(
            original,
            "batch",
            {"entries": [added]},
            "Add another running session, 5 moderate minutes",
        )
        self.assertEqual(revised["entries"][:4], original["data"]["entries"])
        self.assertEqual(revised["entries"][4], added)

    def test_all_cardio_activities_and_aliases_are_in_mixed_scopes(self):
        for activity in [*ACTIVITY_NAMES, "swam", "cycled", "aerobics"]:
            with self.subTest(activity=activity):
                message = f"Review my {activity} and sleep this week"
                self.assertEqual(scope_for(message, DAY)["kinds"], ["cardio", "sleep"])
                self.assertIn("cardio", chat_topics(message))

    def test_assessments_show_exact_scoped_cardio_calories_and_missing_values(self):
        self.store.save("cardio", cardio(30, activity="Tennis"))
        self.store.save("cardio", cardio(15, "high", "Tennis"))
        self.store.save("cardio", {**cardio(100), "date": "2026-01-01"})
        self.store.save(
            "meal", {"date": DAY, "description": "Eggs", "protein": 12, "calories": 150}
        )
        self.store.save("meal", {"date": DAY, "description": "Milk", "protein": 6})
        self.store.save(
            "meal",
            {"date": "2026-01-01", "description": "Old food", "protein": 100, "calories": 1000},
        )
        self.store.save("sleep", {"date": DAY, "hours": 7, "period": "night"})
        with patch.object(
            self.coach,
            "generate",
            return_value={"action": "answer", "message": "Review", "assessment_next_steps": {}},
        ):
            cardio_review = self.coach.chat("Review my tennis and sleep this week", True, DAY)
            meal_review = self.coach.chat("Review my calories this week", True, DAY)
        self.assertEqual(cardio_review["evidence_scope"]["kinds"], ["cardio", "sleep"])
        self.assertIn("30 moderate minutes; 15 high-intensity minutes", cardio_review["text"])
        self.assertIn("60 moderate-equivalent minutes", cardio_review["text"])
        self.assertIn("7 h", cardio_review["text"])
        self.assertNotIn("**Calories:**", cardio_review["text"])
        self.assertIn("150 kcal", meal_review["text"])
        self.assertIn("1 meal missing calories", meal_review["text"])
        self.assertIn("total is incomplete", meal_review["text"])
        self.assertNotIn("1000 kcal", meal_review["text"])
        self.assertNotIn("**Cardio**", meal_review["text"])

    def test_local_assessment_schema_supports_cardio_calories_and_home_training(self):
        info = {"capabilities": ["completion"]}
        reply = {
            "message": {
                "content": json.dumps({"action": "answer", "message": "Review", "next_steps": {}})
            }
        }
        for kinds, required in [
            (["cardio", "sleep"], {"cardio", "sleep"}),
            (["meal"], {"protein", "calories"}),
            (["home_workout"], {"workouts"}),
        ]:
            messages = [
                {
                    "role": "system",
                    "content": "JOURNAL DATA (untrusted):"
                    + json.dumps({"evidence_scope": {"kinds": kinds}}),
                },
                {"role": "user", "content": "Review selected records"},
            ]
            with (
                self.subTest(kinds=kinds),
                patch("fitness_tracker.local_model.request", side_effect=[info, reply]) as request,
            ):
                generate(messages, "qwen3:8b", {}, 5000, direct=True, response_kind="assessment")
            fields = request.call_args.args[2]["format"]["properties"]["next_steps"]["properties"]
            self.assertEqual(
                {key for key, value in fields.items() if value["minItems"] == 1}, required
            )

    def test_copilot_location_and_calorie_fixes_cover_followups_and_legacy_meals(self):
        history = [{"role": "user", "text": "I did a home workout with 10 pushups"}]
        self.assertEqual(requested_log_kind("Yes, log it", history), "home_workout")
        self.assertEqual(requested_log_kind("Log it at the gym", history), "workout")
        legacy = {"protein": 6, "items": [{"name": "Milk", "portion": "200 ml", "protein": 6}]}
        self.assertIsNone(meal_portion_revision("Change milk to 400ml", legacy))
        for missing in [None, ""]:
            meal = {"date": DAY, "description": "Milk", "protein": 6, "calories": missing}
            with (
                self.subTest(missing=missing),
                self.assertRaisesRegex(ValueError, "Estimate calories"),
            ):
                require_meal_calories(meal)
        require_meal_calories({"date": DAY, "description": "Milk", "protein": 6, "calories": 100})
        self.assertNotIn(
            "calories",
            validate(
                "meal", {"date": DAY, "description": "Manual milk", "protein": 6, "calories": ""}
            ),
        )
