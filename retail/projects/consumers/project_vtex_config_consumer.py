import amqp

from retail.projects.usecases.project_dto import ProjectVtexConfigDTO
from retail.projects.usecases.project_vtex_config import ProjectVtexConfigUseCase

from weni.eda.parsers import JSONParser
from weni.eda.django.consumers import EDAConsumer

import logging

logger = logging.getLogger(__name__)


class ProjectVtexConfigConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        logger.info(
            f"[ProjectVtexConfigConsumer] - Consuming a message. Body: {message.body}"
        )
        body = JSONParser.parse(message.body)
        config = body.get("config")
        project_uuid = body.get("project_uuid")

        project_dto = ProjectVtexConfigDTO(
            account=config.get("account"), store_type=config.get("store_type")
        )
        ProjectVtexConfigUseCase.config_vtex_project(project_uuid, project_dto)
        self.ack()
