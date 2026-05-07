import logging

from typing import Callable, ClassVar

import amqp

from weni.eda.django.consumers import EDAConsumer
from weni.eda.parsers import JSONParser

from retail.broadcasts.services.broadcast_event_parser import BroadcastEventParser
from retail.broadcasts.usecases.handle_status_update import (
    HandleStatusUpdateUseCase,
)

logger = logging.getLogger(__name__)


class BroadcastConsumer(EDAConsumer):
    """Generic broadcast event consumer.

    Subclasses bind a routing key to a method on
    ``HandleStatusUpdateUseCase`` by setting ``handler_method`` to the
    unbound method reference. The shared pipeline below — parse, filter,
    log, ack/nack — covers every consumer with a single implementation.
    """

    # Unbound method reference set by subclasses. Using the method itself
    # (rather than a string name) keeps the binding visible to type
    # checkers and IDEs: a rename on HandleStatusUpdateUseCase will be
    # caught here statically instead of failing at runtime.
    handler_method: ClassVar[Callable] = None  # type: ignore[assignment]

    _handler: HandleStatusUpdateUseCase

    def _ensure_handler(self) -> HandleStatusUpdateUseCase:
        """Lazily instantiate the handler on first use.

        ``EDAConsumer`` controls its own __init__ through the weni.eda
        framework, so the handler lives as a class attribute. Tests can
        inject a custom handler by assigning to ``_handler`` directly.
        """
        handler = getattr(self, "_handler", None)
        if handler is None:
            handler = HandleStatusUpdateUseCase()
            self._handler = handler
        return handler

    def consume(self, message: amqp.Message):  # pragma: no cover
        # Integration entry-point invoked by weni.eda inside the broker;
        # exercised end-to-end in stg/prod, not in unit tests. The
        # parser and the use case methods are unit-tested directly.
        try:
            body = JSONParser.parse(message.body)
        except Exception as exc:
            logger.error(f"[BROADCAST_TRACKING] consume_parse_failed: error={exc}")
            self.ack()
            return

        if not BroadcastEventParser.is_relevant(body):
            self.ack()
            return

        # Only events that survive the relevance filter are worth logging:
        # downstream INFO entries (linked, status_received, status_transition,
        # counters_incremented) carry the business context.
        logger.debug(f"[BROADCAST_TRACKING] consume_event: body={body}")

        try:
            event = BroadcastEventParser.to_event(body)
            # Accessing via ``type(self)`` bypasses Python's descriptor
            # protocol so the unbound method stored in ``handler_method``
            # isn't auto-bound to the consumer instance — we want it
            # bound to the use case instance instead.
            type(self).handler_method(self._ensure_handler(), event)
            self.ack()
        except Exception as exc:
            logger.exception(
                f"[BROADCAST_TRACKING] consume_processing_failed: error={exc}"
            )
            self.nack()


class BroadcastSendConsumer(BroadcastConsumer):
    """Bound to ``retail.template-send`` (routing key ``template-send``).
    Links the courier ``message_id`` to the BroadcastMessage row created
    at dispatch."""

    handler_method = HandleStatusUpdateUseCase.link_send_event


class BroadcastStatusConsumer(BroadcastConsumer):
    """Bound to ``retail.template-status`` (routing key ``template-status``).
    Updates the BroadcastMessage status by ``message_id`` (broadcast_id
    is ignored on purpose at this stage)."""

    handler_method = HandleStatusUpdateUseCase.apply_status_event
