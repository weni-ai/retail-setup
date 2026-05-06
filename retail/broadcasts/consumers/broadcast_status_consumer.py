import logging

from typing import Any, Dict, Optional

import amqp

from weni.eda.django.consumers import EDAConsumer
from weni.eda.parsers import JSONParser

from retail.broadcasts.services.courier_status_mapper import CourierStatusMapper
from retail.broadcasts.usecases.handle_status_update import (
    BroadcastStatusEvent,
    HandleStatusUpdateUseCase,
)

logger = logging.getLogger(__name__)


class BroadcastStatusConsumer(EDAConsumer):
    """Consumes courier events from the msgs.topic exchange.

    The courier publishes outbound message lifecycle events under two
    routing keys, both bound to our queue:

      - ``create``        → first event of a new outbound message. Carries
                            both ``broadcast_id`` and ``message_id`` (Meta's
                            wamid). Used to link our dispatch row to the
                            external id and persist the initial status.
      - ``status-update`` → subsequent transitions (S/D/V/E/F). The
                            ``broadcast_id`` is dropped at this point, so
                            lookup is done by ``message_id``.

    Inbound messages (direction "I") are silently discarded — the broadcast
    tracking only cares about outbound dispatches.
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

    def consume(self, message: amqp.Message):  # pragma: no cover
        # Integration entry-point invoked by weni.eda inside the broker;
        # exercised end-to-end in stg/prod, not in unit tests. The
        # payload-shaping helpers below are unit-tested directly.
        logger.info(f"[BROADCAST_TRACKING] consume_event: body={message.body}")
        try:
            body = JSONParser.parse(message.body)
        except Exception as exc:
            logger.error(f"[BROADCAST_TRACKING] consume_parse_failed: error={exc}")
            self.ack()
            return

        if self._is_inbound(body):
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
    def _is_inbound(body: Dict[str, Any]) -> bool:
        """Return True for inbound messages (``direction == "I"``).

        The msgs.topic exchange carries every message handled by the
        channel — including replies that contacts send back to the store
        (e.g. "ok", "buy", "stop"). Those events have ``direction="I"``
        and carry no ``broadcast_id``, so they will never match any of
        our dispatch rows. We discard them up front to avoid wasting a
        DB lookup and to keep log volume manageable.

        ``status-update`` events have no ``direction`` field at all
        (empty), so only an explicit ``"I"`` is treated as inbound.
        Outbound (``"O"``) and status-only (empty) events flow through.
        """
        return body.get("direction") == "I"

    @staticmethod
    def _to_event(body: Dict[str, Any]) -> BroadcastStatusEvent:
        """Normalize the incoming courier payload into a BroadcastStatusEvent.

        The status field arrives as a single letter (P/Q/S/W/D/V/E/F);
        ``CourierStatusMapper`` translates it into our internal enum
        before the use case sees it. The original payload is preserved
        in ``payload`` for diagnostics.
        """
        broadcast_id = BroadcastStatusConsumer._coerce_broadcast_id(
            body.get("broadcast_id")
        )
        message_id = body.get("message_id") or None
        mapped_status = CourierStatusMapper.map(body.get("status"))

        return BroadcastStatusEvent(
            message_id=message_id,
            broadcast_id=broadcast_id,
            status=mapped_status,
            payload=body,
        )

    @staticmethod
    def _coerce_broadcast_id(raw: Any) -> Optional[int]:
        if raw in (None, ""):
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            logger.warning(
                f"[BROADCAST_TRACKING] consume_invalid_broadcast_id: raw={raw!r}"
            )
            return None
