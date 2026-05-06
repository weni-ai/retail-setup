from django.test import TestCase

from retail.broadcasts.consumers.broadcast_status_consumer import (
    BroadcastStatusConsumer,
)
from retail.broadcasts.models import BroadcastStatus
from retail.broadcasts.usecases.handle_status_update import BroadcastStatusEvent


class BroadcastStatusConsumerRoutingTest(TestCase):
    """Focus on the payload-to-event normalization logic. The full amqp
    integration (ack/nack) is covered by the weni.eda framework and is
    exercised through _handler execution in other tests."""

    def test_to_event_with_create_payload_carries_both_ids(self):
        # Real example from the courier "create" routing key.
        payload = {
            "message_id": "wamid.HBgMNTU4NDk2NzY1MjQ1FQ==",
            "broadcast_id": 7346,
            "status": "Q",
            "direction": "O",
            "channel_type": "WAC",
            "contact_urn": "whatsapp:5511999999999",
            "template_uuid": "9b191149-6bba-4112-a955-3022e99e6486",
        }

        event = BroadcastStatusConsumer._to_event(payload)

        self.assertIsInstance(event, BroadcastStatusEvent)
        self.assertEqual(event.broadcast_id, 7346)
        self.assertEqual(event.message_id, "wamid.HBgMNTU4NDk2NzY1MjQ1FQ==")
        self.assertEqual(event.status, BroadcastStatus.QUEUED)
        self.assertEqual(event.payload, payload)

    def test_to_event_with_status_only_payload(self):
        # Real example from the courier "status-update" routing key.
        payload = {
            "message_id": "wamid.HBgMNTU4NDk2NzY1MjQ1FQ==",
            "status": "D",
            "channel_uuid": "86a16568-432c-4dab-9aa0-91ecf6723870",
            "channel_type": "WAC",
            "broadcast_id": None,
        }

        event = BroadcastStatusConsumer._to_event(payload)

        self.assertIsNone(event.broadcast_id)
        self.assertEqual(event.message_id, "wamid.HBgMNTU4NDk2NzY1MjQ1FQ==")
        self.assertEqual(event.status, BroadcastStatus.DELIVERED)

    def test_to_event_maps_each_courier_status_letter(self):
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
                event = BroadcastStatusConsumer._to_event(
                    {"message_id": "msg-1", "status": letter}
                )
                self.assertEqual(event.status, expected)

    def test_to_event_unknown_status_letter_maps_to_unknown(self):
        event = BroadcastStatusConsumer._to_event(
            {"message_id": "msg-1", "status": "X"}
        )
        self.assertEqual(event.status, BroadcastStatus.UNKNOWN)

    def test_to_event_empty_status_returns_none(self):
        event = BroadcastStatusConsumer._to_event({"message_id": "msg-1"})
        self.assertIsNone(event.status)

    def test_to_event_coerces_string_broadcast_id(self):
        event = BroadcastStatusConsumer._to_event(
            {"message_id": "msg-1", "broadcast_id": "12345", "status": "Q"}
        )
        self.assertEqual(event.broadcast_id, 12345)

    def test_to_event_tolerates_invalid_broadcast_id(self):
        event = BroadcastStatusConsumer._to_event(
            {"message_id": "msg-1", "broadcast_id": "not-a-number", "status": "Q"}
        )
        self.assertIsNone(event.broadcast_id)

    def test_to_event_without_message_id(self):
        event = BroadcastStatusConsumer._to_event({"status": "D"})

        self.assertIsNone(event.message_id)
        self.assertIsNone(event.broadcast_id)
        self.assertEqual(event.status, BroadcastStatus.DELIVERED)

    def test_inbound_messages_are_filtered(self):
        """Inbound payloads (direction='I') must be skipped without
        producing a BroadcastStatusEvent for the use case."""
        self.assertTrue(BroadcastStatusConsumer._is_inbound({"direction": "I"}))
        self.assertFalse(BroadcastStatusConsumer._is_inbound({"direction": "O"}))
        self.assertFalse(BroadcastStatusConsumer._is_inbound({}))
