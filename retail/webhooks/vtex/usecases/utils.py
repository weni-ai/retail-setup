import time
from django.utils import timezone
from django.utils.timezone import timedelta

from retail.features.models import IntegratedFeature
from sentry_sdk import capture_exception


DEFAULT_ABANDONED_CART_COUNTDOWN = 25 * 60


def is_weekday(day: int) -> bool:
    return 0 <= day <= 4


def is_saturday(day: int) -> bool:
    return day == 5


def convert_str_time_to_time(time_str: str) -> time:
    return timezone.datetime.strptime(time_str, "%H:%M").time()


def combine_date_and_time_with_shift(shift: int, t: time) -> timezone.datetime:
    return timezone.datetime.combine(
        timezone.now().date() + timezone.timedelta(days=shift), t
    )


def get_next_available_time(
    now: timezone.datetime,
    weekdays_period: dict,
    saturdays_period: dict,
) -> timezone.datetime:
    current_weekday = now.weekday()
    default_current_day_time = now + timedelta(seconds=DEFAULT_ABANDONED_CART_COUNTDOWN)

    if is_weekday(current_weekday):
        from_time_str = weekdays_period.get("from")
        to_time_str = weekdays_period.get("to")

        from_time = convert_str_time_to_time(from_time_str)
        to_time = convert_str_time_to_time(to_time_str)

        if combine_date_and_time_with_shift(0, to_time) < default_current_day_time:
            return default_current_day_time

        if is_saturday(current_weekday + 1):
            if not saturdays_period:
                return combine_date_and_time_with_shift(3, from_time)

            saturdays_from_time_str = saturdays_period.get("from")

            next_from_time = convert_str_time_to_time(saturdays_from_time_str)
            return combine_date_and_time_with_shift(1, next_from_time)

        else:
            next_from_time = convert_str_time_to_time(from_time_str)
            return combine_date_and_time_with_shift(1, next_from_time)

    else:
        to_time_str = saturdays_from_time_str.get("to")
        to_time = convert_str_time_to_time(to_time_str)

        if combine_date_and_time_with_shift(0, to_time) < default_current_day_time:
            return default_current_day_time

        shift = 2 if is_saturday(current_weekday) else 1

        next_from_time_str = weekdays_period.get("from")
        next_from_time = convert_str_time_to_time(next_from_time_str)

        return combine_date_and_time_with_shift(shift, next_from_time)


def calculate_abandoned_cart_countdown(integrated_feature: IntegratedFeature) -> int:
    feature_settings = integrated_feature.config.get("integration_settings", {})
    message_time_restriction = feature_settings.get("message_time_restriction", {})
    is_active = message_time_restriction.get("is_active", False)

    if not is_active:
        return DEFAULT_ABANDONED_CART_COUNTDOWN

    periods = message_time_restriction.get("periods", [])
    weekdays_period = periods.get("weekdays", {})
    saturdays_period = periods.get("saturdays", {})

    now = timezone.now()

    try:
        next_available_time = get_next_available_time(
            now=now,
            weekdays_period=weekdays_period,
            saturdays_period=saturdays_period,
        )
    except Exception as e:
        capture_exception(e)
        return DEFAULT_ABANDONED_CART_COUNTDOWN

    return (next_available_time - now).seconds
