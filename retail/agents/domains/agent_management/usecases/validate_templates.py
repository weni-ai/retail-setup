import logging

from typing import Optional, TypedDict, Dict, Any

from retail.services.meta import MetaService
from retail.interfaces.services.meta import MetaServiceInterface
from retail.templates.adapters.template_library_to_custom_adapter import (
    TemplateTranslationAdapter,
)
from retail.agents.domains.agent_management.models import Agent

logger = logging.getLogger(__name__)


class TemplateInfo(TypedDict):
    name: str
    content: str
    metadata: Dict[str, Any]


class ValidateAgentRulesUseCase:
    """
    Validates agent rules of source_type LIBRARY against Meta's template library.

    For LIBRARY rules, fetches template info from Meta API and populates
    metadata and content. Non-LIBRARY rules are skipped.
    """

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
                "header": self.template_adapter.header_transformer.transform(data_obj),
                "body": data_obj.get("body"),
                "body_params": data_obj.get("body_params"),
                "footer": data_obj.get("footer"),
                "buttons": data_obj.get("buttons"),
                "category": data_obj.get("category"),
                "language": data_obj.get("language"),
            },
        }

    def execute(self, agent: Agent) -> None:
        library_rules = agent.templates.filter(source_type="LIBRARY")

        for rule in library_rules:
            # TODO: Currently uses agent.language (fixed pt_BR) to fetch templates from Meta.
            # To support dynamic language per project, consider:
            # 1. Validate in multiple languages (pt_BR, en, es) and save all in metadata
            # 2. Or re-validate during integration using initial_template_language from project
            # Ref: initial_template_language is saved in IntegratedAgent.config during integration
            template_info = self._get_template_info(rule.name, agent.language)

            if template_info is None:
                logger.warning(
                    f"Template '{rule.name}' not found in Meta library. "
                    f"Rule '{rule.slug}' for agent '{agent.uuid}' "
                    "may need source_type update."
                )
            else:
                logger.info(f"Template valid in Meta library: {rule.name}")
                rule.name = template_info["name"]
                rule.content = template_info["content"]
                rule.metadata = template_info["metadata"]

            rule.save()


# Backward-compatible alias
ValidatePreApprovedTemplatesUseCase = ValidateAgentRulesUseCase
