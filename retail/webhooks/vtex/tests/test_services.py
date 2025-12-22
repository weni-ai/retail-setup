from calendar import FRIDAY, MONDAY, SATURDAY, SUNDAY, THURSDAY
from datetime import time as datetime_time
import datetime
from unittest import mock
import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from django.utils.timezone import timedelta

from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project
from retail.webhooks.vtex.services import CartTimeRestrictionService
from retail.webhooks.vtex.services import CartPhoneRestrictionService


class TestCartTimeRestrictionService(TestCase):
    def setUp(self):
        self.service = CartTimeRestrictionService

    def test_is_weekday(self):
        for i in range(MONDAY, FRIDAY + 1):
            self.assertTrue(self.service.is_weekday(i))

        for i in range(SATURDAY, SUNDAY + 1):
            self.assertFalse(self.service.is_weekday(i))

    def test_is_saturday(self):
        for i in list(range(MONDAY, FRIDAY + 1)) + [SUNDAY]:
            self.assertFalse(self.service.is_saturday(i))

        self.assertTrue(self.service.is_saturday(SATURDAY))

    def test_convert_str_time_to_time(self):
        """Test conversion of string time to time object."""
        self.assertEqual(
            self.service.convert_str_time_to_time("10:00"), datetime_time(10, 0)
        )

    def test_combine_date_and_time_with_shift(self):
        t = datetime_time(10, 0)
        now = timezone.now()
        result = self.service.combine_date_and_time_with_shift(now.date(), t, 1)
        expected_naive = timezone.datetime.combine(now.date() + timedelta(days=1), t)
        expected_aware = timezone.make_aware(
            expected_naive, timezone.get_current_timezone()
        )
        self.assertEqual(result, expected_aware)

    def test_combine_date_and_time_with_shift_returns_aware_datetime(self):
        """
        Test that combine_date_and_time_with_shift always returns a timezone-aware datetime.
        This test ensures the fix for the Sentry error where naive datetime was returned.
        """
        t = datetime_time(7, 0)
        today = timezone.now().date()
        result = self.service.combine_date_and_time_with_shift(today, t, 1)

        # Must be timezone-aware
        self.assertFalse(timezone.is_naive(result))
        self.assertTrue(timezone.is_aware(result))

    def test_make_aware_if_naive(self):
        """Test if a naive datetime is made aware."""
        now = datetime.datetime.now()
        self.assertEqual(
            self.service.make_aware_if_naive(now),
            timezone.make_aware(now),
        )

    def test_get_next_available_time_in_a_weekday_before_period(self):
        dt = timezone.datetime(
            2025, 1, 30, 5, 00, tzinfo=timezone.get_current_timezone()
        )

        self.assertEqual(dt.weekday(), THURSDAY)

        weekdays_period = {"from": "08:00", "to": "20:00"}
        saturdays_period = {"from": "10:00", "to": "12:00"}

        next_available_time = self.service.get_next_available_time(
            dt, weekdays_period, saturdays_period
        )

        self.assertEqual(next_available_time.weekday(), THURSDAY)
        self.assertEqual(
            next_available_time,
            timezone.datetime(
                2025, 1, 30, 8, 00, tzinfo=timezone.get_current_timezone()
            ),
        )

    def test_get_next_available_time_in_a_weekday_inside_period(self):
        dt = timezone.datetime(
            2025, 1, 30, 20, 00, tzinfo=timezone.get_current_timezone()
        ) - timedelta(seconds=self.service.default_abandoned_countdown + 60)

        self.assertEqual(dt.weekday(), THURSDAY)

        weekdays_period = {"from": "08:00", "to": "20:00"}
        saturdays_period = {"from": "10:00", "to": "12:00"}

        next_available_time = self.service.get_next_available_time(
            dt, weekdays_period, saturdays_period
        )

        self.assertEqual(next_available_time.weekday(), THURSDAY)
        self.assertEqual(
            next_available_time.date(),
            dt.date(),
        )

    def test_get_next_available_time_in_a_weekday(self):
        dt = timezone.datetime(
            2025, 1, 30, 20, 00, tzinfo=timezone.get_current_timezone()
        ) - timedelta(seconds=self.service.default_abandoned_countdown - 60)

        self.assertEqual(dt.weekday(), THURSDAY)

        weekdays_period = {"from": "08:00", "to": "20:00"}
        saturdays_period = {"from": "10:00", "to": "12:00"}

        expected_next_available_time = self.service.convert_str_time_to_time(
            weekdays_period["from"]
        )

        next_available_time = self.service.get_next_available_time(
            dt, weekdays_period, saturdays_period
        )

        self.assertEqual(next_available_time.weekday(), FRIDAY)
        self.assertEqual(
            next_available_time,
            self.service.combine_date_and_time_with_shift(
                dt.date(), expected_next_available_time, 1
            ),
        )

    def test_get_next_available_time_in_a_friday(self):
        dt = timezone.datetime(
            2025, 1, 31, 20, 00, tzinfo=timezone.get_current_timezone()
        ) - timedelta(seconds=self.service.default_abandoned_countdown - 60)

        self.assertEqual(dt.weekday(), FRIDAY)

        weekdays_period = {"from": "08:00", "to": "20:00"}
        saturdays_period = {"from": "10:00", "to": "12:00"}

        expected_next_available_time = self.service.convert_str_time_to_time(
            saturdays_period["from"]
        )

        next_available_time = self.service.get_next_available_time(
            dt, weekdays_period, saturdays_period
        )

        self.assertEqual(next_available_time.weekday(), SATURDAY)
        self.assertEqual(
            next_available_time,
            self.service.combine_date_and_time_with_shift(
                dt.date(), expected_next_available_time, 1
            ),
        )

    def test_get_next_available_time_in_a_saturday(self):
        dt = timezone.datetime(
            2025, 2, 1, 12, 00, tzinfo=timezone.get_current_timezone()
        ) - timedelta(seconds=self.service.default_abandoned_countdown - 60)

        self.assertEqual(dt.weekday(), SATURDAY)

        weekdays_period = {"from": "08:00", "to": "20:00"}
        saturdays_period = {"from": "10:00", "to": "12:00"}

        expected_next_available_time = self.service.convert_str_time_to_time(
            weekdays_period["from"]
        )

        next_available_time = self.service.get_next_available_time(
            dt, weekdays_period, saturdays_period
        )

        self.assertEqual(next_available_time.weekday(), MONDAY)
        self.assertEqual(
            next_available_time,
            self.service.combine_date_and_time_with_shift(
                dt.date(), expected_next_available_time, 2
            ),
        )

    def test_get_next_available_time_in_a_saturday_before_period(self):
        dt = timezone.datetime(
            2025, 2, 1, 7, 00, tzinfo=timezone.get_current_timezone()
        )

        self.assertEqual(dt.weekday(), SATURDAY)

        weekdays_period = {"from": "08:00", "to": "20:00"}
        saturdays_period = {"from": "10:00", "to": "12:00"}

        next_available_time = self.service.get_next_available_time(
            dt, weekdays_period, saturdays_period
        )

        self.assertEqual(next_available_time.weekday(), SATURDAY)
        self.assertEqual(
            next_available_time,
            timezone.datetime(
                2025, 2, 1, 10, 00, tzinfo=timezone.get_current_timezone()
            ),
        )

    def test_get_next_available_time_in_a_saturday_inside_period(self):
        dt = timezone.datetime(
            2025, 2, 1, 12, 00, tzinfo=timezone.get_current_timezone()
        ) - timedelta(seconds=self.service.default_abandoned_countdown + 60)

        self.assertEqual(dt.weekday(), SATURDAY)

        weekdays_period = {"from": "08:00", "to": "20:00"}
        saturdays_period = {"from": "10:00", "to": "12:00"}

        next_available_time = self.service.get_next_available_time(
            dt, weekdays_period, saturdays_period
        )

        self.assertEqual(dt.weekday(), SATURDAY)
        self.assertEqual(
            next_available_time.date(),
            dt.date(),
        )

    def test_get_next_available_time_in_a_sunday(self):
        dt = timezone.datetime(
            2025, 2, 2, 12, 00, tzinfo=timezone.get_current_timezone()
        ) - timedelta(seconds=self.service.default_abandoned_countdown - 60)

        self.assertEqual(dt.weekday(), SUNDAY)

        weekdays_period = {"from": "08:00", "to": "20:00"}
        saturdays_period = {"from": "10:00", "to": "12:00"}

        expected_next_available_time = self.service.convert_str_time_to_time(
            weekdays_period["from"]
        )

        next_available_time = self.service.get_next_available_time(
            dt, weekdays_period, saturdays_period
        )

        self.assertEqual(next_available_time.weekday(), MONDAY)
        self.assertEqual(
            next_available_time,
            self.service.combine_date_and_time_with_shift(
                dt.date(), expected_next_available_time, 1
            ),
        )

    def test_calculate_abandoned_cart_countdown_for_inactive_time_restriction(self):
        feature = Feature.objects.create()
        project = Project.objects.create(uuid=uuid.uuid4())
        user = User.objects.create()
        config = {
            "integration_settings": {
                "message_time_restriction": {
                    "is_active": False,
                }
            }
        }

        integrated_feature = IntegratedFeature.objects.create(
            feature=feature, project=project, config=config, user=user
        )
        countdown = self.service(integrated_feature=integrated_feature).get_countdown()

        self.assertEqual(countdown, self.service.default_abandoned_countdown)

    @mock.patch(
        "retail.webhooks.vtex.services.CartTimeRestrictionService.get_next_available_time"
    )
    def test_calculate_abandoned_cart_countdown_for_active_time_restriction(
        self, mock_get_next_available_time
    ):
        feature = Feature.objects.create()
        project = Project.objects.create(uuid=uuid.uuid4())
        user = User.objects.create()
        config = {
            "integration_settings": {
                "message_time_restriction": {
                    "is_active": True,
                    "periods": {
                        "weekdays": {
                            "from": "08:00",
                            "to": "20:00",
                        },
                        "saturdays": {
                            "from": "10:00",
                            "to": "12:00",
                        },
                    },
                }
            }
        }

        mock_get_next_available_time.return_value = timezone.now() + timedelta(
            seconds=3600
        )

        integrated_feature = IntegratedFeature.objects.create(
            feature=feature, project=project, config=config, user=user
        )
        countdown = self.service(integrated_feature=integrated_feature).get_countdown()

        self.assertAlmostEqual(countdown, 3600, delta=45)

    def test_get_next_available_time_returns_aware_datetime_on_sunday_night(self):
        """
        Test that replicates the Sentry error scenario.

        Sentry data:
        - now = datetime.datetime(2025, 12, 21, 22, 59, 22, 160444, tzinfo=datetime.timezone.utc)
        - next_available_time was naive: datetime.datetime(2025, 12, 22, 7, 0)

        The bug was that (next_available_time - now).seconds raised TypeError
        because next_available_time was naive and now was aware.
        """
        # Sunday, December 21, 2025, 22:59 UTC (exactly like Sentry)
        now_utc = datetime.datetime(
            2025, 12, 21, 22, 59, 22, 160444, tzinfo=datetime.timezone.utc
        )

        weekdays_period = {"from": "07:00", "to": "23:00"}
        saturdays_period = {"from": "09:00", "to": "20:00"}

        next_available_time = self.service.get_next_available_time(
            now_utc, weekdays_period, saturdays_period
        )

        # Must be timezone-aware (this was the bug - it was naive before)
        self.assertTrue(
            timezone.is_aware(next_available_time),
            f"next_available_time should be aware, but got: {next_available_time}",
        )

        # Should be Monday (next weekday)
        self.assertEqual(next_available_time.weekday(), MONDAY)

        # This subtraction should NOT raise TypeError anymore
        try:
            countdown_seconds = (next_available_time - now_utc).seconds
            self.assertIsInstance(countdown_seconds, int)
            self.assertGreater(countdown_seconds, 0)
        except TypeError as e:
            self.fail(f"Subtraction raised TypeError (naive vs aware): {e}")

    def test_get_countdown_with_utc_timezone_does_not_raise_typeerror(self):
        """
        Integration test that replicates the exact Sentry error.

        This test uses the real get_countdown method with UTC timezone
        to ensure the fix works end-to-end.
        """
        feature = Feature.objects.create()
        project = Project.objects.create(uuid=uuid.uuid4())
        user = User.objects.create()
        config = {
            "integration_settings": {
                "message_time_restriction": {
                    "is_active": True,
                    "periods": {
                        "weekdays": {"from": "07:00", "to": "23:00"},
                        "saturdays": {"from": "09:00", "to": "20:00"},
                    },
                }
            }
        }

        integrated_feature = IntegratedFeature.objects.create(
            feature=feature, project=project, config=config, user=user
        )

        # Mock timezone.now() to return UTC datetime (like in Sentry)
        # Sunday night, which triggers the "return next monday" path
        sunday_night_utc = datetime.datetime(
            2025, 12, 21, 22, 59, 22, 160444, tzinfo=datetime.timezone.utc
        )

        with mock.patch(
            "retail.webhooks.vtex.services.timezone.now", return_value=sunday_night_utc
        ):
            try:
                countdown = self.service(
                    integrated_feature=integrated_feature
                ).get_countdown()
                self.assertIsInstance(countdown, int)
                self.assertGreater(countdown, 0)
            except TypeError as e:
                self.fail(
                    f"get_countdown raised TypeError (naive vs aware datetime): {e}"
                )

    def test_get_next_available_time_friday_night_returns_aware_datetime(self):
        """
        Test Friday night scenario where next available is Saturday.
        Ensures the Saturday path also returns aware datetime.
        """
        # Friday, January 31, 2025, 21:00 local time (after 20:00 weekday limit)
        friday_night = timezone.datetime(
            2025, 1, 31, 21, 0, 0, 0, tzinfo=timezone.get_current_timezone()
        )

        self.assertEqual(friday_night.weekday(), FRIDAY)

        weekdays_period = {"from": "08:00", "to": "20:00"}
        saturdays_period = {"from": "10:00", "to": "12:00"}

        next_available_time = self.service.get_next_available_time(
            friday_night, weekdays_period, saturdays_period
        )

        # Must be timezone-aware
        self.assertTrue(timezone.is_aware(next_available_time))

        # Should be Saturday
        self.assertEqual(next_available_time.weekday(), SATURDAY)

        # Subtraction should work
        countdown_seconds = (next_available_time - friday_night).seconds
        self.assertIsInstance(countdown_seconds, int)

    def test_get_next_available_time_saturday_night_returns_aware_datetime(self):
        """
        Test Saturday night scenario where next available is Monday.
        Ensures the Saturday after-hours path returns aware datetime.
        """
        # Saturday, December 20, 2025, 15:00 UTC (after 12:00 Saturday limit)
        saturday_afternoon_utc = datetime.datetime(
            2025, 12, 20, 15, 0, 0, 0, tzinfo=datetime.timezone.utc
        )

        weekdays_period = {"from": "08:00", "to": "20:00"}
        saturdays_period = {"from": "10:00", "to": "12:00"}

        next_available_time = self.service.get_next_available_time(
            saturday_afternoon_utc, weekdays_period, saturdays_period
        )

        # Must be timezone-aware
        self.assertTrue(timezone.is_aware(next_available_time))

        # Should be Monday
        self.assertEqual(next_available_time.weekday(), MONDAY)

        # Subtraction should work
        countdown_seconds = (next_available_time - saturday_afternoon_utc).seconds
        self.assertIsInstance(countdown_seconds, int)

    def test_get_next_available_time_weekday_after_hours_returns_aware_datetime(self):
        """
        Test weekday after hours scenario where next available is next weekday.
        Ensures the weekday after-hours path returns aware datetime.
        """
        # Thursday, January 30, 2025, 21:00 local time (after 20:00 weekday limit)
        thursday_night = timezone.datetime(
            2025, 1, 30, 21, 0, 0, 0, tzinfo=timezone.get_current_timezone()
        )

        self.assertEqual(thursday_night.weekday(), THURSDAY)

        weekdays_period = {"from": "08:00", "to": "20:00"}
        saturdays_period = {"from": "10:00", "to": "12:00"}

        next_available_time = self.service.get_next_available_time(
            thursday_night, weekdays_period, saturdays_period
        )

        # Must be timezone-aware
        self.assertTrue(timezone.is_aware(next_available_time))

        # Should be Friday
        self.assertEqual(next_available_time.weekday(), FRIDAY)

        # Subtraction should work
        countdown_seconds = (next_available_time - thursday_night).seconds
        self.assertIsInstance(countdown_seconds, int)


class TestCartPhoneRestrictionService(TestCase):
    def setUp(self):
        self.feature = Feature.objects.create()
        self.project = Project.objects.create(uuid=uuid.uuid4())
        self.user = User.objects.create()

    def test_validate_phone_restriction_no_restriction_active(self):
        """Test phone validation when no restriction is active."""
        config = {
            "integration_settings": {
                "abandoned_cart_restriction": {
                    "is_active": False,
                }
            }
        }

        integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature, project=self.project, config=config, user=self.user
        )
        service = CartPhoneRestrictionService(integrated_feature)

        # Should allow any phone when restriction is not active
        self.assertTrue(service.validate_phone_restriction("5584987654321"))

    def test_validate_phone_restriction_active_no_phone_numbers(self):
        """Test phone validation when restriction is active but no phone numbers configured."""
        config = {
            "integration_settings": {
                "abandoned_cart_restriction": {
                    "is_active": True,
                    "phone_numbers": [],
                }
            }
        }

        integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature, project=self.project, config=config, user=self.user
        )
        service = CartPhoneRestrictionService(integrated_feature)

        # Should block when restriction is active but no numbers configured
        self.assertFalse(service.validate_phone_restriction("5584987654321"))

    def test_validate_phone_restriction_active_phone_allowed(self):
        """Test phone validation when restriction is active and phone is allowed."""
        config = {
            "integration_settings": {
                "abandoned_cart_restriction": {
                    "is_active": True,
                    "phone_numbers": ["5584987654321", "5584987654322"],
                }
            }
        }

        integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature, project=self.project, config=config, user=self.user
        )
        service = CartPhoneRestrictionService(integrated_feature)

        # Should allow phone that is in the allowed list
        self.assertTrue(service.validate_phone_restriction("5584987654321"))
        self.assertTrue(service.validate_phone_restriction("5584987654322"))

    def test_validate_phone_restriction_active_phone_blocked(self):
        """Test phone validation when restriction is active and phone is blocked."""
        config = {
            "integration_settings": {
                "abandoned_cart_restriction": {
                    "is_active": True,
                    "phone_numbers": ["5584987654321", "5584987654322"],
                }
            }
        }

        integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature, project=self.project, config=config, user=self.user
        )
        service = CartPhoneRestrictionService(integrated_feature)

        # Should block phone that is not in the allowed list
        self.assertFalse(service.validate_phone_restriction("5584987654323"))

    def test_validate_phone_restriction_normalizes_numbers(self):
        """Test that phone numbers are normalized before comparison."""
        config = {
            "integration_settings": {
                "abandoned_cart_restriction": {
                    "is_active": True,
                    "phone_numbers": ["+55 84 98765-4321", "+55 84 98765-4322"],
                }
            }
        }

        integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature, project=self.project, config=config, user=self.user
        )
        service = CartPhoneRestrictionService(integrated_feature)

        # Should allow normalized numbers that match the normalized allowed list
        self.assertTrue(service.validate_phone_restriction("5584987654321"))
        self.assertTrue(service.validate_phone_restriction("5584987654322"))

    def test_validate_phone_restriction_missing_config(self):
        """Test phone validation when restriction config is missing."""
        config = {"integration_settings": {}}

        integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature, project=self.project, config=config, user=self.user
        )
        service = CartPhoneRestrictionService(integrated_feature)

        # Should allow any phone when restriction config is missing
        self.assertTrue(service.validate_phone_restriction("5584987654321"))
