import amqp
import logging

from retail.projects.models import Project

from weni.eda.parsers import JSONParser
from weni.eda.django.consumers import EDAConsumer

logger = logging.getLogger(__name__)


class ProjectUpdateConsumer(EDAConsumer):  # pragma: no cover
    """Consumes project update events from update-projects.topic.

    Performs an additive merge on the local Project.config:
    creates new keys, updates existing ones, never deletes
    keys that only exist locally.
    """

    def consume(self, message: amqp.Message):
        logger.info(
            f"[ProjectUpdateConsumer] - Consuming a message. Body: {message.body}"
        )
        body = JSONParser.parse(message.body)
        action = body.get("action")
        project_uuid = body.get("project_uuid")
        config = body.get("config")

        if action != "updated" or config is None:
            self.ack()
            return

        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            logger.warning(
                f"[ProjectUpdateConsumer] - Project {project_uuid} not found, "
                "skipping config update."
            )
            self.ack()
            return

        project.config.update(config)
        project.save(update_fields=["config"])

        logger.info(
            f"[ProjectUpdateConsumer] - Config updated for project {project_uuid}"
        )
        self.ack()
