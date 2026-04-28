import logging

from typing import Any, Dict, Optional

import amqp

from weni.eda.django.consumers import EDAConsumer
from weni.eda.parsers import JSONParser

from retail.broadcasts.usecases.handle_status_update import (
    BroadcastStatusEvent,
    HandleStatusUpdateUseCase,
)

logger = logging.getLogger(__name__)


class BroadcastStatusConsumer(EDAConsumer):  # pragma: no cover
    """Consumes courier events from the msgs.topic exchange.

    Two event shapes are expected:
      - Create event: contains both broadcast_id and message_id. Used to
        link the external message id (from Meta) to the BroadcastMessage
        previously created at dispatch.
      - Status event: contains only message_id. Used to update the status
        of a BroadcastMessage already linked.
    """

    _handler: HandleStatusUpdateUseCase

    def _ensure_handler(self) -> HandleStatusUpdateUseCase:
        """Lazily instantiate the status handler on first use.

        EDAConsumer has its own __init__ contract with the weni.eda
        framework, so the handler is kept as a class attribute to avoid
        shadowing it. Subclassing for tests can still inject a custom
        handler by assigning to `_handler` directly.
        """
        handler = getattr(self, "_handler", None)
        if handler is None:
            handler = HandleStatusUpdateUseCase()
            self._handler = handler
        return handler

    def consume(self, message: amqp.Message):
        logger.info(f"[BROADCAST_TRACKING] consume_event: body={message.body}")
        try:
            body = JSONParser.parse(message.body)
        except Exception as exc:
            logger.error(f"[BROADCAST_TRACKING] consume_parse_failed: error={exc}")
            self.ack()
            return

        try:
            event = self._to_event(body)
            self._ensure_handler().execute(event)
            self.ack()
        except Exception as exc:
            logger.exception(
                f"[BROADCAST_TRACKING] consume_processing_failed: error={exc}"
            )
            self.nack()

    @staticmethod
    def _to_event(body: Dict[str, Any]) -> BroadcastStatusEvent:
        """Normalize the incoming courier payload into a BroadcastStatusEvent.

        Broadcast ids arrive as integers in the courier payload; coerce
        defensively to keep the consumer resilient to minor shape changes.
        """
        raw_broadcast_id = body.get("broadcast_id")
        broadcast_id: Optional[int] = None
        if raw_broadcast_id not in (None, ""):
            try:
                broadcast_id = int(raw_broadcast_id)
            except (TypeError, ValueError):
                logger.warning(
                    f"[BROADCAST_TRACKING] consume_invalid_broadcast_id: "
                    f"raw={raw_broadcast_id!r}"
                )

        message_id = body.get("message_id") or None
        status = body.get("status") or None

        return BroadcastStatusEvent(
            message_id=message_id,
            broadcast_id=broadcast_id,
            status=status,
            payload=body,
        )
