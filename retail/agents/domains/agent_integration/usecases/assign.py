import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from typing import Dict, List, TypedDict, Mapping, Any, Optional

from uuid import UUID

from django.db import transaction
from django.conf import settings

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.domains.agent_integration.exceptions import (
    DirectSendTemplateUnavailableError,
    DirectSendUnsupportedComponentError,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent, Credential
from retail.agents.domains.agent_integration.usecases.fetch_country_phone_code import (
    FetchCountryPhoneCodeUseCase,
)
from retail.agents.domains.agent_management.models import Agent, PreApprovedTemplate
from retail.services.integrations.service import IntegrationsService
from retail.services.meta import MetaService
from retail.interfaces.services.integrations import IntegrationsServiceInterface
from retail.interfaces.services.meta import MetaServiceInterface
from retail.projects.models import Project
from retail.templates.usecases.create_library_template import (
    LibraryTemplateData,
    CreateLibraryTemplateUseCase,
)
from retail.templates.usecases._base_template_creator import TemplateBuilderMixin
from retail.templates.usecases._meta_library_template_fetch import (
    fetch_meta_library_template_metadata,
)
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
from retail.agents.domains.agent_integration.usecases.build_payment_recovery_translation import (
    BuildPaymentRecoveryTranslationUseCase,
)
from retail.vtex.usecases.proxy_vtex import ProxyVtexUsecase
from retail.services.vtex_io.service import VtexIOService

logger = logging.getLogger(__name__)


_DIRECT_SEND_FALLBACK_LANGUAGE = "pt_BR"


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


# Settings key -> display_name for agents that manage their own default
# custom template. Single source of truth used by both the template creation
# flows and the reserved-names check that prevents customer templates with
# the same name from shadowing our `weni_<name>_<timestamp>` template.
AGENT_DEFAULT_TEMPLATE_DISPLAY_NAMES: Dict[str, str] = {
    "ABANDONED_CART_AGENT_UUID": "Abandoned Cart",
    "PAYMENT_RECOVERY_AGENT_UUID": "Payment Recovery",
}


class AssignAgentUseCase:
    def __init__(
        self,
        integrations_service: Optional[IntegrationsServiceInterface] = None,
        fetch_country_phone_code_usecase: Optional[FetchCountryPhoneCodeUseCase] = None,
        meta_service: Optional[MetaServiceInterface] = None,
    ):
        self.integrations_service = integrations_service or IntegrationsService()
        self.fetch_country_phone_code_usecase = (
            fetch_country_phone_code_usecase or FetchCountryPhoneCodeUseCase()
        )
        self._meta_service = meta_service

    @property
    def meta_service(self) -> MetaServiceInterface:
        """Lazily construct ``MetaService`` only when the Direct Send branch
        actually needs it.

        ``MetaClient.__init__`` reads ``settings.META_SYSTEM_USER_ACCESS_TOKEN``,
        which is only configured under ``USE_LAMBDA=True``. Eager
        construction in ``__init__`` would break every legacy-cohort
        assignment whose tests don't inject a meta_service mock — the
        Direct Send fetch is the ONLY consumer (`_create_library_templates`
        Direct Send branch), so deferring construction also avoids
        instantiating an unused HTTP client on every legacy assignment.
        """
        if self._meta_service is None:
            self._meta_service = MetaService()
        return self._meta_service

    def _resolve_direct_send_flag(self, agent: Agent, app_uuid: UUID) -> bool:
        """Decide whether the assignment should take the Direct Send path.

        Two signals must both be true (FR-019, contract
        ``integrations-channel-app.md`` §4):

        - the agent is the OrderStatus agent
          (``settings.ORDER_STATUS_AGENT_UUID``);
        - the channel-app reports ``config.direct_send=True``.

        On any failure the conservative default is ``False`` (FR-005).
        """
        order_status_agent_uuid = getattr(settings, "ORDER_STATUS_AGENT_UUID", "")
        if not order_status_agent_uuid or str(agent.uuid) != order_status_agent_uuid:
            return False

        app = self.integrations_service.get_channel_app("wpp-cloud", str(app_uuid))
        if app is None:
            logger.warning(
                f"[DirectSend] channel_lookup_failed: agent={agent.uuid} "
                f"app_uuid={app_uuid} — defaulting to direct_send=False"
            )
            return False

        return bool((app.get("config") or {}).get("direct_send", False))

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
        contact_percentage: Optional[int] = None,
        direct_send: bool = False,
    ) -> IntegratedAgent:
        ignore_templates_slugs = self._get_ignore_templates_slugs(ignore_templates)

        initial_config = self._build_initial_config(agent, project)
        # FR-001 / SC-004: write the key only when True; absence is the
        # canonical legacy marker and writing False on the legacy cohort
        # would expand the persisted config shape and break SC-004 / SC-007.
        if direct_send:
            initial_config["direct_send"] = True

        defaults: Dict[str, Any] = {
            "channel_uuid": channel_uuid,
            "ignore_templates": ignore_templates_slugs,
            "config": initial_config,
        }
        if contact_percentage is not None:
            defaults["contact_percentage"] = contact_percentage

        integrated_agent, created = IntegratedAgent.objects.get_or_create(
            agent=agent,
            project=project,
            is_active=True,
            defaults=defaults,
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

        # Check if this is the payment recovery agent
        payment_recovery_agent_uuid = getattr(
            settings, "PAYMENT_RECOVERY_AGENT_UUID", ""
        )
        if (
            payment_recovery_agent_uuid
            and str(agent.uuid) == payment_recovery_agent_uuid
        ):
            config["payment_recovery"] = {
                "hook_created": False,
                "delay_minutes": 5,
            }

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

    def _resolve_contact_percentage(self, agent: Agent) -> Optional[int]:
        """
        Return the contact_percentage override for specific agent types.

        Payment recovery must reach 100% of eligible contacts from day one;
        other agents keep the model default (10%).
        """
        payment_recovery_agent_uuid = getattr(
            settings, "PAYMENT_RECOVERY_AGENT_UUID", ""
        )
        if (
            payment_recovery_agent_uuid
            and str(agent.uuid) == payment_recovery_agent_uuid
        ):
            return 100
        return None

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
        library_pre_approveds: List[PreApprovedTemplate],
        project_uuid: UUID,
        app_uuid: UUID,
    ) -> None:
        """
        Instantiate pre-approveds that are available in Meta's Library catalog.

        For each spec, create a local Template+Version and (unless the template
        has a URL button requiring manual customization) trigger submission to
        Meta via `CreateLibraryTemplateUseCase.notify_integrations`.
        """
        create_library_use_case = CreateLibraryTemplateUseCase()
        for pre_approved in library_pre_approveds:
            metadata = pre_approved.metadata or {}
            # TODO: Currently uses metadata.language from validation (fixed pt_BR).
            # To support dynamic language per project, use:
            # integrated_agent.config.get("initial_template_language") or metadata.get("language")
            # May need to re-validate template in Meta with the correct project language.
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

            # `or []` covers both missing key and explicit `None` (some Meta
            # library specs include `"buttons": null` for templates without buttons).
            buttons = metadata.get("buttons") or []
            has_url_button = any(button.get("type") == "URL" for button in buttons)

            if has_url_button:
                template.needs_button_edit = True
            else:
                # Submit template to Meta via integrations-engine (Celery task).
                # Skipped for URL buttons because the URL must be customized first.
                create_library_use_case.notify_integrations(
                    version.template_name, version.uuid, data
                )

            template.metadata = pre_approved.metadata
            template.config = pre_approved.config or {}
            template.parent = pre_approved
            template.integrated_agent = integrated_agent
            template.save()

            integrated_agent.ignore_templates.append(template.parent.slug)
            integrated_agent.save(update_fields=["ignore_templates"])

    def _create_direct_send_library_templates(
        self,
        integrated_agent: IntegratedAgent,
        library_pre_approveds: List[PreApprovedTemplate],
        project_uuid: UUID,
        app_uuid: UUID,
    ) -> None:
        """Persist library-catalog templates locally for the Direct Send path.

        For every pre-approved spec, fetches the template content from
        Meta's library catalog in the project-resolved language. If the
        project locale is missing AND it is not already ``pt_BR``,
        retries in ``pt_BR`` (FR-003c). If both attempts fail, raises
        :class:`DirectSendTemplateUnavailableError` so the surrounding
        ``@transaction.atomic`` block rolls back the whole assignment
        (FR-003d). Skips every Integrations Engine template-creation
        call (Decision 5).
        """
        template_builder = TemplateBuilderMixin()
        project_language = integrated_agent.config.get(
            "initial_template_language", DEFAULT_TEMPLATE_LANGUAGE
        )

        for pre_approved in library_pre_approveds:
            content, actual_language = self._fetch_direct_send_template_content(
                pre_approved=pre_approved,
                project=integrated_agent.project,
                integrated_agent=integrated_agent,
                project_language=project_language,
            )

            template, version = template_builder.build_template_and_version(
                payload={
                    "template_name": pre_approved.name,
                    "app_uuid": app_uuid,
                    "project_uuid": project_uuid,
                },
                integrated_agent=integrated_agent,
            )

            template.metadata = {
                **content["metadata"],
                "direct_send": {
                    "fetched_from_meta_library": True,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "requested_language": project_language,
                    "actual_language": actual_language,
                },
            }
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

            integrated_agent.ignore_templates.append(pre_approved.slug)
            integrated_agent.save(update_fields=["ignore_templates"])

            logger.info(
                f"[DirectSend] template_persisted: project_uuid={integrated_agent.project.uuid} "
                f"agent={integrated_agent.uuid} template={pre_approved.name} "
                f"requested_language={project_language} actual_language={actual_language}"
            )

    def _fetch_direct_send_template_content(
        self,
        *,
        pre_approved: PreApprovedTemplate,
        project: Project,
        integrated_agent: IntegratedAgent,
        project_language: str,
    ):
        """Fetch the template content with a ``pt_BR`` per-template fallback.

        Returns ``(content, actual_language)`` on success. Raises
        :class:`DirectSendTemplateUnavailableError` when neither the
        project locale nor ``pt_BR`` returns content (FR-003d). The
        first-locale fetch swallows adapter rejections so the ``pt_BR``
        retry can fire per FR-003c (c); the retry itself propagates
        adapter rejections so the surrounding ``@transaction.atomic``
        rolls back.
        """
        content = self._safely_fetch_direct_send_metadata(
            pre_approved.name, project_language
        )
        actual_language = project_language

        if content is None and project_language != _DIRECT_SEND_FALLBACK_LANGUAGE:
            content = fetch_meta_library_template_metadata(
                self.meta_service, pre_approved.name, _DIRECT_SEND_FALLBACK_LANGUAGE
            )
            if content is not None:
                actual_language = _DIRECT_SEND_FALLBACK_LANGUAGE
                logger.warning(
                    f"[DirectSend] template_language_fallback: "
                    f"project_uuid={project.uuid} agent={integrated_agent.uuid} "
                    f"template={pre_approved.name} "
                    f"requested_language={project_language} "
                    f"fallback_language={_DIRECT_SEND_FALLBACK_LANGUAGE}"
                )

        if content is None:
            reason = "missing_translation"
            logger.error(
                f"[DirectSend] assignment_failed_atomic: "
                f"project_uuid={project.uuid} agent={integrated_agent.uuid} "
                f"template={pre_approved.name} "
                f"requested_language={project_language} fallback_language=pt_BR "
                f"reason={reason}"
            )
            raise DirectSendTemplateUnavailableError(
                template_name=pre_approved.name,
                requested_language=project_language,
                fallback_language=_DIRECT_SEND_FALLBACK_LANGUAGE,
                reason=reason,
            )

        return content, actual_language

    def _safely_fetch_direct_send_metadata(
        self, template_name: str, language: str
    ) -> Optional[Dict[str, Any]]:
        """First-locale fetch with FR-003c routing for adapter rejections.

        Translates ``DirectSendUnsupportedComponentError`` into "no
        usable content" (returns ``None``) so the caller's ``pt_BR``
        retry can fire per FR-003c (c) — but ONLY when a retry is
        actually available (``language`` is non-``pt_BR``). When the
        first-locale fetch IS already ``pt_BR``, no retry is possible,
        so the exception propagates and the operator sees the specific
        ``direct_send_unsupported_component`` code instead of the more
        generic ``direct_send_template_unavailable`` (FR-003d).
        """
        try:
            return fetch_meta_library_template_metadata(
                self.meta_service, template_name, language
            )
        except DirectSendUnsupportedComponentError:
            if language == _DIRECT_SEND_FALLBACK_LANGUAGE:
                raise
            return None

    def _adopt_customer_templates(
        self,
        integrated_agent: IntegratedAgent,
        customer_sourced_pre_approveds: List[PreApprovedTemplate],
        project_uuid: UUID,
        app_uuid: UUID,
    ) -> None:
        """
        Adopt pre-approveds whose source is the customer's WABA.

        No template is submitted to Meta here — we fetch the customer's
        approved translations via `integrations_service.fetch_templates_from_user`
        and register a local Template+Version pointing at the existing Meta
        template. Specs without a matching customer translation are skipped
        silently (nothing to adopt yet).
        """
        logger.info(
            "Fetching customer-approved translations for customer-sourced pre-approveds..."
        )

        template_builder = TemplateBuilderMixin()
        # TODO: Currently uses agent.language (fixed pt_BR) to fetch user templates.
        # To support dynamic language per project, use:
        # integrated_agent.config.get("initial_template_language", agent.language)
        language = integrated_agent.agent.language

        translations_by_name = self.integrations_service.fetch_templates_from_user(
            app_uuid,
            str(project_uuid),
            [pre_approved.name for pre_approved in customer_sourced_pre_approveds],
            language,
        )

        logger.info(
            f"Found {len(translations_by_name)} customer-approved translations to adopt"
        )

        for pre_approved in customer_sourced_pre_approveds:
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

    def _get_reserved_display_names(self, agent: Agent) -> List[str]:
        """
        Return the display names reserved by this agent's default custom template.

        These names must not be adopted from the customer's WABA by
        `_adopt_customer_templates` — adoption would shadow our
        `weni_<name>_<timestamp>` template at broadcast time.
        """
        reserved: List[str] = []
        for setting_name, display_name in AGENT_DEFAULT_TEMPLATE_DISPLAY_NAMES.items():
            if str(agent.uuid) == getattr(settings, setting_name, ""):
                reserved.append(display_name)
        return reserved

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

        Each spec is routed by its source:
        - Library-sourced (`is_valid=True`): instantiate via Meta Library
          catalog and submit to Meta (unless a URL button requires manual
          customization first).
        - Customer-sourced (`is_valid=False`): reuse a translation the
          customer already has approved in their WABA, without submitting to
          Meta. Specs without a matching customer translation are ignored.

        Pre-approveds whose display_name is reserved by the agent's default
        custom template flow are dropped upfront to avoid shadowing the
        `weni_<name>_<timestamp>` template we will create later.
        """
        pre_approveds = pre_approveds.exclude(uuid__in=ignore_templates)

        reserved_display_names = self._get_reserved_display_names(
            integrated_agent.agent
        )
        if reserved_display_names:
            skipped = list(
                pre_approveds.filter(
                    display_name__in=reserved_display_names
                ).values_list("name", flat=True)
            )
            if skipped:
                logger.info(
                    f"[AssignAgent] Skipping pre-approved templates reserved by "
                    f"default custom template flow - "
                    f"agent={integrated_agent.agent.uuid} "
                    f"reserved={reserved_display_names} skipped={skipped}"
                )
                pre_approveds = pre_approveds.exclude(
                    display_name__in=reserved_display_names
                )

        if integrated_agent.config.get("direct_send", False):
            self._create_direct_send_library_templates(
                integrated_agent,
                list(pre_approveds),
                project_uuid,
                app_uuid,
            )
            return

        library_pre_approveds = pre_approveds.filter(is_valid=True)
        customer_sourced_pre_approveds = pre_approveds.filter(is_valid=False)

        self._create_library_templates(
            integrated_agent,
            library_pre_approveds,
            project_uuid,
            app_uuid,
        )
        self._adopt_customer_templates(
            integrated_agent,
            customer_sourced_pre_approveds,
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
        1) Create IntegratedAgent and credentials (with auto-detected language from VTEX)
        2) Create templates from the agent's PreApprovedTemplate definitions
        3) If the agent is the Abandoned Cart agent (ABANDONED_CART_AGENT_UUID),
           create a default custom template using the custom template flow.
        4) If the agent is the Payment Recovery agent (PAYMENT_RECOVERY_AGENT_UUID),
           create a default custom template and a VTEX hook via proxy.

        The initial_template_language is automatically detected from VTEX tenant locale.
        """
        project = self._get_project(project_uuid)
        self._validate_credentials(agent, credentials)

        templates = agent.templates.all()

        ignore_templates = self._get_ignore_templates(agent, include_templates)

        contact_percentage = self._resolve_contact_percentage(agent)

        direct_send = self._resolve_direct_send_flag(agent, app_uuid)

        integrated_agent = self._create_integrated_agent(
            agent=agent,
            project=project,
            channel_uuid=channel_uuid,
            ignore_templates=ignore_templates,
            contact_percentage=contact_percentage,
            direct_send=direct_send,
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

        # If this is the payment recovery agent, create template + VTEX hook
        payment_recovery_agent_uuid = getattr(
            settings, "PAYMENT_RECOVERY_AGENT_UUID", ""
        )
        if (
            payment_recovery_agent_uuid
            and str(agent.uuid) == payment_recovery_agent_uuid
        ):
            logger.info(f"[AssignAgent] payment recovery agent detected={agent.uuid}")
            template_created = self._create_default_payment_recovery_template(
                integrated_agent=integrated_agent,
                project_uuid=project_uuid,
                app_uuid=app_uuid,
            )
            if template_created:
                self._create_payment_recovery_hook(integrated_agent)
            else:
                logger.warning(
                    f"[AssignAgent] Skipping hook creation — template failed for "
                    f"integrated_agent={integrated_agent.uuid}"
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

            vtex_host_store = project.config.get("vtex_host_store")
            if vtex_host_store:
                domain = urlparse(vtex_host_store).netloc
            else:
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
                "display_name": AGENT_DEFAULT_TEMPLATE_DISPLAY_NAMES[
                    "ABANDONED_CART_AGENT_UUID"
                ],
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

    def _build_payment_recovery_webhook_url(
        self, integrated_agent: IntegratedAgent
    ) -> str:
        domain_url = settings.DOMAIN
        return (
            f"{domain_url}/api/v3/agents/"
            f"payment-recovery-webhook/{integrated_agent.uuid}/"
        )

    def _create_default_payment_recovery_template(
        self,
        integrated_agent: IntegratedAgent,
        project_uuid: UUID,
        app_uuid: UUID,
    ) -> bool:
        """
        Create a default custom template for the payment recovery agent.

        Uses the same image placeholder as abandoned cart. The template has
        PAYMENT_REQUEST buttons with placeholder payment data for approval.

        Returns:
            True if the template was created (or already exists), False on failure.
        """
        template_language = integrated_agent.config.get(
            "initial_template_language", DEFAULT_TEMPLATE_LANGUAGE
        )

        try:
            logger.info(
                f"[PaymentRecovery] Template creation started - "
                f"agent={integrated_agent.uuid} language={template_language}"
            )

            placeholder_image_url = settings.ABANDONED_CART_DEFAULT_IMAGE_URL
            image_converter = ImageUrlToBase64Converter()
            placeholder_image_base64 = image_converter.convert(placeholder_image_url)
            if not placeholder_image_base64:
                raise ValueError(
                    f"Failed to convert placeholder image URL to base64: "
                    f"{placeholder_image_url}"
                )

            template_translation = (
                BuildPaymentRecoveryTranslationUseCase.build_template_translation(
                    language_code=template_language,
                    header_image_base64=placeholder_image_base64,
                )
            )

            payload: CreateCustomTemplateData = {
                "template_translation": template_translation,
                "category": "MARKETING",
                "app_uuid": str(app_uuid),
                "project_uuid": str(project_uuid),
                "display_name": AGENT_DEFAULT_TEMPLATE_DISPLAY_NAMES[
                    "PAYMENT_RECOVERY_AGENT_UUID"
                ],
                "start_condition": "If payment_status is pending",
                "parameters": [
                    {
                        "name": "start_condition",
                        "value": "If payment_status is pending",
                    },
                    {
                        "name": "variables",
                        "value": [
                            {
                                "name": "1",
                                "type": "text",
                                "definition": "Client name",
                                "fallback": "Cliente",
                            },
                        ],
                    },
                ],
                "integrated_agent_uuid": integrated_agent.uuid,
                "use_agent_rule": True,
            }

            use_case = CreateCustomTemplateUseCase()
            use_case.execute(payload)
            logger.info(
                f"[PaymentRecovery] Template created successfully - "
                f"agent={integrated_agent.uuid} language={template_language}"
            )
            return True
        except CustomTemplateAlreadyExists:
            logger.info(
                f"[PaymentRecovery] Template already exists - "
                f"agent={integrated_agent.uuid}"
            )
            return True
        except Exception as exc:
            logger.exception(
                f"[PaymentRecovery] Template creation failed - "
                f"agent={integrated_agent.uuid}: {exc}"
            )
            return False

    def _create_payment_recovery_hook(self, integrated_agent: IntegratedAgent) -> None:
        """
        Create a VTEX hook via proxy to monitor payment-pending orders.

        Uses the proxy route (retail -> IO) so no VTEX app key/token is needed.
        Saves the webhook URL and hook status in integrated_agent.config.
        """
        try:
            webhook_url = self._build_payment_recovery_webhook_url(integrated_agent)

            logger.info(
                f"[PaymentRecovery] Creating VTEX hook - "
                f"agent={integrated_agent.uuid} webhook_url={webhook_url}"
            )

            hook_data = {
                "filter": {
                    "type": "FromOrders",
                    "expression": (
                        'isCompleted = false and (salesChannel = "1") '
                        "and (paymentData.transactions.payments"
                        '[paymentSystem = "125"])'
                    ),
                    "disableSingleFire": False,
                },
                "hook": {
                    "url": webhook_url,
                    "headers": {"User-Agent": "vtex-retail/0.0.0"},
                },
            }

            proxy_usecase = ProxyVtexUsecase(vtex_io_service=VtexIOService())
            proxy_usecase.execute(
                method="POST",
                path="/api/orders/hook/config",
                data=hook_data,
                project_uuid=str(integrated_agent.project.uuid),
            )

            current_config = integrated_agent.config.copy()
            payment_recovery_config = current_config.get("payment_recovery", {})
            payment_recovery_config.update(
                {
                    "webhook_url": webhook_url,
                    "hook_created": True,
                }
            )
            current_config["payment_recovery"] = payment_recovery_config
            integrated_agent.config = current_config
            integrated_agent.save(update_fields=["config"])

            logger.info(
                f"[PaymentRecovery] VTEX hook created successfully - "
                f"agent={integrated_agent.uuid}"
            )
        except Exception as exc:
            logger.exception(
                f"[PaymentRecovery] VTEX hook creation failed - "
                f"agent={integrated_agent.uuid}: {exc}"
            )
