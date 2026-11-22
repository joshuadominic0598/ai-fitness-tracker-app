import json
import tempfile
import threading
import unittest
import urllib.request
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from fitness_tracker.chat_actions import adjusted_meal_totals, require_meal_calories
from fitness_tracker.coach import Coach, Connections
from fitness_tracker.server import AppServer
from fitness_tracker.store import Store, validate

DAY = "2026-11-21"


def meal():
    return {
        "date": DAY,
        "description": "KFC chicken",
        "source": "ai",
        "protein": 29,
        "calories": 640,
        "low": 29,
        "high": 49.50000000000001,
        "items": [{"name": "KFC chicken", "portion": "2 pieces", "protein": 29, "calories": 640}],
    }


def seed(store, kind="meal", data=None):
    draft = store.draft(kind, data or meal())
    store.message(
        "user",
        {
            "text": "Log my food",
            "logging_kind": "meal",
            "context_date": DAY,
            "status": "sent",
            "request_id": "original-meal-request",
        },
    )
    store.message(
        "assistant",
        {"text": "Review", "action": kind, "draft": draft, "request_id": "original-meal-request"},
    )
    return draft


class MealAdjustmentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(temp.name)
        self.coach = Coach(self.store, Connections(Path(temp.name)))

    def test_manual_totals_approve_without_ai_and_replay_without_duplicates(self):
        draft = seed(self.store)
        kwargs = {
            "approve_draft_id": draft["id"],
            "request_id": "adjust-and-approve",
            "meal_totals": [{"protein": 30, "calories": 650, "low": 30, "high": 45}],
        }
        with patch.object(self.coach, "generate") as model:
            result = self.coach.chat("I approve", True, DAY, **kwargs)
            replay = self.coach.chat("I approve", True, DAY, **kwargs)
        model.assert_not_called()
        self.assertEqual(result["approved"], replay["approved"])
        self.assertIn("30 g protein", result["text"])
        self.assertIn("650 kcal", result["text"])
        self.assertIn("totals adjusted by you", result["text"])
        saved = self.store.entries()[0]
        self.assertEqual(
            (saved["protein"], saved["calories"], saved["low"], saved["high"]), (30, 650, 30, 45)
        )
        self.assertEqual(
            saved["items"][0]["protein"], 29, "original food estimates remain available"
        )
        self.assertEqual(saved["confirmed_totals"], {"protein": 30, "calories": 650})
        reopened = Store(self.store.directory)
        self.assertEqual(reopened.entries(), [saved])
        self.assertEqual(validate("meal", saved)["confirmed_totals"], saved["confirmed_totals"])

    def test_batch_adjusts_only_the_selected_meal_and_preserves_other_entries(self):
        original = seed(
            self.store,
            "batch",
            {
                "entries": [
                    {"kind": "meal", "data": meal()},
                    {"kind": "meal", "data": meal()},
                    {"kind": "sleep", "data": {"date": DAY, "hours": 7, "period": "night"}},
                ]
            },
        )
        target = original["data"]["entries"][1]["item_id"]
        result = self.coach.chat(
            "I approve",
            True,
            DAY,
            approve_draft_id=original["id"],
            meal_totals=[{"item_id": target, "protein": 40}],
        )
        saved = result["approved"]["entries"]
        self.assertEqual([entry["protein"] for entry in saved if entry["kind"] == "meal"], [29, 40])
        self.assertEqual(saved[1]["calories"], 640)
        self.assertNotIn(
            "low", saved[1], "changing protein without supplying a range drops the old uncertainty"
        )
        self.assertEqual(saved[2]["hours"], 7)

    def test_invalid_adjustments_never_save_or_dismiss_the_preview(self):
        draft = seed(self.store)
        for adjustment in [
            {"protein": -1},
            {"protein": 501},
            {"protein": float("nan")},
            {"protein": True},
            {"calories": 10001},
            {"item_id": "unknown", "protein": 30},
            {"protein": 30, "low": 35, "high": 40},
            {"protein": 30, "low": 25},
        ]:
            with self.subTest(adjustment=adjustment), self.assertRaises(ValueError):
                self.coach.chat(
                    "I approve", True, DAY, approve_draft_id=draft["id"], meal_totals=[adjustment]
                )
            self.assertEqual(self.store.entries(), [])
            self.assertEqual(self.store.drafts(), [draft])
        with self.assertRaises(ValueError):
            adjusted_meal_totals(draft, [{"protein": 30}, {"protein": 30}])

    def test_stale_approval_cannot_overwrite_changes_to_the_day(self):
        draft = seed(self.store)
        sleep = self.store.save("sleep", {"date": DAY, "hours": 7, "period": "night"})
        with self.assertRaisesRegex(ValueError, "day changed"):
            self.coach.chat(
                "I approve", True, DAY, approve_draft_id=draft["id"], meal_totals=[{"protein": 30}]
            )
        self.assertEqual(self.store.entries(), [sleep])

    def test_ranges_are_optional_rounded_and_checked_against_the_total(self):
        original = meal()
        self.assertEqual(validate("meal", original)["high"], 49.5)
        for protein, low, high in [(30, "", ""), (0, 0, 10), (40, 35, 49.50000000000001)]:
            data = {
                "date": DAY,
                "description": "Manual meal",
                "protein": protein,
                "low": low,
                "high": high,
            }
            result = validate("meal", data)
            if low == "":
                self.assertNotIn("low", result)
            else:
                self.assertEqual(result["high"], round(high, 2))
        with self.assertRaisesRegex(ValueError, "inside the stated range"):
            validate(
                "meal",
                {"date": DAY, "description": "Manual meal", "protein": 30, "low": 35, "high": 40},
            )
        adjusted = adjusted_meal_totals(
            {"kind": "meal", "data": original}, [{"protein": 30, "low": None, "high": None}]
        )
        self.assertNotIn("low", adjusted)
        with self.assertRaisesRegex(ValueError, "manual approval"):
            require_meal_calories(adjusted)
        inconsistent = deepcopy(adjusted)
        inconsistent["protein"] = 99
        with self.assertRaisesRegex(ValueError, "confirmed value"):
            validate("meal", inconsistent)


class MealApprovalHTTPTests(unittest.TestCase):
    def test_regular_and_streaming_chat_forward_manual_totals(self):
        for stream in (False, True):
            with self.subTest(stream=stream), tempfile.TemporaryDirectory() as directory:
                server = AppServer(("127.0.0.1", 0), directory)
                server.store.set_coach_consent(True)
                draft = seed(server.store)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    payload = {
                        "message": "I approve",
                        "date": DAY,
                        "request_id": "manual-approval-http",
                        "approve_draft_id": draft["id"],
                        "meal_totals": [{"protein": 30}],
                        "stream": stream,
                    }
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/api/chat",
                        json.dumps(payload).encode(),
                        {"Content-Type": "application/json", "X-App-Token": server.token},
                    )
                    with (
                        patch.object(server.coach, "generate") as model,
                        urllib.request.urlopen(request) as response,
                    ):
                        raw = response.read().decode()
                    model.assert_not_called()
                    result = (
                        next(
                            json.loads(line)["response"]
                            for line in raw.splitlines()
                            if json.loads(line).get("type") == "final"
                        )
                        if stream
                        else json.loads(raw)
                    )
                    self.assertEqual(result["approved"]["entries"][0]["protein"], 30)
                    self.assertEqual(len(server.store.entries()), 1)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()
