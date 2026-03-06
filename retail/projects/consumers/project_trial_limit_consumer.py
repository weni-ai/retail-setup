import logging

import pika

from weni.pika_eda.django.consumers import PikaEDAConsumer

from retail.projects.usecases.suspend_trial_dto import SuspendTrialProjectDTO
from retail.projects.usecases.suspend_trial_project import SuspendTrialProjectUseCase

logger = logging.getLogger(__name__)


class ProjectTrialLimitConsumer(PikaEDAConsumer):
    """
    Consumes messages from Nexus (via Amazon MQ / pika_eda) when a
    project reaches its trial conversation limit.

    Expected message body:
        {
            "project_uuid": "<uuid>",
            "conversation_limit": 1000
        }
    """

    def consume(
        self,
        channel: pika.channel.Channel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
    ):
        data = self.body
        logger.info(f"[ProjectTrialLimitConsumer] - Consuming message: {data}")

        dto = SuspendTrialProjectDTO(
            project_uuid=data.get("project_uuid"),
            conversation_limit=data.get("conversation_limit"),
        )

        use_case = SuspendTrialProjectUseCase()
        use_case.execute(dto)

        logger.info(
            f"[ProjectTrialLimitConsumer] - Successfully processed "
            f"trial limit for project: {dto.project_uuid}"
        )
