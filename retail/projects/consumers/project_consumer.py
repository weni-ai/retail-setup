import amqp

from retail.projects.usecases.project_dto import ProjectCreationDTO
from retail.projects.usecases.project_creation import ProjectCreationUseCase

from weni.eda.parsers import JSONParser
from weni.eda.django.consumers import EDAConsumer


class ProjectConsumer(EDAConsumer):  # pragma: no cover
    def consume(self, message: amqp.Message):
        print(f"[ProjectConsumer] - Consuming a message. Body: {message.body}")
        body = JSONParser.parse(message.body)

        project_dto = ProjectCreationDTO(
            uuid=body.get("uuid"),
            name=body.get("name"),
            organization_uuid=body.get("organization_uuid"),
            authorizations=body.get("authorizations", []),
        )
        ProjectCreationUseCase.create_project(project_dto)
        self.ack()
