from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.test import TestCase

from retail.contracts.acceptance_timezone import resolve_acceptance_local_offset


class ResolveAcceptanceLocalOffsetTests(TestCase):
    def test_returns_sao_paulo_offset_for_utc_timestamp(self):
        accepted_at = datetime(2026, 6, 10, 14, 32, tzinfo=dt_timezone.utc)

        offset = resolve_acceptance_local_offset(accepted_at)

        self.assertEqual(offset, "-03:00")

    def test_accepts_naive_datetime_as_utc(self):
        accepted_at = datetime(2026, 6, 10, 14, 32)

        offset = resolve_acceptance_local_offset(accepted_at)

        self.assertEqual(offset, "-03:00")

    def test_returns_zero_offset_when_utcoffset_is_none(self):
        accepted_at = MagicMock()
        local_dt = MagicMock()
        local_dt.utcoffset.return_value = None
        accepted_at.astimezone.return_value = local_dt

        with patch(
            "retail.contracts.acceptance_timezone.dj_timezone.is_naive",
            return_value=False,
        ):
            offset = resolve_acceptance_local_offset(accepted_at)

        self.assertEqual(offset, "+00:00")
