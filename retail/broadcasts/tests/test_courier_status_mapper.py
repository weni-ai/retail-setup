from django.test import TestCase

from retail.broadcasts.models import BroadcastStatus
from retail.broadcasts.services.courier_status_mapper import CourierStatusMapper


class CourierStatusMapperTest(TestCase):
    def test_each_letter_maps_to_its_dedicated_status(self):
        cases = {
            "P": BroadcastStatus.PENDING,
            "Q": BroadcastStatus.QUEUED,
            "S": BroadcastStatus.SENT,
            "W": BroadcastStatus.WIRED,
            "D": BroadcastStatus.DELIVERED,
            "V": BroadcastStatus.READ,
            "E": BroadcastStatus.ERRORED,
            "F": BroadcastStatus.FAILED,
        }
        for letter, expected in cases.items():
            with self.subTest(letter=letter):
                self.assertEqual(CourierStatusMapper.map(letter), expected)

    def test_unknown_letter_maps_to_unknown(self):
        self.assertEqual(CourierStatusMapper.map("X"), BroadcastStatus.UNKNOWN)

    def test_empty_string_returns_none(self):
        self.assertIsNone(CourierStatusMapper.map(""))

    def test_none_returns_none(self):
        self.assertIsNone(CourierStatusMapper.map(None))
