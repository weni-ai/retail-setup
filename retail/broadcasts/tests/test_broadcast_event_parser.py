from django.test import TestCase

from retail.broadcasts.models import BroadcastStatus
from retail.broadcasts.services.broadcast_event_parser import BroadcastEventParser
from retail.broadcasts.usecases.handle_status_update import BroadcastStatusEvent


class BroadcastEventParserToEventTest(TestCase):
    """Validates the courier-payload → BroadcastStatusEvent normalization."""

    def test_to_event_with_send_payload_carries_both_ids(self):
        # Real example from the courier "template-send" routing key.
        payload = {
            "message_id": "wamid.HBgMNTU4NDk2NzY1MjQ1FQ==",
            "broadcast_id": 7346,
            "status": "Q",
            "direction": "O",
            "channel_type": "WAC",
            "contact_urn": "whatsapp:5511999999999",
            "template_uuid": "9b191149-6bba-4112-a955-3022e99e6486",
        }

        event = BroadcastEventParser.to_event(payload)

        self.assertIsInstance(event, BroadcastStatusEvent)
        self.assertEqual(event.broadcast_id, 7346)
        self.assertEqual(event.message_id, "wamid.HBgMNTU4NDk2NzY1MjQ1FQ==")
        self.assertEqual(event.status, BroadcastStatus.QUEUED)
        self.assertEqual(event.payload, payload)

    def test_to_event_with_status_payload(self):
        # Real example from the courier "template-status" routing key.
        payload = {
            "message_id": "wamid.HBgMNTU4NDk2NzY1MjQ1FQ==",
            "status": "D",
            "channel_uuid": "86a16568-432c-4dab-9aa0-91ecf6723870",
            "channel_type": "WAC",
            "broadcast_id": None,
        }

        event = BroadcastEventParser.to_event(payload)

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
                event = BroadcastEventParser.to_event(
                    {"message_id": "msg-1", "status": letter}
                )
                self.assertEqual(event.status, expected)

    def test_to_event_unknown_status_letter_maps_to_unknown(self):
        event = BroadcastEventParser.to_event({"message_id": "msg-1", "status": "X"})
        self.assertEqual(event.status, BroadcastStatus.UNKNOWN)

    def test_to_event_empty_status_returns_none(self):
        event = BroadcastEventParser.to_event({"message_id": "msg-1"})
        self.assertIsNone(event.status)

    def test_to_event_coerces_string_broadcast_id(self):
        event = BroadcastEventParser.to_event(
            {"message_id": "msg-1", "broadcast_id": "12345", "status": "Q"}
        )
        self.assertEqual(event.broadcast_id, 12345)

    def test_to_event_tolerates_invalid_broadcast_id(self):
        event = BroadcastEventParser.to_event(
            {"message_id": "msg-1", "broadcast_id": "not-a-number", "status": "Q"}
        )
        self.assertIsNone(event.broadcast_id)

    def test_to_event_treats_broadcast_id_zero_as_absent(self):
        """The courier emits broadcast_id=0 on status-update events so
        the parser must normalize 0 to None — otherwise the consumer
        would route status events incorrectly."""
        event = BroadcastEventParser.to_event(
            {"message_id": "msg-1", "broadcast_id": 0, "status": "S"}
        )
        self.assertIsNone(event.broadcast_id)

    def test_to_event_treats_negative_broadcast_id_as_absent(self):
        event = BroadcastEventParser.to_event(
            {"message_id": "msg-1", "broadcast_id": -1, "status": "S"}
        )
        self.assertIsNone(event.broadcast_id)

    def test_to_event_without_message_id(self):
        event = BroadcastEventParser.to_event({"status": "D"})

        self.assertIsNone(event.message_id)
        self.assertIsNone(event.broadcast_id)
        self.assertEqual(event.status, BroadcastStatus.DELIVERED)


class BroadcastEventParserRelevanceTest(TestCase):
    """Validates the cheap relevance filter that discards events that
    cannot possibly belong to one of our broadcasts."""

    def test_inbound_messages_are_filtered(self):
        self.assertTrue(BroadcastEventParser._is_inbound({"direction": "I"}))
        self.assertFalse(BroadcastEventParser._is_inbound({"direction": "O"}))
        self.assertFalse(BroadcastEventParser._is_inbound({}))

    def test_accepts_outbound_wac_with_message_id(self):
        self.assertTrue(
            BroadcastEventParser.is_relevant(
                {
                    "direction": "O",
                    "channel_type": "WAC",
                    "message_id": "wamid.HBgM",
                }
            )
        )

    def test_accepts_status_only_event_without_direction(self):
        self.assertTrue(
            BroadcastEventParser.is_relevant(
                {
                    "channel_type": "WAC",
                    "message_id": "wamid.HBgM",
                    "status": "D",
                }
            )
        )

    def test_rejects_inbound(self):
        self.assertFalse(
            BroadcastEventParser.is_relevant(
                {
                    "direction": "I",
                    "channel_type": "WAC",
                    "message_id": "wamid.HBgM",
                }
            )
        )

    def test_rejects_non_wac_channel(self):
        self.assertFalse(
            BroadcastEventParser.is_relevant(
                {
                    "direction": "O",
                    "channel_type": "WWC",
                    "message_id": "wamid.HBgM",
                }
            )
        )

    def test_rejects_payload_without_message_id(self):
        self.assertFalse(BroadcastEventParser.is_relevant({"channel_type": "WAC"}))

    def test_accepts_payload_with_channel_type_field_missing(self):
        # Some broker events may omit channel_type entirely; we only
        # reject when the field is present and outside the whitelist.
        self.assertTrue(
            BroadcastEventParser.is_relevant(
                {"direction": "O", "message_id": "wamid.HBgM"}
            )
        )
