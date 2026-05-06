from unittest.mock import MagicMock

from django.test import TestCase

from retail.broadcasts.consumers.broadcast_status_consumer import (
    BroadcastSendConsumer,
    BroadcastStatusConsumer,
)
from retail.broadcasts.usecases.handle_status_update import HandleStatusUpdateUseCase


class BroadcastSendConsumerTest(TestCase):
    """The send consumer must always invoke ``link_send_event`` —
    routing key is the source of truth for the action, not the payload."""

    def test_handler_method_points_to_link_send_event(self):
        # Class-level binding is the contract: any rename on the use case
        # must be reflected here, and the IDE/type-checker will catch it
        # because the reference is to the method itself, not a string.
        self.assertIs(
            BroadcastSendConsumer.handler_method,
            HandleStatusUpdateUseCase.link_send_event,
        )


class BroadcastStatusConsumerTest(TestCase):
    """The status consumer must always invoke ``apply_status_event``."""

    def test_handler_method_points_to_apply_status_event(self):
        self.assertIs(
            BroadcastStatusConsumer.handler_method,
            HandleStatusUpdateUseCase.apply_status_event,
        )


class BroadcastConsumerLazyHandlerTest(TestCase):
    """Both consumers share the same lazy-handler infrastructure inherited
    from the base class. Validating the contract on one instance is enough."""

    def test_ensure_handler_lazily_instantiates_default(self):
        consumer = BroadcastSendConsumer.__new__(BroadcastSendConsumer)

        first = consumer._ensure_handler()
        second = consumer._ensure_handler()

        self.assertIs(first, second)

    def test_ensure_handler_keeps_injected_instance(self):
        injected = MagicMock()
        consumer = BroadcastStatusConsumer.__new__(BroadcastStatusConsumer)
        consumer._handler = injected

        self.assertIs(consumer._ensure_handler(), injected)
