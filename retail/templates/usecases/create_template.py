import logging
from typing import Any, Dict, Optional, TypedDict
from uuid import UUID

from django.conf import settings

from retail.clients.aws_lambda.client import AwsLambdaClient
from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService
from retail.templates.models import Template
from retail.templates.tasks import task_create_template

from ._base_template_creator import TemplateBuilderMixin

logger = logging.getLogger(__name__)


class CreateTemplateData(TypedDict):
    template_translation: Dict[str, Any]
    template_name: str
    start_condition: str
    category: str
    app_uuid: str
    project_uuid: str


class RuleGenerator:
    def execute(self):
        pass


class CreateTemplateUseCase(TemplateBuilderMixin):
    """
    Use case responsible for creating a Meta template and its version.

    This class handles the logic of checking whether a template already exists,
    creating one if necessary, creating a new version, and notifying the
    asynchronous integration process.
    """

    def __init__(self, lambda_service: Optional[AwsLambdaServiceInterface] = None):
        lambda_client = AwsLambdaClient(settings.RULE_GENERATOR_LAMBDA_REGION)
        self.lambda_service = lambda_service or AwsLambdaService(lambda_client)

    def _notify_integrations(
        self, version_name: str, version_uuid: UUID, payload: CreateTemplateData
    ) -> None:
        """
        Notifies the integration layer to asynchronously create the template and its translation.

        Args:
            version_name (str): The generated name of the version (used as template identifier).
            version_uuid (UUID): UUID of the created version.
            payload (CreateTemplateData): Payload containing app/project identifiers and template data.

        Raises:
            ValueError: If any required field is missing from the payload.
        """
        if not all(
            [
                version_name,
                payload.get("app_uuid"),
                payload.get("project_uuid"),
                version_uuid,
            ]
        ):
            raise ValueError("Missing required data to notify integrations")

        task_create_template.delay(
            template_name=version_name,
            app_uuid=payload["app_uuid"],
            project_uuid=payload["project_uuid"],
            category=payload["category"],
            version_uuid=str(version_uuid),
            template_translation=payload["template_translation"],
        )

    def _generate_rule(self) -> str:
        payload = {
            "actionGroup": "MyGroup",
            "function": "MyFunction",
            "parameters": [
                {
                    "name": "variables",
                    "value": '[{"definition": "abcd", "fallback": "dcba"}]',
                },
                {"name": "start_condition", "value": "some condition"},
                {
                    "name": "exemples",
                    "value": '[{"input": "example 1"}, {"input": "example 2"}]',
                },
                {"name": "template_content", "value": "some template text"},
            ],
        }

        response = self.lambda_service.invoke(
            settings.RULE_GENERATOR_LAMBDA_NAME, payload
        )

        logger.info(f"Rules generator invoked successfully: {response}")

        return response.get("Payload")

    def execute(self, payload: CreateTemplateData) -> Template:
        """
        Executes the template creation flow.

        This method will:
        - Retrieve or create a new Template instance.
        - Create a new Version for the template.
        - Trigger the integration notification asynchronously.

        Args:
            payload (CreateTemplateData): The data required to create the template and version.

        Returns:
            Template: The created or existing template instance.
        """

        template, version = self.build_template_and_version(payload)
        self._notify_integrations(version.template_name, version.uuid, payload)
        return template
