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
        self.assertEqual(
            self.service.combine_date_and_time_with_shift(now.date(), t, 1),
            timezone.datetime.combine(now.date() + timedelta(days=1), t),
        )

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
