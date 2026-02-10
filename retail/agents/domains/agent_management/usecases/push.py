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

from retail.templates.models import Template


logger = logging.getLogger(__name__)


class SourceData(TypedDict):
    entrypoint: str
    path: str


class RuleItemsData(TypedDict, total=False):
    display_name: str
    template: str
    start_condition: str
    source: SourceData
    template_variables_labels: List[str]


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

    def _is_delivered_order_template(self, rule_slug: str, rule: RuleItemsData) -> bool:
        """
        Detect if a template is related to delivered order tracking.

        Args:
            rule_slug: The slug/key of the rule (e.g., "OrderDelivered")
            rule: Rule data containing template information

        Returns:
            bool: True if template is for delivered order tracking
        """
        # Detection based on standardized rule slug
        return rule_slug.lower() == "orderdelivered"

    def _update_or_create_pre_approved_templates(
        self, agent: Agent, agent_payload: AgentItemsData
    ) -> None:
        for slug, rule in agent_payload["rules"].items():
            # Detect if this is a delivered order template
            is_delivered_order = self._is_delivered_order_template(slug, rule)

            # Prepare config with persistent settings
            config = {}
            if is_delivered_order:
                config["is_delivered_order_template"] = True

            # Store template_variables_labels in config
            template_variables_labels = rule.get("template_variables_labels", [])
            if template_variables_labels:
                config["template_variables_labels"] = template_variables_labels

            PreApprovedTemplate.objects.update_or_create(
                slug=slug,
                agent=agent,
                defaults={
                    "name": rule.get("template"),
                    "start_condition": rule.get("start_condition"),
                    "display_name": rule.get("display_name"),
                    "config": config,
                },
            )

            # Log template creation with variables info
            if template_variables_labels:
                logger.info(
                    f"Template variables labels registered for agent {agent.uuid}: "
                    f"rule_slug='{slug}', template='{rule.get('template')}', "
                    f"variables={template_variables_labels}"
                )

            # Log if delivered order template was detected
            if is_delivered_order:
                logger.info(
                    f"Delivered order template detected for agent {agent.uuid}: "
                    f"rule_slug='{slug}', template='{rule.get('template')}', "
                    f"display_name='{rule.get('display_name')}'"
                )

    @staticmethod
    def has_delivered_order_templates(agent: Agent) -> bool:
        """
        Check if an agent has any delivered order templates.

        Args:
            agent: Agent instance to check

        Returns:
            bool: True if agent has delivered order templates
        """
        # Check PreApprovedTemplate (for unassigned agents)
        pre_approved_exists = agent.templates.filter(
            config__is_delivered_order_template=True
        ).exists()

        # Check Template (for assigned agents)
        template_exists = Template.objects.filter(
            parent__agent=agent, config__is_delivered_order_template=True
        ).exists()

        return pre_approved_exists or template_exists

    @staticmethod
    def has_delivered_order_templates_by_integrated_agent(
        integrated_agent_uuid: str,
    ) -> bool:
        """
        Check if an integrated agent has any integrated delivered order templates.

        A template is considered integrated when it has a current_version with APPROVED status,
        meaning it's been successfully integrated and can be used.

        Args:
            integrated_agent_uuid: UUID of the integrated agent to check

        Returns:
            bool: True if integrated agent has integrated delivered order templates
        """
        # Check Template (for assigned agents) - only integrated templates with approved version
        template_exists = Template.objects.filter(
            integrated_agent__uuid=integrated_agent_uuid,
            config__is_delivered_order_template=True,
            current_version__isnull=False,  # Must have current_version (integrated)
            current_version__status="APPROVED",  # Must have approved version
            is_active=True,
        ).exists()

        return template_exists

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
