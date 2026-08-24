import unittest
from datetime import datetime, timezone

from influenza_target_data.schedule import schedule_state
from influenza_target_data.weeks import season_weeks_through, week_sunday


class WeekTests(unittest.TestCase):
    def test_week_sunday(self):
        self.assertEqual(week_sunday("2026W40").isoformat(), "2026-10-04")

    def test_season_crosses_new_year(self):
        weeks = season_weeks_through("2027W02")
        self.assertEqual(weeks[0], "2026W40")
        self.assertEqual(weeks[-1], "2027W02")

    def test_offseason_has_no_season_range(self):
        self.assertEqual(season_weeks_through("2026W30"), [])

    def test_schedule_uses_stockholm_time(self):
        state = schedule_state(datetime(2026, 10, 8, 6, tzinfo=timezone.utc))
        self.assertEqual(state["should_poll"], "true")
        self.assertEqual(state["target_week"], "2026W40")


if __name__ == "__main__":
    unittest.main()
