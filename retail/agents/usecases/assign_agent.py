from typing import List, TypedDict

from uuid import UUID

from django.db.models import QuerySet

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.models import Agent, Credential, IntegratedAgent, PreApprovedTemplate
from retail.projects.models import Project
from retail.templates.usecases.create_library_template import (
    CreateLibraryTemplateData,
    CreateLibraryTemplateUseCase,
)


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
    def _get_project(self, project_uuid: UUID):
        try:
            return Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            raise NotFound(f"Project not found: {project_uuid}")

    def _create_integrated_agent(
        self, agent: Agent, project: Project, channel_uuid: UUID
    ) -> IntegratedAgent:
        integrated_agent, created = IntegratedAgent.objects.get_or_create(
            agent=agent,
            project=project,
            defaults={
                "channel_uuid": channel_uuid,
            },
        )

        if not created:
            raise ValidationError(
                detail={"agent": "This agent is already assigned in this project."}
            )

        return integrated_agent

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

    def _adapt_button(
        self, buttons: List[MetaButtonFormat]
    ) -> List[IntegrationsButtonFormat]:
        integration_buttons = []

        for button in buttons:
            integration_button_url_format = IntegrationsButtonUrlFormat(
                base_url=button.get("url"), url_suffix_example=button.get("url")
            )
            integrations_button = IntegrationsButtonFormat(
                type=button.get("type"), url=integration_button_url_format
            )
            integration_buttons.append(integrations_button)

        return integration_buttons

    def _create_templates(
        self,
        integrated_agent: IntegratedAgent,
        pre_approveds: QuerySet[PreApprovedTemplate],
        project_uuid: UUID,
        app_uuid: UUID,
    ) -> None:
        use_case = CreateLibraryTemplateUseCase()

        for pre_approved in pre_approveds:
            if not pre_approved.is_valid:
                continue

            metadata = pre_approved.metadata or {}
            data: CreateLibraryTemplateData = {
                "template_name": metadata.get("name"),
                "library_template_name": metadata.get("name"),
                "category": metadata.get("category"),
                "language": metadata.get("language"),
                "app_uuid": app_uuid,
                "project_uuid": project_uuid,
                "start_condition": pre_approved.start_condition,
            }

            if metadata.get("buttons"):
                data["library_template_button_inputs"] = self._adapt_button(
                    metadata.get("buttons")
                )

            template = use_case.execute(data)
            template.metadata = pre_approved.metadata
            template.parent = pre_approved
            template.integrated_agent = integrated_agent
            template.save()

    def execute(
        self,
        agent: Agent,
        project_uuid: UUID,
        app_uuid: UUID,
        channel_uuid: UUID,
        credentials: dict,
    ) -> IntegratedAgent:
        project = self._get_project(project_uuid)
        self._validate_credentials(agent, credentials)

        templates = agent.templates.all()

        integrated_agent = self._create_integrated_agent(
            agent=agent,
            project=project,
            channel_uuid=channel_uuid,
        )

        self._create_credentials(integrated_agent, agent, credentials)
        self._create_templates(integrated_agent, templates, project_uuid, app_uuid)

        return integrated_agent
