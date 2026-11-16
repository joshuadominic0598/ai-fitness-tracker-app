import tempfile
import unittest
from datetime import date

from fitness_tracker.consistency import metric_score
from fitness_tracker.goals import calendar_window, validate_goals
from fitness_tracker.store import Store, valid_date


class CalendarTests(unittest.TestCase):
    def test_weeks_monday_sunday_including_year_boundary(self):
        for reference, start, end in [
            (date(2026, 11, 15), date(2026, 11, 9), date(2026, 11, 15)),
            (date(2026, 11, 16), date(2026, 11, 16), date(2026, 11, 22)),
            (date(2050, 1, 1), date(2049, 12, 27), date(2050, 1, 2)),
        ]:
            self.assertEqual(
                calendar_window({"period": 1, "unit": "week"}, reference), (start, end)
            )

    def test_calendar_month_lengths_and_leap_years(self):
        for year, month, days in [
            (2026, 11, 30),
            (2026, 12, 31),
            (2027, 2, 28),
            (2028, 2, 29),
            (2048, 2, 29),
            (2050, 2, 28),
        ]:
            self.assertEqual(
                calendar_window({"period": 1, "unit": "month"}, date(year, month, 15)),
                (date(year, month, 1), date(year, month, days)),
            )
        self.assertEqual(
            calendar_window({"period": 2, "unit": "month"}, date(2028, 3, 5)),
            (date(2028, 2, 1), date(2028, 3, 31)),
        )

    def test_monthly_goals_are_persisted_and_scored_by_calendar(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            goals = store.profile()["goals"]
            goals["protein"] = {"amount": 2800, "period": 1, "unit": "month"}
            saved = store.save_profile({"goals": goals})
            self.assertEqual(saved["goals"]["protein"]["unit"], "month")
            score = metric_score(
                {date(2027, 2, 15): 2800}, goals["protein"], date(2027, 3, 1), date(2027, 2, 1)
            )
            self.assertEqual(score["met_periods"], 1)
            self.assertEqual(score["attainment"], 100)
            validate_goals(saved["goals"])

    def test_calendar_accepts_last_day_of_2050(self):
        self.assertEqual(valid_date("2050-12-31"), "2050-12-31")
        self.assertEqual(valid_date("2048-02-29"), "2048-02-29")
        for value in ("2050-02-29", "2051-01-01", "1899-12-31"):
            with self.assertRaises(ValueError):
                valid_date(value)
