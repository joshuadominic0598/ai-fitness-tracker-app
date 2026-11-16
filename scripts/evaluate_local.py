#!/usr/bin/env python3
"""Exercise the real local model in a disposable journal; never approve personal logs.

Use --workout-file to test a private note. Reports contain metrics/checks, not prompts,
food details, model prose, or journal data. Public-search transport is a controlled
fixture in the agent-loop case; model decisions and calculator execution are real.
"""

import argparse
import copy
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fitness_tracker.coach import Coach, Connections  # noqa: E402
from fitness_tracker.store import Store  # noqa: E402
from fitness_tracker.workout_notes import check_coverage, inventory  # noqa: E402

DAY = "2026-11-13"
NOTE = """Log my workout for 2026-11-13:
standing hammer curls 12kg 8 reps then 6 reps, then 8kg 11 reps
seated bicep curls 12kg 6 reps 8kg 7 reps
cable bicep curl total loaded 15kg 9 reps, 12kg 7 reps
lateral raise standing 4kg 3 sets 12 reps, 10 reps 10 reps
front dumbell raise 4kg 9 reps and 7 reps
cable rear delt fly single arm 3kg 11 reps, then 9 reps
reverse curl (forearms) 8kg 7 reps"""


class ObservedCoach(Coach):
    def __init__(self, *args):
        super().__init__(*args)
        self.raw = []

    def generate(self, *args, **kwargs):
        result = super().generate(*args, **kwargs)
        self.raw.append(copy.deepcopy(result))
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--context", type=int, default=8192)
    parser.add_argument("--workout-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cases", help="Optional comma-separated case names to run")
    args = parser.parse_args()
    note = args.workout_file.read_text() if args.workout_file else NOTE
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "context_tokens": args.context,
        "input_budget": 5000,
        "private_prompts_in_report": False,
        "cases": [],
    }
    with tempfile.TemporaryDirectory(prefix="blaze-local-eval-") as tmp:
        root = Path(tmp)

        def workspace(name):
            folder = root / name
            folder.mkdir()
            connections = Connections(folder)
            connections.save(
                {
                    "provider": "ollama",
                    "ollama_model": args.model,
                    "ollama_context_tokens": args.context,
                }
            )
            return ObservedCoach(Store(folder), connections)

        def run(name, fn):
            if args.cases and name not in args.cases.split(","):
                return
            started = time.monotonic()
            try:
                result = fn()
                row = {"case": name, "ok": True, **result}
            except Exception as error:
                row = {
                    "case": name,
                    "ok": False,
                    "error_type": type(error).__name__,
                }
                if str(error) in {
                    "meal_initial_preview",
                    "meal_corrected_preview",
                    "meal_food_count",
                    "meal_milk_portion",
                    "meal_stale_preview",
                    "meal_other_foods_changed",
                }:
                    row["failed_check"] = str(error)
            row["seconds"] = round(time.monotonic() - started, 2)
            report["cases"].append(row)
            print(json.dumps(row), flush=True)
            if args.output:
                args.output.write_text(json.dumps(report, indent=2) + "\n")

        def workout_case(value, label):
            coach = workspace(label)
            result = coach.chat(value, True, DAY, logging_kind="workout")
            proposal = result["draft"]["data"]
            expected = sum(len(g["sets"]) for g in inventory(value)["groups"])
            sets = sum(len(e["sets"]) for e in proposal["exercises"])
            assert sets == expected
            check_coverage(value, proposal)
            raw_exact = True
            try:
                check_coverage(value, coach.raw[-1].get("proposal"))
            except (ValueError, TypeError):
                raw_exact = False
            assert coach.store.entries() == []
            assert result["agent"]["local_runs"], "No successful local generation"
            return {
                "source_chars": len(value),
                "expected_sets": expected,
                "preview_sets": sets,
                "exercises": len(proposal["exercises"]),
                "raw_model_sets_exact": raw_exact,
                "app_sets_exact": True,
                "usage": result["agent"]["local_runs"],
            }

        run("workout", lambda: workout_case(note, "short"))
        run("double_workout", lambda: workout_case(note + "\n" + note, "double"))

        def meal_case():
            coach = workspace("meal")
            first = coach.chat(
                "Log my food: 150ml milk, one boiled egg and 30g cheese. List each food separately with protein and assumptions.",
                True,
                DAY,
                logging_kind="meal",
            )
            assert first.get("draft"), "meal_initial_preview"
            data = first["draft"]["data"]
            assert len(data.get("items", [])) == 3, "meal_food_count"
            before = copy.deepcopy(data["items"])
            second = coach.chat(
                "Change only the milk portion to 250ml, keeping the egg and cheese unchanged.",
                True,
                DAY,
            )
            assert second.get("draft"), "meal_corrected_preview"
            changed = second["draft"]["data"]
            assert len(changed["items"]) == 3, "meal_food_count"
            assert any("250" in item["portion"] for item in changed["items"]), "meal_milk_portion"
            assert len(coach.store.drafts()) == 1, "meal_stale_preview"
            assert coach.store.entries() == []
            preserved = [item["protein"] for item in before[1:]] == [
                item["protein"] for item in changed["items"][1:]
            ]
            assert preserved, "meal_other_foods_changed"
            return {
                "items": 3,
                "correction_preserved_other_items": preserved,
                "source_based_correction": second["agent"].get("source_based_correction", False),
                "saved_entries": 0,
                "usage": first["agent"]["local_runs"] + second["agent"]["local_runs"],
            }

        run("meal_breakdown_and_correction", meal_case)

        def simple_case(label, message, kind):
            coach = workspace(label)
            result = coach.chat(message, True, DAY, logging_kind=kind)
            assert result.get("draft"), result["text"]
            assert result["draft"]["kind"] == kind
            assert coach.store.entries() == []
            return {"draft_kind": kind, "saved_entries": 0, "usage": result["agent"]["local_runs"]}

        run(
            "exercise_plan",
            lambda: simple_case(
                "plan",
                "Plan a session with Hammer_Curls and Side_Lateral_Raise. Exercises only, not a completed workout.",
                "plan",
            ),
        )
        run(
            "supplement",
            lambda: simple_case(
                "supplement", "Log 1 tablet Vitamin D for the selected date.", "supplement"
            ),
        )

        def agent_case():
            coach = workspace("agent")
            original = coach.run_tool

            def tool(name, parameters):
                if name in ("web_search", "research"):
                    return [
                        {
                            "title": "Controlled public-search fixture",
                            "url": "https://example.test/protein",
                            "abstract": "Test fixture: supplied estimates are not intake prescriptions. Use the calculator for arithmetic.",
                            "kind": "test fixture",
                        }
                    ]
                return original(name, parameters)

            with patch.object(coach, "run_tool", side_effect=tool):
                result = coach.chat(
                    "Research general protein guidance, and use the calculator to verify 12.5 + 6.3 + 5 grams as a total. Do not log anything.",
                    True,
                    DAY,
                    research_mode=True,
                )
            tools = [
                row["tool"]
                for row in result["agent"]["trace"]
                if row.get("node") == "tool" and row.get("ok")
            ]
            assert "web_search" in tools and "calculator" in tools
            assert result["action"] == "answer"
            assert coach.store.entries() == []
            return {
                "tools": tools,
                "public_search_fixture": True,
                "usage": result["agent"]["local_runs"],
                "saved_entries": 0,
            }

        run("agent_tool_loop", agent_case)
    return 0 if all(row["ok"] for row in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
