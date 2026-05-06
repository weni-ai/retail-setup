from django.test import TestCase

from retail.broadcasts.models import BroadcastStatus
from retail.broadcasts.services.flows_status_mapper import FlowsStatusMapper


class FlowsStatusMapperTest(TestCase):
    def test_maps_queued(self):
        self.assertEqual(FlowsStatusMapper.map("queued"), BroadcastStatus.QUEUED)

    def test_maps_sent(self):
        self.assertEqual(FlowsStatusMapper.map("sent"), BroadcastStatus.SENT)

    def test_maps_failed(self):
        self.assertEqual(FlowsStatusMapper.map("failed"), BroadcastStatus.FAILED)

    def test_uppercase_input_is_normalized(self):
        self.assertEqual(FlowsStatusMapper.map("QUEUED"), BroadcastStatus.QUEUED)

    def test_unknown_value_maps_to_unknown(self):
        self.assertEqual(
            FlowsStatusMapper.map("future-status"), BroadcastStatus.UNKNOWN
        )

    def test_empty_string_returns_none(self):
        self.assertIsNone(FlowsStatusMapper.map(""))

    def test_none_returns_none(self):
        self.assertIsNone(FlowsStatusMapper.map(None))
