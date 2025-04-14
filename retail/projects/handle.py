import amqp

from retail.projects.consumers.project_consumer import ProjectConsumer
from retail.projects.consumers.project_vtex_config_consumer import (
    ProjectVtexConfigConsumer,
)


def handle_consumers(channel: amqp.Channel):
    channel.basic_consume("retail.projects", callback=ProjectConsumer().handle)
    channel.basic_consume(
        "create_vtex_app.topic", callback=ProjectVtexConfigConsumer().handle
    )
