import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.coach import Coach, Connections, ProviderError
from fitness_tracker.store import Store, validate
from fitness_tracker.workout_notes import (
    check_coverage,
    clean_diary,
    combine_source,
    ground_proposal,
    inventory,
)

# Synthetic fixture: repeated timestamps and varied line structures, no personal journal data.
NOTE = """[01/02/26, 1:00 PM] Athlete: hammer curl 10kg 9 reps
Tricep pushdown 17.5kg 9 reps
[01/02/26, 1:05 PM] Athlete: Chest fly 12.5kg, 6 reps and 3 reps
Then 10kg, 8 reps
Tricep pushdown 17.5kg 7 reps
[01/02/26, 1:10 PM] Athlete: Bench press 12.5kg 9 reps
Tricep pushdown drop set 17.5kg 7 reps 12.5kg 4 reps
Bench press 17.5kg 5 reps
Tricep up rope 3, 8 reps
Bench 17.5kg 5 reps
Bench close grip 10kg 7reps
Tricep rope up, 8kg, did 6 reps, then 2 reps
35kg leg extension 9
55kg leg extension 5 reps
45kg 9 reps
leg curl 30kg 5 reps, Then 20kg did like 11 reps to close
Tricep down 10kg, 11 reps"""
CLARIFY = "Rope plate 3 is 8kg. Chest fly was a machine. Leg curl was lying down."
IDS = [
    "Hammer_Curls",
    "Triceps_Pushdown",
    "Butterfly",
    "Barbell_Bench_Press_-_Medium_Grip",
    "Cable_Rope_Overhead_Triceps_Extension",
    "Close-Grip_Barbell_Bench_Press",
    "Leg_Extensions",
    "Lying_Leg_Curls",
]
SETS = [
    [(10, 9)],
    [(17.5, 9), (17.5, 7), (17.5, 7), (12.5, 4), (10, 11)],
    [(12.5, 6), (12.5, 3), (10, 8)],
    [(12.5, 9), (17.5, 5), (17.5, 5)],
    [(8, 8), (8, 6), (8, 2)],
    [(10, 7)],
    [(35, 9), (55, 5), (45, 9)],
    [(30, 5), (20, 11)],
]


def proposal():
    return {
        "date": "2026-02-01",
        "exercises": [
            {
                "exercise_id": eid,
                "tracking": "reps",
                "load_mode": "weighted",
                "sets": [{"weight": w, "reps": r, "seconds": 0} for w, r in sets],
            }
            for eid, sets in zip(IDS, SETS)
        ],
    }


class WorkoutNoteTests(unittest.TestCase):
    def test_metadata_is_removed_and_all_twenty_one_sets_remain(self):
        clean = clean_diary(NOTE)
        self.assertNotIn("Athlete", clean)
        self.assertNotIn("1:05", clean)
        source = inventory(NOTE + "\nClarifications: " + CLARIFY)
        self.assertEqual(source["unresolved"], [])
        self.assertEqual(
            [[(s["weight"], s["reps"]) for s in g["sets"]] for g in source["groups"]], SETS
        )
        self.assertEqual(sum(len(g["sets"]) for g in source["groups"]), 21)
        check_coverage(NOTE + "\nClarifications: " + CLARIFY, proposal())

    def test_source_uncertainty_requires_clarification_not_assumed_kg(self):
        source = inventory(NOTE)
        self.assertEqual(len(source["unresolved"]), 3)
        self.assertEqual(sum(len(g["sets"]) for g in source["groups"]), 20)

    def test_grounding_preserves_source_numbers_and_repeated_sets(self):
        generated = proposal()
        generated["exercises"][3]["sets"] = [{"weight": 100, "reps": 1, "seconds": 0}]
        generated["exercises"][0]["exercise_id"] = "hammer_curl"
        grounded = ground_proposal(NOTE + "\nClarifications: " + CLARIFY, generated)
        self.assertEqual(
            [[(s["weight"], s["reps"]) for s in e["sets"]] for e in grounded["exercises"]],
            SETS,
        )
        self.assertEqual(grounded["exercises"][0]["exercise_id"], "Hammer_Curls")
        generated["exercises"].append({"exercise_id": "Dumbbell_Shoulder_Press", "sets": []})
        with self.assertRaisesRegex(ValueError, "outside the source"):
            ground_proposal(NOTE + "\nClarifications: " + CLARIFY, generated)

    def test_bench_variants_require_explicit_equipment(self):
        for note, expected in [
            ("Bench close grip 10kg 8 reps", "Close-Grip_Barbell_Bench_Press"),
            ("Smith bench close grip 10kg 8 reps", "Smith_Machine_Close-Grip_Bench_Press"),
            ("Bench press 10kg 8 reps", "Barbell_Bench_Press_-_Medium_Grip"),
            ("Dumbbell bench press 10kg 8 reps", "Dumbbell_Bench_Press"),
        ]:
            with self.subTest(note=note):
                self.assertEqual(inventory(note)["groups"][0]["candidates"], [expected])

    def test_omitted_duplicate_and_reordered_sets_are_rejected(self):
        for altered in (copy.deepcopy(proposal()),):
            altered["exercises"][3]["sets"].pop()
            with self.assertRaisesRegex(ValueError, "bench press"):
                check_coverage(NOTE + "\nClarifications: " + CLARIFY, altered)
        altered = proposal()
        altered["exercises"][1]["sets"].reverse()
        with self.assertRaises(ValueError):
            check_coverage(NOTE + "\nClarifications: " + CLARIFY, altered)

    def test_repeated_exercise_objects_merge_without_losing_equal_sets(self):
        data = proposal()
        ex = data["exercises"][3]
        data["exercises"] = [{**ex, "sets": [s]} for s in ex["sets"]]
        clean = validate("workout", data)
        self.assertEqual(len(clean["exercises"]), 1)
        self.assertEqual(len(clean["exercises"][0]["sets"]), 3)

    def test_catalog_movements_are_matched_without_misattributing_their_sets(self):
        source = inventory(
            "hammer curl 10kg 9 reps\nDumbbell shoulder press 12.5kg 8 reps\nThen 15kg 6 reps"
        )
        self.assertEqual(len(source["groups"][0]["sets"]), 1)
        self.assertEqual(source["unsupported"], [])
        self.assertEqual(source["groups"][1]["candidates"][0], "Dumbbell_Shoulder_Press")
        self.assertEqual(len(source["groups"][1]["sets"]), 2)

    def test_rear_and_reverse_fly_are_not_chest_fly(self):
        for movement in (
            "cable rear delt fly single arm",
            "rear-delt dumbbell fly",
            "reverse cable fly",
            "rear deltoid fly",
        ):
            with self.subTest(movement=movement):
                source = inventory("hammer curl 12kg 8 reps\n" + movement + " 3kg 9 reps")
                self.assertNotIn("chest fly", [g["label"] for g in source["groups"]])
                self.assertEqual(len(source["groups"][0]["sets"]), 1)
                self.assertEqual(len(source["groups"]) + len(source["unsupported"]), 2)
                self.assertEqual(source["unresolved"], [])
        source = inventory("machine chest fly 15kg 8 reps\ncable rear delt fly 3kg 9 reps")
        self.assertEqual(source["groups"][0]["candidates"], ["Butterfly"])
        self.assertEqual(len(source["groups"][0]["sets"]), 1)

    def test_mixed_shoulder_workout_preserves_source_sets_in_editable_preview(self):
        note = (
            "hammer curl 12kg 8 reps then 6 reps\n"
            "lateral raise standing 4kg 3 sets 12 reps, 10 reps 10 reps\n"
            "cable rear delt fly single arm 3kg 9 reps then 7 reps"
        )
        data = {
            "date": "2026-02-01",
            "exercises": [
                {
                    "exercise_id": eid,
                    "sets": [{"weight": weight, "reps": r} for r in reps],
                }
                for eid, weight, reps in (
                    ("Hammer_Curls", 12, [8, 6]),
                    ("Side_Lateral_Raise", 4, [12, 10, 10]),
                    ("Cable_Rear_Delt_Fly", 3, [9, 7]),
                )
            ],
        }
        for omit_set in (False, True):
            with self.subTest(omit_set=omit_set), tempfile.TemporaryDirectory() as tmp:
                store = Store(tmp)
                connections = Connections(Path(tmp))
                connections.save({})
                coach = Coach(store, connections)
                generated = copy.deepcopy(data)
                if omit_set:
                    generated["exercises"][0]["sets"].pop()
                with patch.object(
                    coach,
                    "generate",
                    return_value={"action": "workout", "message": "Review.", "proposal": generated},
                ):
                    result = coach.chat(note, True, "2026-02-01", logging_kind="workout")
                self.assertEqual(store.entries(), [])
                self.assertEqual(result["action"], "workout")
                self.assertEqual(
                    sum(len(e["sets"]) for e in result["draft"]["data"]["exercises"]), 7
                )
                self.assertEqual(
                    result["draft"]["data"]["exercises"][0]["sets"],
                    [{"weight": 12, "reps": r, "seconds": 0} for r in [8, 6]],
                )
                corrected = copy.deepcopy(result["draft"]["data"])
                corrected["exercises"][1]["sets"][0]["reps"] = 11
                with patch.object(
                    coach,
                    "generate",
                    return_value={
                        "action": "workout",
                        "message": "Changed.",
                        "proposal": corrected,
                    },
                ):
                    revision = coach.chat("Change the first lateral raise set to 11 reps", True)
                self.assertEqual(len(store.drafts()), 1)
                self.assertNotEqual(revision["draft"]["id"], result["draft"]["id"])
                self.assertEqual(revision["draft"]["data"]["exercises"][1]["sets"][0]["reps"], 11)
                self.assertEqual(store.entries(), [])

    def test_full_arm_and_shoulder_note_has_all_fifteen_sets(self):
        note = """Log my workout for 2026-02-01:
standing hammer curls 12kg 8 reps then 6 reps, then 8kg 11 reps
seated bicep curls 12kg 6 reps 8kg 7 reps
cable bicep curl - total weight loaded 15kg - 9 reps, 12kg 7 reps
lateral raise standing - 4kg 3 sets - hit 12 reps, 10 reps 10 reps
front dumbell raise - 4kg - 9 reps and 7 reps
side delts i did cable rear delt fly single arm - 3kg 11 reps, then 9 reps
reverse curl (forearms) 8kg - 7 reps"""
        source = inventory(note)
        self.assertEqual(source["unsupported"], [])
        self.assertEqual(source["unresolved"], [])
        self.assertEqual(len(source["groups"]), 7)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            connections = Connections(Path(tmp))
            connections.save({})
            coach = Coach(store, connections)
            data = {
                "date": "2026-02-01",
                "exercises": [
                    {"exercise_id": g["candidates"][0], "sets": [{"weight": 99, "reps": 1}]}
                    for g in source["groups"]
                ],
            }
            with patch.object(
                coach,
                "generate",
                return_value={
                    "action": "workout",
                    "message": "Review.",
                    "proposal": data,
                },
            ) as generate:
                result = coach.chat(note, True, "2026-02-01", logging_kind="workout")
            self.assertEqual(generate.call_args.kwargs["response_kind"], "workout")
            self.assertIn("Cable_Rear_Delt_Fly", str(generate.call_args.args[0]))
            exercises = result["draft"]["data"]["exercises"]
            self.assertEqual(len(exercises), 7)
            self.assertEqual(sum(len(e["sets"]) for e in exercises), 15)
            self.assertIn("1. Hammer Curls\n   Set 1: 12 kg × 8 reps", result["text"])
            self.assertEqual(result["text"].count("   Set "), 15)
            self.assertIn("6. Cable Rear Delt Fly", result["text"])
            self.assertIn("7. Reverse Barbell Curl", result["text"])
            for group, exercise in zip(source["groups"], exercises):
                self.assertEqual(
                    [(s["weight"], s["reps"]) for s in group["sets"]],
                    [(s["weight"], s["reps"]) for s in exercise["sets"]],
                )
            self.assertEqual(store.entries(), [])
            # Optional variation questions cannot block a complete reviewable list.
            with patch.object(
                coach,
                "generate",
                return_value={
                    "action": "clarify",
                    "message": "Which curl variation?",
                    "proposal": None,
                },
            ):
                fallback = coach.chat(note, True, "2026-02-01", logging_kind="workout")
            self.assertEqual(fallback["action"], "workout")
            self.assertEqual(
                sum(len(e["sets"]) for e in fallback["draft"]["data"]["exercises"]), 15
            )
            self.assertIn("Exercise variations to review", fallback["draft"]["data"]["notes"])
            self.assertEqual(store.entries(), [])
            with patch.object(coach, "generate", side_effect=ProviderError("HTTP 503")) as generate:
                offline = coach.chat(note, True, "2026-02-01", logging_kind="workout")
            self.assertEqual(generate.call_count, 2)
            self.assertEqual(offline["action"], "workout")
            self.assertIn("provider was unavailable", offline["notices"][0])
            self.assertEqual(sum(len(e["sets"]) for e in offline["draft"]["data"]["exercises"]), 15)
            self.assertEqual(store.entries(), [])

    def test_retries_replace_notes_without_duplicating_sets(self):
        note = "Log my workout: hammer curl 12kg 8 reps then 6 reps"
        accumulated = note + "\nClarifications:\n" + note
        for retry in (note, "YOU\n" + note):
            self.assertEqual(combine_source(accumulated, retry), note)
        self.assertEqual(
            combine_source(accumulated, "The cable was a rope attachment"),
            note + "\nClarifications:\nThe cable was a rope attachment",
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            connections = Connections(Path(tmp))
            connections.save({})
            coach = Coach(store, connections)
            store.message(
                "user", {"text": note, "logging_kind": "workout", "workout_source": accumulated}
            )
            store.message("assistant", {"action": "clarify", "text": "Preview failed."})
            with patch.object(
                coach,
                "generate",
                return_value={
                    "action": "workout",
                    "message": "Review.",
                    "proposal": {
                        "date": "2026-02-01",
                        "exercises": [
                            {"exercise_id": "Hammer_Curls", "sets": [{"weight": 12, "reps": 8}]}
                        ],
                    },
                },
            ):
                result = coach.chat("YOU\n" + note, True, "2026-02-01", logging_kind="workout")
            self.assertEqual(len(result["draft"]["data"]["exercises"][0]["sets"]), 2)
            self.assertEqual(store.messages()[-2]["workout_source"], note)

    def test_partial_preview_accepts_a_clarification_without_retyping_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            connections = Connections(Path(tmp))
            connections.save({})
            coach = Coach(store, connections)
            with patch.object(coach, "generate", side_effect=ProviderError("HTTP 503")):
                first = coach.chat(NOTE, True, "2026-02-01", logging_kind="workout")
            self.assertEqual(first["action"], "workout")
            self.assertTrue(first["workout_incomplete"])
            self.assertIn("Partial workout preview", first["text"])
            self.assertEqual(sum(len(ex["sets"]) for ex in first["draft"]["data"]["exercises"]), 20)
            self.assertIn("machine plate", first["text"])
            with patch.object(
                coach,
                "generate",
                return_value={
                    "action": "workout",
                    "message": "Review all sets.",
                    "proposal": proposal(),
                },
            ) as generate:
                result = coach.chat(CLARIFY, True, "2026-02-01")
                self.assertEqual(generate.call_count, 2)
                self.assertIn("EXPLICIT SET INVENTORY", generate.call_args.args[0][0]["content"])
                self.assertNotIn("Athlete", generate.call_args.args[0][-1]["content"])
            self.assertIn("draft", result)
            self.assertNotIn("workout_incomplete", result)
            self.assertEqual(len(store.drafts()), 1)
            self.assertEqual(store.entries(), [])
            store.approve(result["draft"]["id"])
            self.assertEqual(sum(len(ex["sets"]) for ex in store.entries()[0]["exercises"]), 21)
