import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

from fitness_tracker.coach import Connections
from fitness_tracker.consistency import consistency, consistency_trend, score_periods
from fitness_tracker.store import Store, insights


class GoalsAndConsistencyTests(unittest.TestCase):
    def test_score_trend_is_historical_and_matches_current_score(self):
        profile = self.store.profile()
        records = [
            {"kind": "meal", "date": "2026-11-09", "protein": 100},
            {"kind": "meal", "date": "2026-11-11", "protein": 98},
        ]
        trend = consistency_trend(records, profile, date(2026, 11, 12))
        self.assertEqual(len(trend), 4)
        self.assertEqual(
            trend[-1]["overall"], consistency(records, profile, date(2026, 11, 12))["overall"]
        )
        future = {"kind": "meal", "date": "2026-11-15", "protein": 500}
        self.assertEqual(consistency_trend(records + [future], profile, date(2026, 11, 12)), trend)
        self.assertEqual(
            trend[0]["overall"], consistency(records[:1], profile, date(2026, 11, 9))["overall"]
        )
        self.assertEqual(consistency_trend([], profile, date(2026, 11, 12)), [])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_legacy_profile_hydrates_and_updates_preserve_other_targets(self):
        self.store.save_profile({"name": "Example", "weekly_goal": 4, "protein_goal": 140})
        profile = self.store.profile()
        self.assertEqual(profile["goals"]["workout"], {"amount": 4, "period": 1, "unit": "week"})
        goals = dict(profile["goals"])
        goals["protein"] = {"amount": 840, "period": 1, "unit": "week"}
        goals["workout"] = {"amount": 11, "period": 4, "unit": "week"}
        self.store.save_profile({"goals": goals})
        self.store.save_profile({"name": "Updated", "creatine_goal": 4})
        reopened = Store(self.temp.name).profile()
        self.assertEqual(reopened["goals"]["protein"], goals["protein"])
        self.assertEqual(reopened["goals"]["workout"], goals["workout"])
        self.assertEqual(reopened["goals"]["creatine"]["amount"], 4)
        self.assertEqual(reopened["name"], "Updated")
        self.assertEqual(reopened["protein_goal"], 120)  # compatibility average only

    def test_invalid_goal_is_atomic(self):
        original = self.store.profile()
        for changes in (
            {"period": 0},
            {"period": 1.5},
            {"period": 53, "unit": "week"},
            {"unit": "year"},
            {"amount": -1},
            {"amount": True},
            {"amount": float("nan")},
        ):
            goals = dict(original["goals"])
            goals["workout"] = {**goals["workout"], **changes}
            with self.assertRaises(ValueError):
                self.store.save_profile({"goals": goals, "name": "Do not persist"})
            self.assertEqual(self.store.profile(), original)
        with self.assertRaises(ValueError):
            self.store.save_profile({"consistency_supplements": ["Not in list"]})
        with self.assertRaises(ValueError):
            self.store.save_profile({"goals": None})

    def test_rest_break_examples_and_partial_periods(self):
        long_break = score_periods([(1, 90, True), (0, 30, True)])
        short_break = score_periods([(1, 90, True), (0, 7, True)])
        spaced_breaks = score_periods([(1, 23, True), (0, 7, True)] * 4)
        fewer_sessions = score_periods([(0.75, 7, True)] * 16)
        self.assertAlmostEqual(long_break, 84.3, places=1)
        self.assertGreater(short_break, 99)
        self.assertGreater(spaced_breaks, 96)
        self.assertGreater(fewer_sessions, long_break)
        self.assertEqual(score_periods([(1, 90, True), (0, 7, False)]), 100)
        self.assertEqual(score_periods([(2, 10, True)]), 100)

    def test_gym_weeks_allow_rest_days_and_a_month_break_costs_about_15(self):
        start = date(2026, 1, 5)  # Monday
        entries = [
            {"kind": "workout", "date": (start + timedelta(weeks=w, days=d)).isoformat()}
            for w in range(12)
            for d in (0, 2, 4)
        ]
        profile = self.store.profile()
        result = consistency(entries, profile, start + timedelta(weeks=16))
        self.assertAlmostEqual(result["categories"]["exercise"]["score"], 85.1, places=1)
        self.assertEqual(result["scored_categories"], 1)
        self.assertEqual(result["overall"], 85.1)
        self.assertEqual(result["attainment"], 75)
        self.assertEqual(result["categories"]["exercise"]["met_periods"], 12)
        self.assertEqual(result["categories"]["exercise"]["completed_periods"], 16)
        complete = consistency(entries, profile, start + timedelta(weeks=12))
        self.assertEqual(complete["overall"], 100)
        # Duplicating a workout on a date cannot inflate gym frequency.
        self.assertEqual(
            consistency(entries + entries, profile, start + timedelta(weeks=16))["overall"], 85.1
        )

    def test_nutrition_periods_supplement_routine_and_missing_categories(self):
        today = date(2026, 11, 9)  # Monday, prior week fully elapsed
        self.assertIsNone(consistency([], self.store.profile(), today)["overall"])
        goals = self.store.profile()["goals"]
        goals["protein"] = {"amount": 840, "period": 1, "unit": "week"}
        profile = self.store.save_profile(
            {"goals": goals, "consistency_supplements": ["Creatine", "Vitamin D"]}
        )
        entries = []
        for i in range(7):
            day = (today - timedelta(days=7 - i)).isoformat()
            entries += [
                {"kind": "meal", "date": day, "protein": 120},
                {"kind": "supplement", "date": day, "name": "Creatine", "amount": 5, "unit": "g"},
            ]
        result = consistency(entries, profile, today)
        self.assertEqual(result["categories"]["protein"]["score"], 100)
        self.assertEqual(result["categories"]["creatine"]["score"], 100)
        self.assertIsNone(result["categories"]["supplements"]["score"])
        self.assertEqual(result["overall"], 100)
        # Only chosen supplements matter; inactive categories remain unscored.
        profile["consistency_supplements"] = ["Creatine"]
        extra = [
            {"kind": "meal", "date": "2026-11-10", "protein": 500},
            {"kind": "plan", "date": "2026-11-08"},
        ]
        self.assertEqual(consistency(entries + extra, profile, today)["overall"], 100)
        self.assertIsNone(result["categories"]["exercise"]["score"])

    def test_exact_goal_hits_exclude_today(self):
        today = date(2026, 11, 10)
        self.store.save_profile({"protein_goal": 100})
        self.store.save("meal", {"date": "2026-11-09", "description": "Yesterday", "protein": 98})
        self.store.save("meal", {"date": "2026-11-10", "description": "Today", "protein": 100})
        result = insights(self.store.entries(), self.store.profile(), today)
        self.assertEqual(result["protein_goal_days"], 0)

    def test_scoped_connection_saves_preserve_services_and_atomic_parallel_merge(self):
        c = Connections(Path(self.temp.name))
        changes = [
            {"ollama_model": "qwen3:8b"},
            {"ollama_url": "http://127.0.0.1:11434"},
            {"ollama_context_tokens": 8192},
            {"context_budget_tokens": 5000},
        ]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(c.save, changes))
        self.assertEqual(
            c.read(), {key: value for change in changes for key, value in change.items()}
        )
        self.assertEqual(c.public()["provider"], "ollama")
