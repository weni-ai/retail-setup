import logging

from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService
from retail.agents.models import Agent, PreApprovedTemplate
from retail.projects.models import Project
from retail.agents.exceptions import AgentFileNotSent

from django.core.files.uploadedfile import UploadedFile

from rest_framework.exceptions import NotFound

from typing import Optional, Dict, TypedDict, List

from uuid import UUID

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
    pre_result_examples_file: str


class AgentItemsData(TypedDict):
    name: str
    rules: RuleData
    pre_processing: PreProcessingData


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

    def _get_or_create_agent(self, payload: AgentItemsData, project: Project) -> Agent:
        agent, created = Agent.objects.get_or_create(
            name=payload.get("name"),
            project=project,
            defaults={
                "is_oficial": False,
            },
        )
        return agent, created

    def _upload_to_lambda(self, file_obj: UploadedFile, function_name: str) -> str:
        lambda_arn = self.lambda_service.send_file(
            file_obj=file_obj, function_name=function_name
        )

        return lambda_arn

    def _assign_arn_to_integrated_agent(
        self, lambda_arn: str, agent: Agent, project: Project
    ) -> None:
        integrated_agent = agent.integrateds.filter(project=project)

        if integrated_agent.exists():
            integrated_agent = integrated_agent.first()
            integrated_agent.lambda_arn = lambda_arn
            integrated_agent.save()

    def _assign_arn_to_agent(self, lambda_arn: str, agent: Agent) -> Agent:
        agent.lambda_arn = lambda_arn
        agent.save()
        return agent

    def _create_function_name(self, agent_name: str, agent_uuid: UUID) -> str:
        simple_hash = f"{agent_name}_{str(agent_uuid.hex)}"
        return simple_hash

    def _create_pre_approved_templates(
        self, agent: Agent, agent_payload: AgentItemsData
    ) -> None:
        templates = [
            PreApprovedTemplate.objects.get_or_create(
                name=rule.get("template"), start_condition=rule.get("start_condition")
            )[0]
            for rule in agent_payload["rules"].values()
        ]
        agent.templates.set(templates)

    def execute(
        self, payload: PushAgentData, files: Dict[str, UploadedFile]
    ) -> List[Agent]:
        project = self._get_project(payload.get("project_uuid"))
        agents = payload.get("agents")

        assigned_agents = []

        for key, value in agents.items():
            agent, _ = self._get_or_create_agent(payload=value, project=project)
            file_obj = files.get(key)

            if not file_obj:
                raise AgentFileNotSent(detail=f"File for agent {key} not sent.")

            lambda_arn = self._upload_to_lambda(
                file_obj=file_obj,
                function_name=self._create_function_name(key, agent.uuid),
            )
            agent = self._assign_arn_to_agent(lambda_arn, agent)
            self._assign_arn_to_integrated_agent(lambda_arn, agent, project)
            self._create_pre_approved_templates(agent, value)
            assigned_agents.append(agent)

            logger.info(f"Agent push completed: {agent.uuid}")

        return assigned_agents
