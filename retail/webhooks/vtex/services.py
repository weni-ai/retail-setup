from calendar import FRIDAY, MONDAY, SATURDAY
from datetime import date, time
import logging
from django.utils import timezone
from django.utils.timezone import timedelta
from django.conf import settings
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass

from retail.features.models import IntegratedFeature
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.vtex.usecases.phone_number_normalizer import PhoneNumberNormalizer
from sentry_sdk import capture_exception, capture_message

logger = logging.getLogger(__name__)


@dataclass
class CartServiceContext:
    """
    Context for cart services with all necessary information.
    """

    project_uuid: str
    config: Dict[str, Any]
    entity_type: str  # 'integrated_feature' or 'integrated_agent'
    entity_uuid: Optional[str] = None


class ConfigProvider(ABC):
    """
    Abstract base class for entities that provide configuration data.
    """

    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        """Return the configuration dictionary."""
        pass


class IntegratedFeatureConfigProvider(ConfigProvider):
    """Config provider for IntegratedFeature."""

    def __init__(self, integrated_feature: IntegratedFeature):
        self.integrated_feature = integrated_feature

    def get_config(self) -> Dict[str, Any]:
        return self.integrated_feature.config


class IntegratedAgentConfigProvider(ConfigProvider):
    """Config provider for IntegratedAgent."""

    def __init__(self, integrated_agent: IntegratedAgent):
        self.integrated_agent = integrated_agent

    def get_config(self) -> Dict[str, Any]:
        return self.integrated_agent.config


class CartTimeRestrictionService:
    """
    This class is responsible for calculating the countdown time for the abandoned cart feature.

    For IntegratedAgent, the abandonment time can be configured via the agent's config
    under the 'abandoned_cart.abandonment_time_minutes' key. If not configured,
    falls back to the environment variable ABANDONED_CART_COUNTDOWN.
    """

    default_abandoned_countdown = settings.ABANDONED_CART_COUNTDOWN * 60

    def __init__(self, context: CartServiceContext):
        self.context = context

    def _get_abandonment_countdown_seconds(self) -> int:
        """
        Get the abandonment countdown in seconds based on configuration.

        For IntegratedAgent, checks config['abandoned_cart']['abandonment_time_minutes'].
        Falls back to default ABANDONED_CART_COUNTDOWN if not configured.

        Returns:
            int: Countdown time in seconds.
        """
        config = self.context.config

        # Check if this is an integrated agent with abandoned_cart config
        if self.context.entity_type == "integrated_agent":
            abandoned_cart_config = config.get("abandoned_cart", {})
            abandonment_time_minutes = abandoned_cart_config.get(
                "abandonment_time_minutes"
            )

            if abandonment_time_minutes is not None:
                countdown_seconds = int(abandonment_time_minutes) * 60
                logger.info(
                    "Using configured abandonment time: %d minutes (%d seconds) "
                    "for integrated agent %s",
                    abandonment_time_minutes,
                    countdown_seconds,
                    self.context.entity_uuid,
                )
                return countdown_seconds

            # Log warning if config not found for integrated agent
            logger.warning(
                "Abandonment time not configured for integrated agent %s, "
                "using default %d minutes",
                self.context.entity_uuid,
                settings.ABANDONED_CART_COUNTDOWN,
            )

        return self.default_abandoned_countdown

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
        abandonment_countdown_seconds: int = None,
    ) -> timezone.datetime:
        """
        Returns the next available time based on the provided periods.

        Args:
            now: Current datetime.
            weekdays_period: Period configuration for weekdays.
            saturdays_period: Period configuration for Saturdays.
            abandonment_countdown_seconds: Countdown in seconds. If not provided,
                uses the default from settings.
        """
        current_weekday = now.weekday()

        # Use provided countdown or fall back to default
        countdown_seconds = (
            abandonment_countdown_seconds
            if abandonment_countdown_seconds is not None
            else cls.default_abandoned_countdown
        )

        # This is the time to be returned for the cases when the current time
        # is not outside the allowed periods.
        # Example:
        # If the current time is 10:00 AM and the allowed period is 08:00 AM to 18:00 PM,
        # then the default_current_day_time will be 10:00 AM plus the abandoned cart countdown.
        # If the countdown is 10 minutes, then the default_current_day_time will be 10:10 AM.
        default_current_day_time = now + timedelta(seconds=countdown_seconds)

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

        For IntegratedAgent, uses the configured abandonment_time_minutes from
        config['abandoned_cart']['abandonment_time_minutes'].
        Falls back to ABANDONED_CART_COUNTDOWN env var if not configured.
        """
        config = self.context.config

        # Get the appropriate countdown based on integration type
        abandonment_countdown = self._get_abandonment_countdown_seconds()

        # Both integrated feature and integrated agent use the same structure
        message_time_restriction = config.get("message_time_restriction", {})
        is_active = message_time_restriction.get("is_active", False)

        if not is_active:
            logger.info(
                "Message time restriction not active - using abandonment countdown: %d seconds "
                "(project=%s, entity=%s)",
                abandonment_countdown,
                self.context.project_uuid,
                self.context.entity_type,
            )
            return abandonment_countdown

        periods = message_time_restriction.get("periods", [])
        weekdays_period = periods.get("weekdays", {})
        saturdays_period = periods.get("saturdays", {})

        if not weekdays_period or not saturdays_period:
            error_message = (
                "Invalid message time restriction settings for abandoned cart. "
                f"Project: {self.context.project_uuid}, Entity: {self.context.entity_type}"
            )
            logger.error(error_message, exc_info=True)
            capture_message(error_message)
            return abandonment_countdown

        now = timezone.now()

        try:
            next_available_time = self.get_next_available_time(
                now=now,
                weekdays_period=weekdays_period,
                saturdays_period=saturdays_period,
                abandonment_countdown_seconds=abandonment_countdown,
            )
        except Exception as e:
            error_message = (
                "Could not calculate the next available time. "
                f"Project: {self.context.project_uuid}, Entity: {self.context.entity_type}. "
                f"Error: {str(e)}"
            )
            logger.error(error_message, exc_info=True)
            capture_exception(e)
            return abandonment_countdown

        final_countdown = (next_available_time - now).seconds
        logger.info(
            "Message time restriction applied - countdown: %d seconds, "
            "next_available_time: %s (project=%s, entity=%s)",
            final_countdown,
            next_available_time.isoformat(),
            self.context.project_uuid,
            self.context.entity_type,
        )
        return final_countdown


class CartPhoneRestrictionService:
    """
    This class is responsible for validating phone number restrictions for the abandoned cart feature.
    """

    def __init__(self, context: CartServiceContext):
        self.context = context

    def validate_phone_restriction(self, phone: str) -> bool:
        """
        Validates if the phone number is allowed based on the configured restrictions.

        Args:
            phone (str): The normalized phone number to validate.

        Returns:
            bool: True if the phone is allowed, False if it should be blocked.
        """
        config = self.context.config

        # Both integrated feature and integrated agent use the same structure
        abandoned_cart_restriction = config.get("abandoned_cart_restriction", {})

        if not abandoned_cart_restriction.get("is_active", False):
            logger.info(
                f"No abandoned cart phone restriction active for project: {self.context.project_uuid}"
            )
            return True

        phone_list_restriction = abandoned_cart_restriction.get("phone_numbers", [])

        if not phone_list_restriction:
            logger.info(
                "Abandoned cart phone restriction active but no phone numbers configured "
                f"for project: {self.context.project_uuid}. Blocking by default."
            )
            return False

        # Normalize all numbers in the restriction list
        normalized_phones = {
            PhoneNumberNormalizer.normalize(number) for number in phone_list_restriction
        }

        if phone not in normalized_phones:
            logger.info(
                f"Phone {phone} blocked due to abandoned cart phone "
                f"restriction for project: {self.context.project_uuid}. "
                f"Allowed numbers: {normalized_phones}"
            )
            return False

        logger.info(
            f"Phone {phone} allowed through abandoned cart phone "
            f"restriction for project: {self.context.project_uuid}."
        )
        return True
