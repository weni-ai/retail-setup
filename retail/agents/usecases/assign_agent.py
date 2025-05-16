import secrets

import uuid

import hashlib

import os

from typing import Tuple

from rest_framework.exceptions import NotFound

from retail.agents.models import Agent, IntegratedAgent
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
        return IntegratedAgent.objects.create(
            agent=agent,
            project=project,
            client_secret=hashed_client_secret,
            lambda_arn=agent.lambda_arn,
        )

    def execute(
        self, agent: Agent, project_uuid: uuid.UUID
    ) -> Tuple[IntegratedAgent, str]:
        project = self._get_project(project_uuid)

        client_secret = self._generate_client_secret()
        hashed_client_secret = self._hash_secret(client_secret)

        integrated_agent = self._create_integrated_agent(
            agent=agent,
            project=project,
            hashed_client_secret=hashed_client_secret,
        )

        return integrated_agent, client_secret
