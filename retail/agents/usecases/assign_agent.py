import hashlib
import os
import secrets
import uuid
from typing import Tuple

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.models import Agent, Credential, IntegratedAgent
from retail.projects.models import Project

SECRET_NUM_BYTES = 32

URANDOM_SIZE = 16


class AssignAgentUseCase:
    def _get_project(self, project_uuid: uuid.UUID):
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
        integrated_agent, created =  IntegratedAgent.objects.get_or_create(
            agent=agent,
            project=project,
            defaults={
                "client_secret": hashed_client_secret,
                "lambda_arn": agent.lambda_arn,
            }
        )
        
        if not created:
            raise ValidationError("Agent already integrated to this project")

        return integrated_agent


    def _validate_credentials(self, agent: Agent, credentials: dict):
        for key in agent.credentials.keys():
            credential = credentials.get(key, None)

            if credential is None:
                raise ValidationError(f"Credential {key} is required")

    def _create_credentials(self, integrated_agent: IntegratedAgent, agent: Agent, credentials: dict) -> None:
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
                }
            )

    def execute(
        self, agent: Agent, project_uuid: uuid.UUID, credentials: dict
    ) -> Tuple[IntegratedAgent, str]:
        project = self._get_project(project_uuid)
        self._validate_credentials(agent, credentials)

        client_secret = self._generate_client_secret()
        hashed_client_secret = self._hash_secret(client_secret)

        integrated_agent = self._create_integrated_agent(
            agent=agent,
            project=project,
            hashed_client_secret=hashed_client_secret,
        )

        self._create_credentials(integrated_agent, agent, credentials)

        return integrated_agent, client_secret
