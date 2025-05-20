import secrets

import hashlib

import os

from typing import Tuple, List, TypedDict

from uuid import UUID

from django.db.models import QuerySet

from rest_framework.exceptions import NotFound

from retail.agents.models import Agent, IntegratedAgent, PreApprovedTemplate
from retail.projects.models import Project
from retail.templates.usecases.create_library_template import (
    CreateLibraryTemplateData,
    CreateLibraryTemplateUseCase,
)

SECRET_NUM_BYTES = 32

URANDOM_SIZE = 16


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

    def _generate_client_secret(self) -> str:
        return secrets.token_urlsafe(SECRET_NUM_BYTES)

    def _hash_secret(self, client_secret: str) -> str:
        salt = os.urandom(URANDOM_SIZE)
        hashed_secret = hashlib.sha256(salt + client_secret.encode()).hexdigest()
        return f"{salt.hex()}:{hashed_secret}"

    def _create_integrated_agent(
        self,
        agent: Agent,
        project: Project,
        hashed_client_secret: str,
    ) -> IntegratedAgent:
        return IntegratedAgent.objects.create(
            agent=agent,
            project=project,
            client_secret=hashed_client_secret,
            lambda_arn=agent.lambda_arn,
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
        templates: QuerySet[PreApprovedTemplate],
        project_uuid: UUID,
        app_uuid: UUID,
    ) -> None:
        use_case = CreateLibraryTemplateUseCase()

        for template in templates:
            if not template.is_valid:
                pass

            metadata = template.metadata or {}
            data: CreateLibraryTemplateData = {
                "template_name": metadata.get("name"),
                "library_template_name": metadata.get("name"),
                "category": metadata.get("category"),
                "language": metadata.get("language"),
                "app_uuid": app_uuid,
                "project_uuid": project_uuid,
                "start_condition": template.start_condition,
                "library_template_button_inputs": self._adapt_button(
                    metadata.get("buttons")
                ),
            }
            raw_template = use_case.execute(data)
            raw_template.integrated_agent = integrated_agent
            raw_template.save()

    def execute(
        self, agent: Agent, project_uuid: UUID, app_uuid: UUID
    ) -> Tuple[IntegratedAgent, str]:
        project = self._get_project(project_uuid)
        templates = agent.templates.all()

        client_secret = self._generate_client_secret()
        hashed_client_secret = self._hash_secret(client_secret)

        integrated_agent = self._create_integrated_agent(
            agent=agent,
            project=project,
            hashed_client_secret=hashed_client_secret,
        )

        self._create_templates(integrated_agent, templates, project_uuid, app_uuid)

        return integrated_agent, client_secret
