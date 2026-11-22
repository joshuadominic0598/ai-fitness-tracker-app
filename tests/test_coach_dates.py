import unittest
from datetime import date, timedelta

from fitness_tracker.coach_workflow import stated_day


class CoachDateTests(unittest.TestCase):
    def test_explicit_written_dates_override_the_selected_journal_day(self):
        for phrase in (
            "Log food for 2026-11-21",
            "Log food for 21/11/2026",
            "Log food for 21st November 2026",
            "Log food for November 21st, 2026",
            "Log food for Nov 21, not today",
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(stated_day(phrase, "2026-11-22"), "2026-11-21")

    def test_relative_dates_do_not_shift_again_from_an_older_selected_date(self):
        self.assertEqual(
            stated_day("Log my sleep yesterday", "2025-01-01"),
            (date.today() - timedelta(days=1)).isoformat(),
        )
        self.assertEqual(stated_day("Log my cardio today", "2025-01-01"), date.today().isoformat())
        self.assertIsNone(stated_day("Log my meal", "2026-11-22"))

    def test_invalid_written_dates_are_not_silently_replaced_by_today(self):
        for phrase in ("Log food for 31/02/2026", "Log food for February 31, 2026"):
            with self.subTest(phrase=phrase), self.assertRaises(ValueError):
                stated_day(phrase, "2026-11-22")
