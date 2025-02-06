from calendar import FRIDAY, MONDAY, SATURDAY
from datetime import date, time
from django.utils import timezone
from django.utils.timezone import timedelta

from retail.features.models import IntegratedFeature
from sentry_sdk import capture_exception, capture_message


DEFAULT_ABANDONED_CART_COUNTDOWN = 25 * 60


def is_weekday(day: int) -> bool:
    return MONDAY <= day <= FRIDAY


def is_saturday(day: int) -> bool:
    return day == SATURDAY


def convert_str_time_to_time(time_str: str) -> time:
    return timezone.datetime.strptime(time_str, "%H:%M").time()


def combine_date_and_time_with_shift(
    dt: date, t: time, shift: int
) -> timezone.datetime:
    return timezone.datetime.combine(dt + timezone.timedelta(days=shift), t)


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

        last_time_allowed_for_day = combine_date_and_time_with_shift(
            now.date(), to_time, 0
        )

        if timezone.is_naive(last_time_allowed_for_day):
            last_time_allowed_for_day = timezone.make_aware(
                last_time_allowed_for_day, timezone.get_current_timezone()
            )

        if default_current_day_time < last_time_allowed_for_day:
            return default_current_day_time

        if is_saturday(current_weekday + 1):
            if not saturdays_period:
                return combine_date_and_time_with_shift(now.date(), from_time, 3)

            saturdays_from_time_str = saturdays_period.get("from")

            next_from_time = convert_str_time_to_time(saturdays_from_time_str)
            return combine_date_and_time_with_shift(now.date(), next_from_time, 1)

        else:
            next_from_time = convert_str_time_to_time(from_time_str)
            return combine_date_and_time_with_shift(now.date(), next_from_time, 1)

    else:
        saturdays_to_time_str = saturdays_period.get("to")
        to_time = convert_str_time_to_time(saturdays_to_time_str)

        last_time_allowed_for_day = combine_date_and_time_with_shift(
            now.date(), to_time, 0
        )
        if timezone.is_naive(last_time_allowed_for_day):
            last_time_allowed_for_day = timezone.make_aware(
                last_time_allowed_for_day, timezone.get_current_timezone()
            )

        if default_current_day_time < last_time_allowed_for_day:
            return default_current_day_time

        shift = 2 if is_saturday(current_weekday) else 1

        next_from_time_str = weekdays_period.get("from")
        next_from_time = convert_str_time_to_time(next_from_time_str)

        return combine_date_and_time_with_shift(now.date(), next_from_time, shift)


def calculate_abandoned_cart_countdown(integrated_feature: IntegratedFeature) -> int:
    feature_settings = integrated_feature.config.get("integration_settings", {})
    message_time_restriction = feature_settings.get("message_time_restriction", {})
    is_active = message_time_restriction.get("is_active", False)

    if not is_active:
        return DEFAULT_ABANDONED_CART_COUNTDOWN

    periods = message_time_restriction.get("periods", [])
    weekdays_period = periods.get("weekdays", {})
    saturdays_period = periods.get("saturdays", {})

    if not weekdays_period or not saturdays_period:
        capture_message(
            f"Invalid message time restriction settings for abandoned cart feature (Integrated feature UUID: {integrated_feature.uuid})"
        )
        return DEFAULT_ABANDONED_CART_COUNTDOWN

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
