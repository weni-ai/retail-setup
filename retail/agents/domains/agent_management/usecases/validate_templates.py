import logging

from typing import Optional

from retail.services.meta import MetaService
from retail.interfaces.services.meta import MetaServiceInterface
from retail.agents.domains.agent_management.models import Agent
from retail.templates.usecases._meta_library_template_fetch import (
    TemplateInfo,
    adapt_meta_library_template_response,
)

logger = logging.getLogger(__name__)


class ValidatePreApprovedTemplatesUseCase:
    def __init__(
        self,
        meta_service: Optional[MetaServiceInterface] = None,
    ):
        self._meta_service = meta_service

    @property
    def meta_service(self) -> MetaServiceInterface:
        """Lazily construct ``MetaService`` only when the validation actually
        fires."""
        if self._meta_service is None:
            self._meta_service = MetaService()
        return self._meta_service

    def _get_template_info(
        self, template_name: str, language: str
    ) -> Optional[TemplateInfo]:
        logger.info(f"Getting template info from meta: {template_name}")

        data = self.meta_service.get_pre_approved_template(template_name, language).get(
            "data"
        )

        if not data:
            return None

        return adapt_meta_library_template_response(data[0], language)

    def execute(self, agent: Agent) -> None:
        templates = agent.templates.all()

        for template in templates:
            # TODO: Currently uses agent.language (fixed pt_BR) to fetch templates from Meta.
            # To support dynamic language per project, consider:
            # 1. Validate in multiple languages (pt_BR, en, es) and save all in metadata
            # 2. Or re-validate during integration using initial_template_language from project
            # Ref: initial_template_language is saved in IntegratedAgent.config during integration
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
