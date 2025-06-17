from calendar import FRIDAY, MONDAY, SATURDAY
from datetime import date, time
import logging
from django.utils import timezone
from django.utils.timezone import timedelta
from django.conf import settings

from retail.features.models import IntegratedFeature
from sentry_sdk import capture_exception, capture_message

logger = logging.getLogger(__name__)


class CartTimeRestrictionService:
    """
    This class is responsible for calculating the countdown time for the abandoned cart feature.
    """

    default_abandoned_countdown = settings.ABANDONED_CART_COUNTDOWN * 60

    def __init__(self, integrated_feature: IntegratedFeature):
        self.integrated_feature = integrated_feature

    @staticmethod
    def is_weekday(day: int) -> bool:
        """
        Returns True if the day is a weekday (Monday to Friday), False otherwise.
        """
        return MONDAY <= day <= FRIDAY

    @staticmethod
    def is_saturday(day: int) -> bool:
        """
        Returns True if the day is Saturday, False otherwise.
        """
        return day == SATURDAY

    @staticmethod
    def convert_str_time_to_time(time_str: str) -> time:
        """
        Converts a string representation of time to a time object.
        """
        return timezone.datetime.strptime(time_str, "%H:%M").time()

    @staticmethod
    def combine_date_and_time_with_shift(
        dt: date, t: time, shift: int
    ) -> timezone.datetime:
        """
        Combines a date and time with a shift to calculate the next available time.
        """
        return timezone.datetime.combine(dt + timezone.timedelta(days=shift), t)

    @staticmethod
    def make_aware_if_naive(dt: timezone.datetime) -> timezone.datetime:
        """
        Makes a datetime object timezone-aware if naive
        """
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())

        return dt

    @classmethod
    def get_next_available_time(
        cls,
        now: timezone.datetime,
        weekdays_period: dict,
        saturdays_period: dict,
    ) -> timezone.datetime:
        """
        Returns the next available time based on the provided periods.
        """
        current_weekday = now.weekday()

        # This is the time to be returned for the cases when the current time
        # is not outside the allowed periods.
        # Example:
        # If the current time is 10:00 AM and the allowed period is 08:00 AM to 18:00 PM,
        # then the default_current_day_time will be 10:00 AM plus the default abandoned cart countdown.
        # If the this default countdown is 25 minutes, then the default_current_day_time will be 10:25 AM.
        default_current_day_time = now + timedelta(
            seconds=cls.default_abandoned_countdown
        )

        # If the current day is a weekday, we need to check the weekdays period
        # for the last first and last time allowed for the day,
        # to check if the current time is inside or outside the allowed periods.
        if cls.is_weekday(current_weekday):
            from_time_str = weekdays_period.get("from")
            to_time_str = weekdays_period.get("to")

            from_time = cls.convert_str_time_to_time(from_time_str)
            to_time = cls.convert_str_time_to_time(to_time_str)

            # The first time allowed for the day is the "from" time configured for
            # the weekdays period.
            # Example: 08:00 AM
            first_time_allowed_for_day = cls.make_aware_if_naive(
                cls.combine_date_and_time_with_shift(now.date(), from_time, 0)
            )

            # The last time allowed for the day is the "to" time configured for
            # the weekdays period.
            # Example: 18:00 PM
            last_time_allowed_for_day = cls.make_aware_if_naive(
                cls.combine_date_and_time_with_shift(now.date(), to_time, 0)
            )

            # If the current time is before the first time allowed for the day,
            # we need to return the first time allowed for the day.
            # Example: If the current time is 07:00 AM and the first time allowed for the day is 08:00 AM,
            # we need to return 08:00 AM.
            if default_current_day_time < first_time_allowed_for_day:
                return first_time_allowed_for_day

            # If the current time is after the last time allowed for the day,
            # we need to return the first time allowed for the next day.
            # Example: If the current time is 19:00 PM and the last time allowed for the day is 18:00 PM,
            # and the first time allowed for the next day is 08:00 AM,
            # we need to return 08:00 AM of the next day.
            if default_current_day_time < last_time_allowed_for_day:
                return default_current_day_time

            # If the next day is Saturday, we need to check the saturdays period
            # to get the next available time based on the saturdays period.
            if cls.is_saturday(current_weekday + 1):
                saturdays_from_time_str = saturdays_period.get("from")

                next_from_time = cls.convert_str_time_to_time(saturdays_from_time_str)
                return cls.combine_date_and_time_with_shift(
                    now.date(), next_from_time, 1
                )

            # If the next day is not Saturday, we need to check the weekdays period
            # to get the next available time based on the weekdays period.
            # Example: If the current time is 19:00 PM and the last time allowed for the day is 18:00 PM,
            # and the first time allowed for the next day is 08:00 AM,
            # we need to return 08:00 AM of the next day.
            else:
                next_from_time = cls.convert_str_time_to_time(from_time_str)
                return cls.combine_date_and_time_with_shift(
                    now.date(), next_from_time, 1
                )

        # If the current day is a Saturday, we need to check the saturdays period
        # for the last first and last time allowed for the day,
        # to check if the current time is inside or outside the allowed periods.
        elif cls.is_saturday(current_weekday):
            saturdays_from_time_str = saturdays_period.get("from")
            from_time = cls.convert_str_time_to_time(saturdays_from_time_str)

            saturdays_to_time_str = saturdays_period.get("to")
            to_time = cls.convert_str_time_to_time(saturdays_to_time_str)

            # The first time allowed for the day is the "from" time configured for
            # the saturdays period.
            first_time_allowed_for_day = cls.make_aware_if_naive(
                cls.combine_date_and_time_with_shift(now.date(), from_time, 0)
            )

            # The last time allowed for the day is the "to" time configured for
            # the saturdays period.
            last_time_allowed_for_day = cls.make_aware_if_naive(
                cls.combine_date_and_time_with_shift(now.date(), to_time, 0)
            )

            # If the current time is before the first time allowed for the day,
            # we need to return the first time allowed for the day.
            # Example: If the current time is 07:00 AM and the first time allowed for the day is 08:00 AM,
            # we need to return 08:00 AM.
            if default_current_day_time < first_time_allowed_for_day:
                return first_time_allowed_for_day

            # If the current time is after the last time allowed for the day,
            # we need to return the first time allowed for the next day.
            # Example: If the current time is 19:00 PM and the last time allowed for the day is 18:00 PM,
            # and the first time allowed for the next day is 08:00 AM,
            # we need to return 08:00 AM of the next day.
            if default_current_day_time < last_time_allowed_for_day:
                return default_current_day_time

            next_from_time_str = weekdays_period.get("from")
            next_from_time = cls.convert_str_time_to_time(next_from_time_str)

            return cls.combine_date_and_time_with_shift(now.date(), next_from_time, 2)

        # If the current day is a sunday, we need to return the first time allowed for the monday.
        else:
            next_from_time_str = weekdays_period.get("from")
            next_from_time = cls.convert_str_time_to_time(next_from_time_str)

            return cls.combine_date_and_time_with_shift(now.date(), next_from_time, 1)

    def get_countdown(self) -> int:
        """
        Returns the countdown in seconds for the current time.
        """
        feature_settings = self.integrated_feature.config.get(
            "integration_settings", {}
        )
        message_time_restriction = feature_settings.get("message_time_restriction", {})
        is_active = message_time_restriction.get("is_active", False)

        if not is_active:
            return self.default_abandoned_countdown

        periods = message_time_restriction.get("periods", [])
        weekdays_period = periods.get("weekdays", {})
        saturdays_period = periods.get("saturdays", {})

        if not weekdays_period or not saturdays_period:
            error_message = f"Invalid message time restriction settings for abandoned cart feature (Integrated feature UUID: {self.integrated_feature.uuid})"  # noqa: E501
            logger.error(error_message, exc_info=True)
            capture_message(error_message)
            return self.default_abandoned_countdown

        now = timezone.now()

        try:
            next_available_time = self.get_next_available_time(
                now=now,
                weekdays_period=weekdays_period,
                saturdays_period=saturdays_period,
            )
        except Exception as e:
            error_message = f"Could not calculate the next available time for the integrated feature with UUID {self.integrated_feature.uuid}. Error: {str(e)}"  # noqa: E501
            logger.error(error_message, exc_info=True)
            capture_exception(e)
            return self.default_abandoned_countdown

        return (next_available_time - now).seconds
