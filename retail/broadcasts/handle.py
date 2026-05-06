import amqp

from retail.broadcasts.consumers.broadcast_status_consumer import (
    BroadcastStatusConsumer,
)


# Queues bound to the dedicated message-template.topic exchange,
# bindings: template-send (broadcast↔message link) and template-status
# (status transitions).
TEMPLATE_SEND_QUEUE = "retail.template-send"
TEMPLATE_STATUS_QUEUE = "retail.template-status"


def handle_consumers(channel: amqp.Channel):  # pragma: no cover
    """Register all EDA consumers owned by the broadcasts app.

    A single ``BroadcastStatusConsumer`` instance handles both queues —
    routing inside it is payload-driven (presence of ``broadcast_id``).
    """
    channel.basic_consume(
        TEMPLATE_SEND_QUEUE, callback=BroadcastStatusConsumer().handle
    )
    channel.basic_consume(
        TEMPLATE_STATUS_QUEUE, callback=BroadcastStatusConsumer().handle
    )
