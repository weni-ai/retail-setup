import amqp
import logging

from retail.projects.models import Project
from retail.projects.usecases.project_dto import ProjectCreationDTO
from retail.projects.usecases.project_creation import ProjectCreationUseCase
from retail.projects.usecases.link_project_to_onboarding import (
    LinkProjectToOnboardingUseCase,
)

from weni.eda.parsers import JSONParser
from weni.eda.django.consumers import EDAConsumer

logger = logging.getLogger(__name__)


class ProjectConsumer(EDAConsumer):  # pragma: no cover
    def consume(self, message: amqp.Message):
        logger.info(f"[ProjectConsumer] - Consuming a message. Body: {message.body}")
        try:
            body = JSONParser.parse(message.body)

            project_dto = ProjectCreationDTO(
                uuid=body.get("uuid"),
                name=body.get("name"),
                organization_uuid=body.get("organization_uuid"),
                authorizations=body.get("authorizations", []),
                vtex_account=body.get("vtex_account", ""),
            )
            ProjectCreationUseCase.create_project(project_dto)
            logger.info(
                f"[ProjectConsumer] - Successfully processed project: {project_dto.uuid}"
            )

            project = Project.objects.get(uuid=project_dto.uuid)
            LinkProjectToOnboardingUseCase.execute(project)

            self.ack()
        except Exception as e:
            logger.error(f"[ProjectConsumer] - Error processing message: {e}")
            # Don't ack the message so it can be retried or moved to dead letter queue
            self.nack()
