import logging

from typing import Optional, TypedDict

from retail.services.meta import MetaService
from retail.interfaces.services.meta import MetaServiceInterface
from retail.agents.models import Agent

logger = logging.getLogger(__name__)


class TemplateInfo(TypedDict):
    name: str
    content: str


class ValidatePreApprovedTemplatesUseCase:
    def __init__(self, meta_service: Optional[MetaServiceInterface] = None):
        self.meta_service = meta_service or MetaService()

    def _get_template_info(self, template_name: str) -> Optional[TemplateInfo]:
        logger.info(f"Getting template info from meta: {template_name}")

        data = self.meta_service.get_pre_approved_template(template_name).get("data")

        if not data:
            return None

        return {"name": data[0].get("name"), "content": data[0].get("body")}

    def execute(self, agent: Agent) -> None:
        templates = agent.templates.all()

        for template in templates:
            template_info = self._get_template_info(template.name)

            if template_info is None:
                logger.info(f"Template not valid: {template.name}")
                template.is_valid = False
            else:
                logger.info(f"Template valid: {template.name}")
                template.name = template_info["name"]
                template.content = template_info["content"]
                template.is_valid = True

            template.save()
