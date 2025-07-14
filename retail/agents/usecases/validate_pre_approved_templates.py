import logging

from typing import Optional, TypedDict, Dict, Any

from retail.services.meta import MetaService
from retail.interfaces.services.meta import MetaServiceInterface
from retail.templates.adapters.template_library_to_custom_adapter import (
    TemplateTranslationAdapter,
)
from retail.agents.models import Agent

logger = logging.getLogger(__name__)


class TemplateInfo(TypedDict):
    name: str
    content: str
    metadata: Dict[str, Any]


class ValidatePreApprovedTemplatesUseCase:
    def __init__(
        self,
        meta_service: Optional[MetaServiceInterface] = None,
        template_adapter: Optional[TemplateTranslationAdapter] = None,
    ):
        self.meta_service = meta_service or MetaService()
        self.template_adapter = template_adapter or TemplateTranslationAdapter()

    def _get_template_info(
        self, template_name: str, language: str
    ) -> Optional[TemplateInfo]:
        logger.info(f"Getting template info from meta: {template_name}")

        data = self.meta_service.get_pre_approved_template(template_name, language).get(
            "data"
        )

        if not data:
            return None

        data_obj = data[0]

        return {
            "name": data_obj.get("name"),
            "content": data_obj.get("body"),
            "metadata": {
                "header": self.template_adapter.header_transformer.transform(
                    data_obj.get("header")
                ),
                "body": data_obj.get("body"),
                "body_params": data_obj.get("body_params"),
                "footer": data_obj.get("footer"),
                "buttons": data_obj.get("buttons"),
                "category": data_obj.get("category"),
                "language": data_obj.get("language"),
            },
        }

    def execute(self, agent: Agent) -> None:
        templates = agent.templates.all()

        for template in templates:
            template_info = self._get_template_info(template.name, agent.language)

            if template_info is None:
                logger.info(f"Template not valid: {template.name}")
                template.is_valid = False
            else:
                logger.info(f"Template valid: {template.name}")
                template.name = template_info["name"]
                template.content = template_info["content"]
                template.metadata = template_info["metadata"]
                template.is_valid = True

            template.save()
