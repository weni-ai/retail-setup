import logging

from typing import List, TypedDict, Mapping, Any, Optional

from uuid import UUID

from django.db import transaction
from django.conf import settings

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.domains.agent_integration.models import IntegratedAgent, Credential
from retail.agents.domains.agent_integration.usecases.fetch_country_phone_code import (
    FetchCountryPhoneCodeUseCase,
)
from retail.agents.domains.agent_management.models import Agent, AgentRule
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
from retail.services.aws_s3.converters import ImageUrlToBase64Converter
from retail.agents.shared.country_code_utils import DEFAULT_TEMPLATE_LANGUAGE
from retail.agents.domains.agent_integration.usecases.build_abandoned_cart_translation import (
    BuildAbandonedCartTranslationUseCase,
)

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
        fetch_country_phone_code_usecase: Optional[FetchCountryPhoneCodeUseCase] = None,
    ):
        self.integrations_service = integrations_service or IntegrationsService()
        self.fetch_country_phone_code_usecase = (
            fetch_country_phone_code_usecase or FetchCountryPhoneCodeUseCase()
        )

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

        # Build initial config based on agent type and project
        initial_config = self._build_initial_config(agent, project)

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

    def _build_initial_config(self, agent: Agent, project: Project) -> dict:
        """
        Build initial configuration for the IntegratedAgent based on agent type.

        This method creates a scalable configuration structure that can be extended
        for different agent types. Currently supports abandoned cart agent with
        specific default settings.

        Fetches locale info from VTEX tenant to automatically set:
        - country_phone_code: Phone code (e.g., '55' for Brazil)
        - initial_template_language: Meta language code (e.g., 'pt_BR', 'en', 'es')

        Args:
            agent: The agent being assigned.
            project: The project the agent is being assigned to.

        Returns:
            dict: Initial configuration dictionary.
        """
        config = {}

        # Fetch locale info from VTEX tenant (phone code + language)
        logger.info(
            f"[AssignAgent] Fetching locale info from VTEX: "
            f"project={project.uuid} vtex_account={project.vtex_account}"
        )
        locale_info = self.fetch_country_phone_code_usecase.fetch_locale_info(project)

        if locale_info:
            if locale_info.country_phone_code:
                config["country_phone_code"] = locale_info.country_phone_code

            if locale_info.meta_language:
                config["initial_template_language"] = locale_info.meta_language

            logger.info(
                f"[AssignAgent] Locale info configured: "
                f"project={project.uuid} vtex_account={project.vtex_account} "
                f"country_phone_code={locale_info.country_phone_code} "
                f"language={locale_info.meta_language}"
            )
        else:
            # Fallback to default language if VTEX fetch fails
            config["initial_template_language"] = DEFAULT_TEMPLATE_LANGUAGE
            logger.warning(
                f"[AssignAgent] Could not fetch locale info, using default language: "
                f"project={project.uuid}"
            )

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

    def _create_library_templates(
        self,
        integrated_agent: IntegratedAgent,
        library_rules: List[AgentRule],
        project_uuid: UUID,
        app_uuid: UUID,
    ) -> None:
        """
        Create templates from LIBRARY agent rules (pre-approved by Meta).
        """
        create_library_use_case = CreateLibraryTemplateUseCase()
        for rule in library_rules:
            metadata = rule.metadata or {}
            # TODO: Currently uses metadata.language from validation (fixed pt_BR).
            # To support dynamic language per project, use:
            # integrated_agent.config.get("initial_template_language") or metadata.get("language")
            # May need to re-validate template in Meta with the correct project language.
            data: LibraryTemplateData = {
                "template_name": rule.name,
                "library_template_name": rule.name,
                "category": metadata.get("category"),
                "language": metadata.get("language"),
                "app_uuid": app_uuid,
                "project_uuid": project_uuid,
                "start_condition": rule.start_condition,
            }

            template, version = create_library_use_case.execute(data)

            if not metadata.get("buttons"):
                create_library_use_case.notify_integrations(
                    version.template_name, version.uuid, data
                )
            else:
                template.needs_button_edit = True

            template.metadata = rule.metadata
            template.config = rule.config or {}
            template.parent = rule
            template.integrated_agent = integrated_agent
            template.save()

            integrated_agent.ignore_templates.append(template.parent.slug)
            integrated_agent.save(update_fields=["ignore_templates"])

    def _create_user_existing_templates(
        self,
        integrated_agent: IntegratedAgent,
        user_existing_rules: List[AgentRule],
        project_uuid: UUID,
        app_uuid: UUID,
    ) -> None:
        """
        Create templates from USER_EXISTING agent rules.

        Fetches the user's already-approved templates from integrations service
        and creates local Template records linked to the agent rules.
        """
        logger.info(
            "Fetching user templates in integrations service (user-existing)..."
        )

        template_builder = TemplateBuilderMixin()
        # TODO: Currently uses agent.language (fixed pt_BR) to fetch user templates.
        # To support dynamic language per project, use:
        # integrated_agent.config.get("initial_template_language", agent.language)
        language = integrated_agent.agent.language

        translations_by_name = self.integrations_service.fetch_templates_from_user(
            app_uuid,
            str(project_uuid),
            [rule.name for rule in user_existing_rules],
            language,
        )

        logger.info(
            f"Found {len(translations_by_name)} templates in integrations "
            f"service (user-existing)"
        )

        for rule in user_existing_rules:
            translation = translations_by_name.get(rule.name)
            if translation is not None:
                template, version = template_builder.build_template_and_version(
                    payload={
                        "template_name": rule.name,
                        "app_uuid": app_uuid,
                        "project_uuid": project_uuid,
                    },
                    integrated_agent=integrated_agent,
                )
                template.metadata = translation
                template.config = rule.config or {}
                template.parent = rule
                template.start_condition = rule.start_condition
                template.display_name = rule.display_name
                template.current_version = version
                template.integrated_agent = integrated_agent
                template.save()

                version.template_name = rule.name
                version.status = "APPROVED"
                version.save()

    def _create_templates(
        self,
        integrated_agent: IntegratedAgent,
        agent_rules: List[AgentRule],
        project_uuid: UUID,
        app_uuid: UUID,
        ignore_templates: List[str],
    ) -> None:
        """
        Create templates for the integrated agent based on AgentRule definitions.

        Routes each rule to the appropriate creation flow based on source_type:
        - LIBRARY: Create from Meta's pre-approved library
        - USER_EXISTING: Fetch user's already-approved templates
        """
        agent_rules = agent_rules.exclude(uuid__in=ignore_templates)
        library_rules = agent_rules.filter(source_type="LIBRARY")
        user_existing_rules = agent_rules.filter(source_type="USER_EXISTING")

        self._create_library_templates(
            integrated_agent,
            library_rules,
            project_uuid,
            app_uuid,
        )
        self._create_user_existing_templates(
            integrated_agent,
            user_existing_rules,
            project_uuid,
            app_uuid,
        )

    def _get_ignore_templates(
        self, agent: Agent, include_templates: List[str]
    ) -> List[str]:
        ignore_templates = (
            AgentRule.objects.filter(agent=agent)
            .exclude(uuid__in=include_templates)
            .values_list("uuid", flat=True)
        )

        return list(ignore_templates)

    def _get_ignore_templates_slugs(
        self,
        ignore_templates: List[str],
    ) -> List[str]:
        slugs = AgentRule.objects.filter(uuid__in=ignore_templates).values_list(
            "slug", flat=True
        )
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
        1) Create IntegratedAgent and credentials (with auto-detected language from VTEX)
        2) Create templates from the agent's AgentRule definitions
        3) If the agent is the Abandoned Cart agent (ABANDONED_CART_AGENT_UUID),
           create a default custom template using the custom template flow
           (lifecycle PENDING -> APPROVED, versioning, etc.).

        The initial_template_language is automatically detected from VTEX tenant locale.

        Args:
            agent: The agent to assign.
            project_uuid: UUID of the project to assign the agent to.
            app_uuid: UUID of the WhatsApp app.
            channel_uuid: UUID of the channel.
            credentials: Agent credentials mapping.
            include_templates: List of template UUIDs to include.

        Returns:
            The created IntegratedAgent instance.
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
        logger.info(f"[AssignAgent] integrated_agent created={integrated_agent.uuid}")

        self._create_credentials(integrated_agent, agent, credentials)
        self._create_templates(
            integrated_agent, templates, project_uuid, app_uuid, ignore_templates
        )

        # If this is the abandoned cart agent, create a default custom template
        abandoned_cart_agent_uuid = getattr(settings, "ABANDONED_CART_AGENT_UUID", "")
        if abandoned_cart_agent_uuid and str(agent.uuid) == abandoned_cart_agent_uuid:
            logger.info(f"[AssignAgent] abandoned cart agent detected={agent.uuid}")
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

        The language is taken from integrated_agent.config["initial_template_language"]
        which was auto-detected from VTEX tenant locale.

        Args:
            integrated_agent: The integrated agent instance.
            project: The project instance.
            project_uuid: UUID of the project.
            app_uuid: UUID of the WhatsApp app.
        """
        # Get language from integrated agent config (auto-detected from VTEX)
        template_language = integrated_agent.config.get(
            "initial_template_language", DEFAULT_TEMPLATE_LANGUAGE
        )

        try:
            logger.info(
                f"[AssignAgent] Default custom template flow start for "
                f"integrated_agent={integrated_agent.uuid}, language={template_language}"
            )

            # Build store domain similar to legacy abandoned cart template creation
            domain = f"{project.vtex_account}.vtexcommercestable.com.br"
            button_base_url = f"https://{domain}/checkout?orderFormId="
            button_url_example = f"{button_base_url}92421d4a70224658acaab0c172f6b6d7"

            # Placeholder image URL for template approval (configurable via env)
            # Download and convert to base64 because integrations-engine expects base64
            placeholder_image_url = settings.ABANDONED_CART_DEFAULT_IMAGE_URL
            logger.info(
                f"[AssignAgent] Converting placeholder image to base64: "
                f"{placeholder_image_url}"
            )
            image_converter = ImageUrlToBase64Converter()
            placeholder_image_base64 = image_converter.convert(placeholder_image_url)
            if not placeholder_image_base64:
                raise ValueError(
                    f"Failed to convert placeholder image URL to base64: "
                    f"{placeholder_image_url}"
                )

            # Build translation using the translation builder with selected language
            template_translation = (
                BuildAbandonedCartTranslationUseCase.build_template_translation(
                    language_code=template_language,
                    button_base_url=button_base_url,
                    button_url_example=button_url_example,
                    header_image_base64=placeholder_image_base64,
                )
            )

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
                            # Variable {{1}} in body - required for is_custom=true templates
                            # Frontend validates that body variables are declared
                            {
                                "name": "1",
                                "type": "text",
                                "definition": "Client name",
                                "fallback": "Cliente",
                            },
                            # NOTE: "button" and "image_url" are NOT body variables
                            # They are special variables returned by agent for:
                            # - button: checkout URL suffix (order_form_id)
                            # - image_url: header image (product image from cart)
                        ],
                    },
                ],
                "integrated_agent_uuid": integrated_agent.uuid,
                "use_agent_rule": True,
            }
            logger.info(
                f"[AssignAgent] Custom template payload ready "
                f"display_name={payload['display_name']} "
                f"language={template_language}"
            )

            logger.info(
                "Creating default custom abandoned cart template for integrated agent %s",
                integrated_agent.uuid,
            )
            use_case = CreateCustomTemplateUseCase()
            use_case.execute(payload)
            logger.info(
                f"[AssignAgent] Custom template creation completed for "
                f"integrated_agent={integrated_agent.uuid}, with language={template_language}"
            )
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
