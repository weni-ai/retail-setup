import amqp
import logging

from retail.projects.models import Project

from weni.eda.parsers import JSONParser
from weni.eda.django.consumers import EDAConsumer

logger = logging.getLogger(__name__)


class ProjectUpdateConsumer(EDAConsumer):  # pragma: no cover
    """Consumes project events from update-projects.topic.

    Handles:
      - updated: syncs name, language, and config to the local Project.
      - deleted: removes the local Project (cascades to ProjectOnboarding).
    """

    def consume(self, message: amqp.Message):
        logger.info(
            f"[ProjectUpdateConsumer] - Consuming a message. Body: {message.body}"
        )
        body = JSONParser.parse(message.body)
        action = body.get("action")

        if action == "updated":
            self._handle_update(body)
        elif action == "deleted":
            self._handle_delete(body)
        else:
            logger.info(f"[ProjectUpdateConsumer] - Ignoring action={action}")

        self.ack()

    def _handle_update(self, body: dict) -> None:
        project_uuid = body.get("project_uuid")

        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            logger.warning(
                f"[ProjectUpdateConsumer] - Project {project_uuid} not found, "
                "skipping update."
            )
            return

        updated_fields = []

        name = body.get("name")
        if name:
            project.name = name
            updated_fields.append("name")

        language = body.get("language")
        if language:
            project.language = language
            updated_fields.append("language")

        config = body.get("config")
        if config:
            project.config.update(config)
            updated_fields.append("config")

        if updated_fields:
            project.save(update_fields=updated_fields)
            logger.info(
                f"[ProjectUpdateConsumer] - Updated {updated_fields} "
                f"for project {project_uuid}"
            )

    def _handle_delete(self, body: dict) -> None:
        project_uuid = body.get("project_uuid")

        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            logger.warning(
                f"[ProjectUpdateConsumer] - Project {project_uuid} not found, "
                "skipping deletion."
            )
            return

        project.delete()
        logger.info(f"[ProjectUpdateConsumer] - Deleted project {project_uuid}")
