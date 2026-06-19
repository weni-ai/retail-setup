import logging

from typing import Any, Dict, Optional

from retail.broadcasts.services.courier_status_mapper import CourierStatusMapper
from retail.broadcasts.usecases.handle_status_update import BroadcastStatusEvent

logger = logging.getLogger(__name__)


# Channel types we own on the courier side. Any event published with a
# different channel_type belongs to other modules (chat widget, external
# providers, etc.) and is discarded silently.
RELEVANT_CHANNEL_TYPES = frozenset({"WAC"})


class BroadcastEventParser:
    """Stateless helper that turns a raw courier payload into a
    ``BroadcastStatusEvent`` plus a relevance check.

    Shared by both consumers (template-send and template-status) since
    the parsing rules are identical — only the downstream action differs.
    """

    @staticmethod
    def is_relevant(body: Dict[str, Any]) -> bool:
        """Return True only when the event has a chance of matching one
        of our broadcasts. Used to discard cheaply (no log, no DB hit)
        the bulk of upstream traffic that belongs to other modules.

        An event is considered relevant when ALL hold:
          - direction is not "I" (inbound replies are not broadcasts);
          - channel_type is in RELEVANT_CHANNEL_TYPES (we only own WAC);
          - message_id is present (without it we cannot link/lookup).
        """
        if BroadcastEventParser._is_inbound(body):
            return False

        channel_type = body.get("channel_type")
        if channel_type and channel_type not in RELEVANT_CHANNEL_TYPES:
            return False

        if not body.get("message_id"):
            return False

        return True

    @staticmethod
    def to_event(body: Dict[str, Any]) -> BroadcastStatusEvent:
        """Normalize the incoming courier payload into a BroadcastStatusEvent.

        The status field arrives as a single letter (P/Q/S/W/D/V/E/F);
        ``CourierStatusMapper`` translates it into our internal enum
        before the use case sees it. The original payload is preserved
        in ``payload`` for diagnostics.
        """
        return BroadcastStatusEvent(
            message_id=body.get("message_id") or None,
            broadcast_id=BroadcastEventParser._coerce_broadcast_id(
                body.get("broadcast_id")
            ),
            status=CourierStatusMapper.map(body.get("status")),
            payload=body,
        )

    @staticmethod
    def _is_inbound(body: Dict[str, Any]) -> bool:
        """Return True for inbound messages (``direction == "I"``).

        Status-update events have no ``direction`` field at all (empty),
        so only an explicit ``"I"`` is treated as inbound. Outbound
        (``"O"``) and status-only (empty) events flow through.
        """
        return body.get("direction") == "I"

    @staticmethod
    def _coerce_broadcast_id(raw: Any) -> Optional[int]:
        """Normalize the broadcast_id field to an int or None.

        The courier emits ``broadcast_id=0`` (or omits the field) on
        status-update events because the original broadcast id is no
        longer carried after the first send/create event. Treating 0
        as a real id would route status events incorrectly, so 0 is
        normalized to None — same as a missing field.
        """
        if raw in (None, ""):
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            logger.warning(
                f"[BROADCAST_TRACKING] consume_invalid_broadcast_id: raw={raw!r}"
            )
            return None
        return value if value > 0 else None
