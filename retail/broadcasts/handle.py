import amqp

from retail.broadcasts.consumers.broadcast_status_consumer import (
    BroadcastStatusConsumer,
)


# Queue bound to the shared msgs.topic exchange.
BROADCAST_STATUS_QUEUE = "retail.msgs-status"


def handle_consumers(channel: amqp.Channel):
    """Register all EDA consumers owned by the broadcasts app."""
    channel.basic_consume(
        BROADCAST_STATUS_QUEUE, callback=BroadcastStatusConsumer().handle
    )
