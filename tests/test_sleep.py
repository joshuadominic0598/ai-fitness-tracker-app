import tempfile
import unittest
from datetime import date

from fitness_tracker.sleep import sleep_days
from fitness_tracker.store import Store, insights, validate


class SleepTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def log(self, hours=6, period="night", continuous=6, day="2026-11-09"):
        return self.store.save(
            "sleep", {"date": day, "hours": hours, "period": period, "continuous_hours": continuous}
        )

    def test_default_targets_and_atomic_goal_validation(self):
        profile = self.store.profile()
        self.assertEqual(
            (profile["sleep_goal"], profile["night_hours_goal"], profile["night_sleep_goal"]),
            (7, 6, 6),
        )
        self.store.save_profile({"sleep_goal": 8, "night_sleep_goal": 7})
        with self.assertRaises(ValueError):
            self.store.save_profile({"sleep_goal": 5})
        self.assertEqual(self.store.profile()["sleep_goal"], 8)
        self.assertEqual(self.store.profile()["goals"], profile["goals"])

    def test_night_and_nap_combine_but_night_blocks_do_not(self):
        self.log()
        self.log(1, "afternoon", None)
        summary = sleep_days(self.store.entries())["2026-11-09"]
        self.assertEqual(summary["hours"], 7)
        self.assertEqual(summary["night_continuous"], 6)
        metrics = insights(self.store.entries(), self.store.profile(), date(2026, 11, 10))
        score = metrics["consistency"]["categories"]["sleep"]
        self.assertEqual((score["attainment"], score["met_periods"]), (100, 1))
        self.store.reset()
        self.log(3, continuous=3)
        self.log(3, continuous=3)
        self.log(1, "afternoon", None)
        metrics = insights(self.store.entries(), self.store.profile(), date(2026, 11, 10))
        self.assertEqual(metrics["daily"]["2026-11-09"]["sleep"]["night_continuous"], 3)
        self.assertEqual(metrics["daily"]["2026-11-09"]["sleep"]["night_hours"], 6)
        self.assertEqual(metrics["consistency"]["categories"]["sleep"]["attainment"], 100)

    def test_unknown_continuity_and_future_entries_stay_distinct(self):
        self.log(7, continuous=None)
        self.log(8, continuous=8, day="2026-11-11")
        metrics = insights(self.store.entries(), self.store.profile(), date(2026, 11, 10))
        self.assertEqual(metrics["sleep_average"], 7)
        self.assertFalse(metrics["daily"]["2026-11-09"]["sleep"]["continuity_recorded"])
        self.assertIsNone(metrics["daily"]["2026-11-10"]["sleep"])
        self.assertEqual(metrics["consistency"]["categories"]["sleep"]["attainment"], 100)
        self.assertEqual(metrics["consistency"]["categories"]["sleep"]["logged_days"], 1)

    def test_rest_day_includes_nap_and_following_night_without_date_shifting(self):
        self.log(6.5, continuous=4, day="2026-11-09")
        self.log(0.5, "afternoon", None, day="2026-11-09")
        self.log(2, "afternoon", None, day="2026-11-10")
        self.log(6, continuous=6, day="2026-11-10")
        metrics = insights(self.store.entries(), self.store.profile(), date(2026, 11, 11))
        self.assertEqual(metrics["daily"]["2026-11-09"]["sleep"]["hours"], 7)
        self.assertEqual(metrics["daily"]["2026-11-09"]["sleep"]["night_continuous"], 4)
        self.assertEqual(metrics["daily"]["2026-11-10"]["sleep"]["hours"], 8)
        self.assertEqual(metrics["daily"]["2026-11-10"]["sleep"]["night_hours"], 6)
        self.assertIsNone(metrics["daily"]["2026-11-11"]["sleep"])
        self.assertEqual(metrics["consistency"]["categories"]["sleep"]["met_periods"], 2)
        self.assertEqual(metrics["consistency"]["categories"]["sleep"]["score"], 100)

    def test_naps_cannot_replace_the_night_goal(self):
        self.log(4, continuous=4)
        self.log(4, "afternoon", None)
        metrics = insights(self.store.entries(), self.store.profile(), date(2026, 11, 10))
        score = metrics["consistency"]["categories"]["sleep"]
        self.assertEqual(score["attainment"], 66.7)
        self.assertEqual(score["met_periods"], 0)
        with self.assertRaises(ValueError):
            self.store.save_profile({"night_hours_goal": 8})
        self.assertEqual(self.store.profile()["night_hours_goal"], 6)

    def test_sleep_validation_and_daily_cap_survive_edit(self):
        for values in [
            dict(hours=-1),
            dict(hours=25),
            dict(hours=float("nan")),
            dict(continuous_hours=7),
            dict(period="afternoon"),
            dict(period="evening"),
        ]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate(
                    "sleep",
                    {
                        "date": "2026-11-09",
                        "hours": 6,
                        "period": "night",
                        "continuous_hours": 6,
                        **values,
                    },
                )
        first = self.log(20, continuous=6)
        self.log(4, "other", None)
        edited = self.store.save("sleep", {**first, "hours": 19}, first["id"])
        self.assertEqual(edited["hours"], 19)
        with self.assertRaises(ValueError):
            self.store.save("sleep", {**first, "hours": 21}, first["id"])
        self.assertEqual(sleep_days(self.store.entries())["2026-11-09"]["hours"], 23)
        self.store.delete(first["id"])
        self.assertEqual(sleep_days(self.store.entries())["2026-11-09"]["hours"], 4)
