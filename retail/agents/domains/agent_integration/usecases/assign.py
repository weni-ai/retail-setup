import logging

from typing import List, TypedDict, Mapping, Any, Optional

from uuid import UUID

from django.db import transaction
from django.conf import settings

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.domains.agent_integration.models import IntegratedAgent, Credential
from retail.agents.domains.agent_management.models import Agent, PreApprovedTemplate
from retail.services.integrations.service import IntegrationsService
from retail.interfaces.services.integrations import IntegrationsServiceInterface
from retail.projects.models import Project
from retail.templates.usecases.create_library_template import (
    LibraryTemplateData,
    CreateLibraryTemplateUseCase,
)
from retail.templates.usecases._base_template_creator import TemplateBuilderMixin
from retail.templates.usecases.create_custom_template import (
    CreateCustomTemplateUseCase,
    CreateCustomTemplateData,
)
from retail.templates.exceptions import CustomTemplateAlreadyExists

logger = logging.getLogger(__name__)


class MetaButtonFormat(TypedDict):
    url: str
    text: str
    type: str


class IntegrationsButtonUrlFormat(TypedDict):
    base_url: str
    url_suffix_example: str


class IntegrationsButtonFormat(TypedDict):
    type: str
    url: IntegrationsButtonUrlFormat


class AssignAgentUseCase:
    def __init__(
        self,
        integrations_service: Optional[IntegrationsServiceInterface] = None,
    ):
        self.integrations_service = integrations_service or IntegrationsService()

    def _get_project(self, project_uuid: UUID):
        try:
            return Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            raise NotFound(f"Project not found: {project_uuid}")

    def _create_integrated_agent(
        self,
        agent: Agent,
        project: Project,
        channel_uuid: UUID,
        ignore_templates: List[str],
    ) -> IntegratedAgent:
        ignore_templates_slugs = self._get_ignore_templates_slugs(ignore_templates)

        # Build initial config based on agent type
        initial_config = self._build_initial_config(agent)

        integrated_agent, created = IntegratedAgent.objects.get_or_create(
            agent=agent,
            project=project,
            is_active=True,
            defaults={
                "channel_uuid": channel_uuid,
                "ignore_templates": ignore_templates_slugs,
                "config": initial_config,
            },
        )

        if not created:
            raise ValidationError(
                detail={"agent": "This agent is already assigned in this project."}
            )

        return integrated_agent

    def _build_initial_config(self, agent: Agent) -> dict:
        """
        Build initial configuration for the IntegratedAgent based on agent type.

        This method creates a scalable configuration structure that can be extended
        for different agent types. Currently supports abandoned cart agent with
        specific default settings.

        Returns:
            dict: Initial configuration dictionary.
        """
        config = {}

        # Check if this is the abandoned cart agent
        abandoned_cart_agent_uuid = getattr(settings, "ABANDONED_CART_AGENT_UUID", "")
        if abandoned_cart_agent_uuid and str(agent.uuid) == abandoned_cart_agent_uuid:
            config["abandoned_cart"] = self._get_abandoned_cart_default_config()

        return config

    def _get_abandoned_cart_default_config(self) -> dict:
        """
        Get default configuration for the abandoned cart agent.

        Configuration options:
        - header_image_type: Type of image to show in template header
            - "first_item": First item in the cart (DEFAULT)
            - "most_expensive": Most expensive item in the cart
            - "no_image": No image header (user chose not to use image)
        - abandonment_time_minutes: Time in minutes to consider cart abandoned (default: 60)
        - minimum_cart_value: Minimum cart value in BRL to trigger notification (default: 50.0)

        Optional (not set by default, can be configured later):
        - notification_cooldown_hours: Hours between notifications for same phone

        Returns:
            dict: Default abandoned cart configuration.
        """
        return {
            "header_image_type": "first_item",
            "abandonment_time_minutes": 60,
            "minimum_cart_value": 50.0,
        }

    def _validate_credentials(self, agent: Agent, credentials: dict):
        for key in agent.credentials.keys():
            credential = credentials.get(key, None)

            if credential is None:
                raise ValidationError(f"Credential {key} is required")

    def _create_credentials(
        self, integrated_agent: IntegratedAgent, agent: Agent, credentials: dict
    ) -> None:
        for key, value in credentials.items():
            agent_credential = agent.credentials.get(key, None)

            if agent_credential is None:
                continue

            Credential.objects.get_or_create(
                key=key,
                integrated_agent=integrated_agent,
                defaults={
                    "value": value,
                    "label": agent_credential.get("label"),
                    "placeholder": agent_credential.get("placeholder"),
                    "is_confidential": agent_credential.get("is_confidential"),
                },
            )

    def _create_valid_templates(
        self,
        integrated_agent: IntegratedAgent,
        valid_pre_approveds: List[PreApprovedTemplate],
        project_uuid: UUID,
        app_uuid: UUID,
    ) -> None:
        create_library_use_case = CreateLibraryTemplateUseCase()
        for pre_approved in valid_pre_approveds:
            metadata = pre_approved.metadata or {}
            data: LibraryTemplateData = {
                "template_name": pre_approved.name,
                "library_template_name": pre_approved.name,
                "category": metadata.get("category"),
                "language": metadata.get("language"),
                "app_uuid": app_uuid,
                "project_uuid": project_uuid,
                "start_condition": pre_approved.start_condition,
            }

            template, version = create_library_use_case.execute(data)

            if not metadata.get("buttons"):
                create_library_use_case.notify_integrations(
                    version.template_name, version.uuid, data
                )
            else:
                template.needs_button_edit = True

            template.metadata = pre_approved.metadata
            template.config = pre_approved.config or {}
            template.parent = pre_approved
            template.integrated_agent = integrated_agent
            template.save()

            integrated_agent.ignore_templates.append(template.parent.slug)
            integrated_agent.save(update_fields=["ignore_templates"])

    def _create_invalid_templates(
        self,
        integrated_agent: IntegratedAgent,
        invalid_pre_approveds: List[PreApprovedTemplate],
        project_uuid: UUID,
        app_uuid: UUID,
    ) -> None:
        logger.info(
            "Fetching user templates in integrations service (non-pre-approved)..."
        )

        template_builder = TemplateBuilderMixin()
        language = integrated_agent.agent.language

        translations_by_name = self.integrations_service.fetch_templates_from_user(
            app_uuid,
            str(project_uuid),
            [pre_approved.name for pre_approved in invalid_pre_approveds],
            language,
        )

        logger.info(
            f"Found {len(translations_by_name)} templates in integrations service (non-pre-approved)"
        )

        for pre_approved in invalid_pre_approveds:
            translation = translations_by_name.get(pre_approved.name)
            if translation is not None:
                template, version = template_builder.build_template_and_version(
                    payload={
                        "template_name": pre_approved.name,
                        "app_uuid": app_uuid,
                        "project_uuid": project_uuid,
                    },
                    integrated_agent=integrated_agent,
                )
                template.metadata = translation
                template.config = pre_approved.config or {}
                template.parent = pre_approved
                template.start_condition = pre_approved.start_condition
                template.display_name = pre_approved.display_name
                template.current_version = version
                template.integrated_agent = integrated_agent
                template.save()

                version.template_name = pre_approved.name
                version.status = "APPROVED"
                version.save()

    def _create_templates(
        self,
        integrated_agent: IntegratedAgent,
        pre_approveds: List[PreApprovedTemplate],
        project_uuid: UUID,
        app_uuid: UUID,
        ignore_templates: List[str],
    ) -> None:
        """
        Create templates for the integrated agent based on PreApprovedTemplate.

        Responsibilities:
        - Valid pre-approved: create library templates and notify integrations
          (or flag for button edit when buttons are present).
        - Invalid pre-approved: fetch user's approved translations and adapt them,
          creating an approved version directly.
        """
        pre_approveds = pre_approveds.exclude(uuid__in=ignore_templates)
        valid_pre_approveds = pre_approveds.filter(is_valid=True)
        invalid_pre_approveds = pre_approveds.filter(is_valid=False)

        self._create_valid_templates(
            integrated_agent,
            valid_pre_approveds,
            project_uuid,
            app_uuid,
        )
        self._create_invalid_templates(
            integrated_agent,
            invalid_pre_approveds,
            project_uuid,
            app_uuid,
        )

    def _get_ignore_templates(
        self, agent: Agent, include_templates: List[str]
    ) -> List[str]:
        ignore_templates = (
            PreApprovedTemplate.objects.filter(agent=agent)
            .exclude(uuid__in=include_templates)
            .values_list("uuid", flat=True)
        )

        return list(ignore_templates)

    def _get_ignore_templates_slugs(
        self,
        ignore_templates: List[str],
    ) -> List[str]:
        slugs = PreApprovedTemplate.objects.filter(
            uuid__in=ignore_templates
        ).values_list("slug", flat=True)
        return list(slugs)

    @transaction.atomic
    def execute(
        self,
        agent: Agent,
        project_uuid: UUID,
        app_uuid: UUID,
        channel_uuid: UUID,
        credentials: Mapping[str, Any],
        include_templates: List[str],
    ) -> IntegratedAgent:
        """
        Assign the agent to the project and materialize its templates.

        Flow:
        1) Create IntegratedAgent and credentials
        2) Create templates from the agent's PreApprovedTemplate definitions
        3) If the agent is the Abandoned Cart agent (ABANDONED_CART_AGENT_UUID),
           create a default custom template using the custom template flow
           (lifecycle PENDING -> APPROVED, versioning, etc.).
        """
        project = self._get_project(project_uuid)
        self._validate_credentials(agent, credentials)

        templates = agent.templates.all()

        ignore_templates = self._get_ignore_templates(agent, include_templates)

        integrated_agent = self._create_integrated_agent(
            agent=agent,
            project=project,
            channel_uuid=channel_uuid,
            ignore_templates=ignore_templates,
        )

        self._create_credentials(integrated_agent, agent, credentials)
        self._create_templates(
            integrated_agent, templates, project_uuid, app_uuid, ignore_templates
        )

        # If this is the abandoned cart agent, create a default custom template
        abandoned_cart_agent_uuid = getattr(settings, "ABANDONED_CART_AGENT_UUID", "")
        if abandoned_cart_agent_uuid and str(agent.uuid) == abandoned_cart_agent_uuid:
            self._create_default_abandoned_cart_template(
                integrated_agent=integrated_agent,
                project=project,
                project_uuid=project_uuid,
                app_uuid=app_uuid,
            )

        return integrated_agent

    def _create_default_abandoned_cart_template(
        self,
        integrated_agent: IntegratedAgent,
        project: Project,
        project_uuid: UUID,
        app_uuid: UUID,
    ) -> None:
        """
        Create a default custom template for the abandoned cart agent.
        Uses the existing custom template flow so the template follows the normal
        lifecycle (PENDING -> APPROVED, versioning, etc.).

        The template is created with:
        - Header image support (product image from cart)
        - Body with client name variable
        - Button with cart checkout URL
        - Quick reply for opt-out

        For now, the template is created only in pt-BR.
        TODO: Add support for multiple languages (e.g., en, es) if needed.
        """
        try:
            # Build store domain similar to legacy abandoned cart template creation
            domain = f"{project.vtex_account}.vtexcommercestable.com.br"
            button_base_url = f"https://{domain}/checkout?orderFormId="
            button_url_example = f"{button_base_url}92421d4a70224658acaab0c172f6b6d7"

            # Placeholder image URL for template approval (configurable via env)
            # This is a sample product image URL that Meta will use for template preview
            # The actual product image will be sent dynamically by the agent via image_url
            placeholder_image_url = settings.ABANDONED_CART_DEFAULT_IMAGE_URL

            # Build translation payload in the format expected by TemplateMetadataHandler
            # NOTE: Use "template_header" (not "header") because build_metadata expects this key
            template_translation = {
                # Header image - will be replaced dynamically by agent with product image
                # Format must be {"header_type": "IMAGE", "text": url} for HeaderTransformer
                "template_header": {
                    "header_type": "IMAGE",
                    "text": placeholder_image_url,
                },
                "template_body": (
                    "Olá, {{1}} vimos que você deixou itens no seu carrinho 🛒. "
                    "\nVamos fechar o pedido e garantir essas ofertas? "
                    "\n\nClique em Finalizar Pedido para concluir sua compra 👇"
                ),
                # Example values for body variables used for preview
                "template_body_params": ["João"],
                "template_footer": "Finalizar Pedido",
                "template_button": [
                    {
                        "type": "URL",
                        "text": "Finalizar Pedido",
                        "url": {
                            "base_url": button_base_url,
                            "url_suffix_example": button_url_example,
                        },
                    },
                    {
                        "type": "QUICK_REPLY",
                        "text": "Parar Promoções",
                    },
                ],
                "category": "MARKETING",
                "language": integrated_agent.agent.language or "pt_BR",
            }

            payload: CreateCustomTemplateData = {
                "template_translation": template_translation,
                "category": "MARKETING",
                "app_uuid": str(app_uuid),
                "project_uuid": str(project_uuid),
                "display_name": "Abandoned Cart",
                # NOTE: start_condition is derived from parameters by TemplateMetadataHandler
                "start_condition": "If cart_link is not empty",
                "parameters": [
                    {
                        "name": "start_condition",
                        "value": "If cart_link is not empty",
                    },
                    {
                        "name": "variables",
                        "value": [
                            {
                                "name": "1",
                                "type": "text",
                                "definition": "Client name for abandoned cart recovery",
                                "fallback": "Cliente",
                            },
                            {
                                "name": "button",
                                "type": "text",
                                "definition": "Cart link (order_form_id) for checkout button",
                                "fallback": "",
                            },
                            {
                                "name": "image_url",
                                "type": "text",
                                "definition": "Product image URL from cart (first_item, most_expensive, or no_image)",
                                "fallback": "",
                            },
                        ],
                    },
                ],
                "integrated_agent_uuid": integrated_agent.uuid,
                "use_agent_rule": True,
            }

            logger.info(
                "Creating default custom abandoned cart template for integrated agent %s",
                integrated_agent.uuid,
            )
            use_case = CreateCustomTemplateUseCase()
            use_case.execute(payload)
        except CustomTemplateAlreadyExists:
            logger.info(
                "Custom abandoned cart template already exists for integrated agent %s",
                integrated_agent.uuid,
            )
        except Exception as exc:
            logger.exception(
                "Error while creating default custom abandoned cart template for "
                "integrated agent %s: %s",
                integrated_agent.uuid,
                exc,
            )
