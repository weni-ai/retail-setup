import secrets

import uuid

import hashlib

import os

from typing import Tuple

from django.db.models import QuerySet, Q

from rest_framework.exceptions import ValidationError, NotFound

from retail.agents.models import Agent, PreApprovedTemplate, IntegratedAgent

SECRET_NUM_BYTES = 32

URANDOM_SIZE = 16


class AssignAgentUseCase:
    def _verify_templates_from_meta(
        self, templates: QuerySet[PreApprovedTemplate]
    ) -> None:
        invalid_templates = templates.filter(Q(is_valid=False) | Q(is_valid=None))

        if invalid_templates.exists():
            raise ValidationError(
                {
                    "message": "It is not possible to assign an agent with invalid templates.",
                    "invalid_templates": list(
                        invalid_templates.values_list("name", flat=True)
                    ),
                }
            )

    def _generate_client_secret(self) -> str:
        return secrets.token_urlsafe(SECRET_NUM_BYTES)

    def _generate_webhook_uuid(self) -> uuid.UUID:
        return uuid.uuid4()

    def _hash_secret(self, client_secret: str) -> str:
        salt = os.urandom(URANDOM_SIZE)
        hashed_secret = hashlib.sha256(salt + client_secret.encode()).hexdigest()
        return f"{salt.hex()}:{hashed_secret}"

    def _create_integrated_agent(
        self,
        agent: Agent,
        hashed_client_secret: str,
        webhook_uuid: str,
    ) -> IntegratedAgent:
        return IntegratedAgent.objects.create(
            agent=agent,
            project=agent.project,
            webhook_uuid=webhook_uuid,
            client_secret=hashed_client_secret,
        )

    def execute(self, agent: Agent) -> Tuple[IntegratedAgent, str]:
        templates = agent.templates.all()
        self._verify_templates_from_meta(templates)

        webhook_uuid = self._generate_webhook_uuid()
        client_secret = self._generate_client_secret()
        hashed_client_secret = self._hash_secret(client_secret)

        integrated_agent = self._create_integrated_agent(
            agent=agent,
            hashed_client_secret=hashed_client_secret,
            webhook_uuid=webhook_uuid,
        )

        return integrated_agent, client_secret
