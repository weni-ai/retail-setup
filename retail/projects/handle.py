import amqp

from retail.projects.consumers.project_consumer import ProjectConsumer


def handle_consumers(channel: amqp.Channel):
    channel.basic_consume("retail.projects", callback=ProjectConsumer().handle)
