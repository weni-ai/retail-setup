import amqp

from retail.projects.handle import handle_consumers as project_handle_consumer


def handle_consumers(channel: amqp.Channel):
    project_handle_consumer(channel)
