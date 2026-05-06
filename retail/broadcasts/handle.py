import amqp

from retail.broadcasts.consumers.broadcast_status_consumer import (
    BroadcastStatusConsumer,
)


BROADCAST_CREATE_QUEUE = "retail.msgs-create"
BROADCAST_STATUS_QUEUE = "retail.msgs-status"


def handle_consumers(channel: amqp.Channel):  # pragma: no cover
    """Register all EDA consumers owned by the broadcasts app.

    Two queues bound to the courier's ``msgs.topic`` exchange feed the
    same consumer class — routing inside ``BroadcastStatusConsumer`` is
    payload-driven (presence of ``broadcast_id``), so one handler
    naturally covers both event shapes:

      - ``retail.msgs-create``  ← routing key ``create``
        First event of a new outbound message; carries broadcast_id and
        message_id together so we can link our dispatch row to Meta's id.
      - ``retail.msgs-status``  ← routing key ``status-update``
        Subsequent status transitions (P/Q/S/W/D/V/E/F); carries only
        message_id since broadcast_id is dropped after the create event.

    Pure plumbing for the broker — exercised end-to-end at runtime, not
    in unit tests; see test_broadcast_status_consumer for the behavior
    of the consumer instances bound here.
    """
    channel.basic_consume(
        BROADCAST_CREATE_QUEUE, callback=BroadcastStatusConsumer().handle
    )
    channel.basic_consume(
        BROADCAST_STATUS_QUEUE, callback=BroadcastStatusConsumer().handle
    )
