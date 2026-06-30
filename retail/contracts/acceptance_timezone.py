"""Timezone helpers for contract acceptance timestamps."""

from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.utils import timezone as dj_timezone

ACCEPTANCE_LOCAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def resolve_acceptance_local_offset(accepted_at: datetime) -> str:
    """Return the UTC offset (±HH:MM) for ``accepted_at`` in the acceptance timezone."""
    if dj_timezone.is_naive(accepted_at):
        accepted_at = dj_timezone.make_aware(accepted_at, dt_timezone.utc)

    local_dt = accepted_at.astimezone(ACCEPTANCE_LOCAL_TIMEZONE)
    offset = local_dt.utcoffset()
    if offset is None:
        return "+00:00"

    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"{sign}{hours:02d}:{minutes:02d}"
