import logging

from typing import Optional

from retail.broadcasts.models import BroadcastStatus

logger = logging.getLogger(__name__)


class CourierStatusMapper:
    """Translates the single-letter status emitted by the courier service
    on the msgs.topic exchange into our internal ``BroadcastStatus`` enum.

    The mapping is 1-to-1 — no upstream state is collapsed — so dashboards
    can reason about the real position of a message in its lifecycle
    (e.g. "still in broker" vs "Meta acknowledged" vs "errored, will retry").

        P (Pending)     → PENDING
        Q (Queued)      → QUEUED
        S (Sent)        → SENT
        W (Wired)       → WIRED
        D (Delivered)   → DELIVERED
        V (Read/Viewed) → READ
        E (Errored)     → ERRORED   # transient, courier will retry
        F (Failed)      → FAILED    # permanent, no retries

    Anything outside the closed domain above is mapped to ``UNKNOWN`` and
    a warning is logged so the courier contract change can be detected
    and the enum extended if needed.
    """

    _MAP = {
        "P": BroadcastStatus.PENDING,
        "Q": BroadcastStatus.QUEUED,
        "S": BroadcastStatus.SENT,
        "W": BroadcastStatus.WIRED,
        "D": BroadcastStatus.DELIVERED,
        "V": BroadcastStatus.READ,
        "E": BroadcastStatus.ERRORED,
        "F": BroadcastStatus.FAILED,
    }

    @classmethod
    def map(cls, raw_status: Optional[str]) -> Optional[BroadcastStatus]:
        """Return the mapped status, or ``None`` when ``raw_status`` is empty.

        Empty/missing status is a valid case (e.g. inbound events) and
        callers must treat it as "no status to apply".
        """
        if not raw_status:
            return None

        mapped = cls._MAP.get(raw_status)
        if mapped is None:
            logger.warning(
                f"[BROADCAST_TRACKING] courier_status_unknown: "
                f"raw_status={raw_status!r} mapped_to={BroadcastStatus.UNKNOWN}"
            )
            return BroadcastStatus.UNKNOWN

        return mapped
