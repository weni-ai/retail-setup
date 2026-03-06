import pika

from retail.projects.consumers.project_trial_limit_consumer import (
    ProjectTrialLimitConsumer,
)

TRIAL_LIMIT_QUEUE = "retail-setup.projects.trial-limit"


def handle_consumers(channel: pika.channel.Channel):
    channel.basic_consume(
        TRIAL_LIMIT_QUEUE,
        on_message_callback=ProjectTrialLimitConsumer().handle,
    )
