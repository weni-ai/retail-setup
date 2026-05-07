import amqp

from retail.broadcasts.consumers.broadcast_status_consumer import (
    BroadcastSendConsumer,
    BroadcastStatusConsumer,
)


# Queues bound to the dedicated message-template.topic exchange,
# bindings: template-send (broadcast↔message link) and template-status
# (status transitions).
TEMPLATE_SEND_QUEUE = "retail.template-send"
TEMPLATE_STATUS_QUEUE = "retail.template-status"


def handle_consumers(channel: amqp.Channel):  # pragma: no cover
    """Register all EDA consumers owned by the broadcasts app.

    Each routing key has its own dedicated consumer, so the action taken
    is decided by the broker binding (the source of truth) rather than
    by inspecting the payload shape.
    """
    channel.basic_consume(TEMPLATE_SEND_QUEUE, callback=BroadcastSendConsumer().handle)
    channel.basic_consume(
        TEMPLATE_STATUS_QUEUE, callback=BroadcastStatusConsumer().handle
    )
