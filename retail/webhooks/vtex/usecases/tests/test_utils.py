from calendar import FRIDAY
from datetime import time as datetime_time
from django.test import TestCase
from django.utils import timezone
from django.utils.timezone import timedelta
import pytz

from retail.webhooks.vtex.usecases.utils import (
    convert_str_time_to_time,
    is_saturday,
    is_weekday,
    combine_date_and_time_with_shift,
    get_next_available_time,
)


class TestDateUtils(TestCase):
    def test_is_weekday(self):
        for i in range(0, 5):
            self.assertTrue(is_weekday(i))

        for i in range(5, 7):
            self.assertFalse(is_weekday(i))

    def test_is_saturday(self):
        for i in range(0, 5):
            self.assertFalse(is_saturday(i))

        for i in range(5, 6):
            self.assertTrue(is_saturday(i))

    def test_convert_str_time_to_time(self):
        """Test conversion of string time to time object."""
        self.assertEqual(convert_str_time_to_time("10:00"), datetime_time(10, 0))

    def test_combine_date_and_time_with_shift(self):
        t = datetime_time(10, 0)
        now = timezone.now()
        self.assertEqual(
            combine_date_and_time_with_shift(1, t),
            timezone.datetime.combine(now.date() + timedelta(days=1), t),
        )

    def test_get_next_available_time_in_a_weekday(self):
        dt = timezone.datetime(2025, 1, 31, 19, 45, tzinfo=pytz.UTC)

        self.assertEqual(dt.weekday(), FRIDAY)

        weekdays_period = {"from": "08:00", "to": "20:00"}
        saturdays_period = {"from": "10:00", "to": "12:00"}

        expected_next_available_time = convert_str_time_to_time(
            saturdays_period["from"]
        )

        next_available_time = get_next_available_time(
            dt, weekdays_period, saturdays_period
        )

        self.assertEqual(
            next_available_time,
            combine_date_and_time_with_shift(1, expected_next_available_time),
        )
