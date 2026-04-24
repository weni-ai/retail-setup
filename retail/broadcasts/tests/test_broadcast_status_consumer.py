from django.test import TestCase

from retail.broadcasts.consumers.broadcast_status_consumer import (
    BroadcastStatusConsumer,
)
from retail.broadcasts.usecases.handle_status_update import BroadcastStatusEvent


class BroadcastStatusConsumerRoutingTest(TestCase):
    """Focus on the payload-to-event normalization logic. The full amqp
    integration (ack/nack) is covered by the weni.eda framework and is
    exercised through _handler execution in other tests."""

    def test_to_event_with_create_payload_carries_both_ids(self):
        payload = {
            "message_id": "msg-20260422-001",
            "broadcast_id": 42058,
            "status": "sent",
            "contact_urn": "whatsapp:5511999999999",
        }

        event = BroadcastStatusConsumer._to_event(payload)

        self.assertIsInstance(event, BroadcastStatusEvent)
        self.assertEqual(event.broadcast_id, 42058)
        self.assertEqual(event.message_id, "msg-20260422-001")
        self.assertEqual(event.status, "sent")
        self.assertEqual(event.payload, payload)

    def test_to_event_with_status_only_payload(self):
        payload = {
            "message_id": "msg-20260422-001",
            "status": "delivered",
            "broadcast_id": None,
        }

        event = BroadcastStatusConsumer._to_event(payload)

        self.assertIsNone(event.broadcast_id)
        self.assertEqual(event.message_id, "msg-20260422-001")
        self.assertEqual(event.status, "delivered")

    def test_to_event_coerces_string_broadcast_id(self):
        payload = {
            "message_id": "msg-1",
            "broadcast_id": "12345",
            "status": "sent",
        }

        event = BroadcastStatusConsumer._to_event(payload)

        self.assertEqual(event.broadcast_id, 12345)

    def test_to_event_tolerates_invalid_broadcast_id(self):
        payload = {
            "message_id": "msg-1",
            "broadcast_id": "not-a-number",
            "status": "sent",
        }

        event = BroadcastStatusConsumer._to_event(payload)

        self.assertIsNone(event.broadcast_id)

    def test_to_event_without_message_id(self):
        payload = {"status": "delivered"}

        event = BroadcastStatusConsumer._to_event(payload)

        self.assertIsNone(event.message_id)
        self.assertIsNone(event.broadcast_id)
        self.assertEqual(event.status, "delivered")
