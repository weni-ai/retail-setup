import logging

from typing import Optional

from retail.broadcasts.models import BroadcastStatus

logger = logging.getLogger(__name__)


class FlowsStatusMapper:
    """Translates the broadcast status returned by the Flows API on the
    POST /whatsapp_broadcasts response into our internal ``BroadcastStatus``
    enum.

    The Flows ``WhatsappBroadcastReadSerializer`` collapses its internal
    states (Initializing, Queued, Sent, Failed) into three user-facing
    strings:

        "queued"  → QUEUED   # accepted by Flows, waiting for courier
        "sent"    → SENT     # already handed off to courier/Meta
        "failed"  → FAILED   # rejected at the Flows side

    Anything outside this closed domain is mapped to ``UNKNOWN`` and a
    warning is logged so a Flows contract change can be detected and
    the enum extended if needed.
    """

    _MAP = {
        "queued": BroadcastStatus.QUEUED,
        "sent": BroadcastStatus.SENT,
        "failed": BroadcastStatus.FAILED,
    }

    @classmethod
    def map(cls, raw_status: Optional[str]) -> Optional[BroadcastStatus]:
        """Return the mapped status, or ``None`` when ``raw_status`` is empty.

        Empty/missing status means the dispatch persistence flow must
        decide a fallback (typically QUEUED, since we only call the
        mapper after a successful Flows response).
        """
        if not raw_status:
            return None

        mapped = cls._MAP.get(raw_status.lower())
        if mapped is None:
            logger.warning(
                f"[BROADCAST_TRACKING] flows_status_unknown: "
                f"raw_status={raw_status!r} mapped_to={BroadcastStatus.UNKNOWN}"
            )
            return BroadcastStatus.UNKNOWN

        return mapped
