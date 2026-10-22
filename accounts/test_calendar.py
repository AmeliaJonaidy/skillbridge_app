from datetime import date

from django.test import SimpleTestCase

from .calendar import build_month_calendar


class CalendarBuilderTests(SimpleTestCase):
    def test_month_navigation_handles_december(self):
        calendar_data = build_month_calendar([], month_value="2026-12", selected_value="2026-12-15")

        self.assertEqual(calendar_data["previous_month"], date(2026, 11, 1))
        self.assertEqual(calendar_data["next_month"], date(2027, 1, 1))
        self.assertEqual(calendar_data["selected_date"], date(2026, 12, 15))
