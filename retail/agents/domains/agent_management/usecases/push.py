import logging

import hashlib

import base64

from typing import Any, Dict, List, Optional, TypedDict

from uuid import UUID

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from rest_framework.exceptions import NotFound

from retail.agents.domains.agent_management.exceptions import AgentFileNotSent
from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_management.models import PreApprovedTemplate
from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService
from retail.projects.models import Project

logger = logging.getLogger(__name__)


class SourceData(TypedDict):
    entrypoint: str
    path: str


class RuleItemsData(TypedDict):
    display_name: str
    template: str
    start_condition: str
    source: SourceData


RuleData = Dict[str, RuleItemsData]


class PreProcessingData(TypedDict, total=False):
    source: SourceData
    result_examples_file: str
    result_example: List[Dict[str, Any]]


class AgentItemsData(TypedDict):
    name: str
    description: str
    rules: RuleData
    pre_processing: PreProcessingData
    language: str


class PushAgentData(TypedDict):
    project_uuid: str
    agents: Dict[str, AgentItemsData]


class PushAgentUseCase:
    def __init__(self, lambda_service: Optional[AwsLambdaServiceInterface] = None):
        self.lambda_service = lambda_service or AwsLambdaService()

    def _get_project(self, project_uuid: str) -> Project:
        try:
            return Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            raise NotFound(f"No project found for UUID: {project_uuid}")

    def _parse_credentials(self, credentials: List[Dict]) -> Dict:
        return {credential.get("key"): credential for credential in credentials}

    def _update_or_create_agent(
        self, payload: AgentItemsData, slug: str, project: Project
    ) -> Agent:
        credentials = self._parse_credentials(payload.get("credentials", []))
        examples = payload.get("pre_processing", {}).get("result_example", [])

        agent, created = Agent.objects.update_or_create(
            slug=slug,
            project=project,
            defaults={
                "name": payload.get("name"),
                "description": payload.get("description"),
                "credentials": credentials,
                "language": payload.get("language"),
                "examples": examples,
            },
        )

        if not created:
            agent.credentials = credentials
            agent.save()

        return agent, created

    def _upload_to_lambda(self, file_obj: UploadedFile, function_name: str) -> str:
        lambda_arn = self.lambda_service.send_file(
            file_obj=file_obj, function_name=function_name
        )

        return lambda_arn

    def _assign_arn_to_agent(self, lambda_arn: str, agent: Agent) -> Agent:
        agent.lambda_arn = lambda_arn
        agent.save()
        return agent

    def _create_function_name(self, agent_name: str, agent_uuid: UUID) -> str:
        input_hash_string = f"{agent_name}-{str(agent_uuid.hex)}"

        hash_object = hashlib.sha256(input_hash_string.encode("utf-8"))
        hash_bytes = hash_object.digest()

        base64_hash = base64.b64encode(hash_bytes).decode("utf-8")
        only_alphanumeric_hash = "".join(c.lower() for c in base64_hash if c.isalnum())

        hash_13_digits = only_alphanumeric_hash[:13]

        return f"retail-setup-{hash_13_digits}"

    def _update_or_create_pre_approved_templates(
        self, agent: Agent, agent_payload: AgentItemsData
    ) -> None:
        for slug, rule in agent_payload["rules"].items():
            PreApprovedTemplate.objects.update_or_create(
                slug=slug,
                agent=agent,
                defaults={
                    "name": rule.get("template"),
                    "start_condition": rule.get("start_condition"),
                    "display_name": rule.get("display_name"),
                },
            )

    @transaction.atomic
    def execute(
        self, payload: PushAgentData, files: Dict[str, UploadedFile]
    ) -> List[Agent]:
        project = self._get_project(payload.get("project_uuid"))
        agents = payload.get("agents")

        created_agents = []

        for key, value in agents.items():
            agent, _ = self._update_or_create_agent(
                payload=value, slug=key, project=project
            )
            file_obj = files.get(key)

            if not file_obj:
                raise AgentFileNotSent(detail=f"File for agent {key} not sent.")

            lambda_arn = self._upload_to_lambda(
                file_obj=file_obj,
                function_name=self._create_function_name(key, agent.uuid),
            )
            agent = self._assign_arn_to_agent(lambda_arn, agent)
            self._update_or_create_pre_approved_templates(agent, value)
            created_agents.append(agent)

            logger.info(f"Agent push completed: {agent.uuid}")

        return created_agents
