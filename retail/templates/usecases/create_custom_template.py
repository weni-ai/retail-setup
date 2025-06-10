import json

from typing import Optional, Dict, Any, TypedDict

from enum import Enum

from uuid import UUID

from django.conf import settings

from rest_framework.exceptions import NotFound

from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService
from retail.templates.usecases import CreateTemplateData
from retail.templates.adapters.template_library_to_custom_adapter import (
    TemplateTranslationAdapter,
)
from retail.templates.usecases._base_template_creator import TemplateBuilderMixin
from retail.templates.tasks import task_create_template
from retail.templates.models import Template
from retail.templates.exceptions import (
    CodeGeneratorBadRequest,
    CodeGeneratorUnprocessableEntity,
)
from retail.agents.models import IntegratedAgent


class LambdaResponsePayload(TypedDict):
    statusCode: int
    body: Dict[str, Any]


class LambdaResponseStatusCode(Enum):
    OK = 200
    BAD_REQUEST = 400
    UNPROCESSABLE_ENTITY = 422


class CreateCustomTemplateData(CreateTemplateData):
    rule_code: str
    category: str
    integrated_agent_uuid: UUID


class CreateCustomTemplateUseCase(TemplateBuilderMixin):
    def __init__(
        self,
        lambda_service: Optional[AwsLambdaServiceInterface] = None,
        template_adapter: Optional[TemplateTranslationAdapter] = None,
    ):
        self.lambda_service = lambda_service or AwsLambdaService()
        self.lambda_code_generator = getattr(
            settings,
            "LAMBDA_CODE_GENERATOR",
            "arn:aws:lambda:us-east-1:123456789012:function:mock",
        )
        self.template_adapter = template_adapter or TemplateTranslationAdapter()

    def _invoke_code_generator(self, rule_code: str) -> Dict[str, Any]:
        payload = {
            "actionGroup": "MyGroup",
            "function": "MyFunction",
            "parameters": [
                {
                    "name": "variables",
                    "value": '[{"definition": "abcd", "fallback": "dcba"}]',
                },
                {
                    "name": "start_condition",
                    "value": "some condition",
                },
                {
                    "name": "exemples",
                    "value": '[{"input": "example 1"}, {"input": "example 2"}]',
                },
                {
                    "name": "template_content",
                    "value": "some template text",
                },
            ],
        }
        response = self.lambda_service.invoke(
            function_name=self.lambda_code_generator, payload=payload
        )

        response_payload = json.load(response["Payload"])

        return response_payload["statusCode"], response_payload["body"]

    def _adapt_translation(
        self, template_translation: Dict[str, Any]
    ) -> Dict[str, Any]:
        return self.template_adapter.adapt(template_translation)

    def _notify_integrations(
        self,
        version_name: str,
        version_uuid: UUID,
        translation_payload: dict,
        app_uuid: str,
        project_uuid: str,
        category: str,
    ) -> None:
        buttons = translation_payload.get("buttons")

        if buttons:
            for button in buttons:
                button["button_type"] = button.pop("type", None)

        task_create_template.delay(
            template_name=version_name,
            app_uuid=app_uuid,
            project_uuid=project_uuid,
            category=category,
            version_uuid=str(version_uuid),
            template_translation=translation_payload,
        )

    def _update_template(
        self,
        template: Template,
        body: Dict[str, Any],
        translation: Dict[str, Any],
        integrated_agent: IntegratedAgent,
    ) -> Template:
        template.integrated_agent = integrated_agent
        template.metadata = translation
        template.rule_code = body.get("generated_code")
        template.save()
        return template

    def _get_integrated_agent(self, integrated_agent_uuid: UUID):
        try:
            return IntegratedAgent.objects.get(id=integrated_agent_uuid, is_active=True)
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Assigned agent not found: {integrated_agent_uuid}")

    def execute(self, payload: CreateCustomTemplateData) -> Template:
        """
        Executes the custom template creation flow.

        Args:
            payload (CreateCustomTemplateData): The input data containing template content and rule code.

        Returns:
            Template: The created template instance.
        """
        status_code, body = self._invoke_code_generator(payload["rule_code"])

        if status_code == LambdaResponseStatusCode.OK:
            template, version = self.build_template_and_version()
            translation = self._adapt_translation(payload.get("template_translation"))
            integrated_agent = self._get_integrated_agent(
                payload.get("integrated_agent_uuid")
            )
            template = self._update_template(
                template, body, translation, integrated_agent
            )
            self._notify_integrations(
                version.template_name,
                version.uuid,
                translation,
                payload.get("app_uuid"),
                payload.get("project_uuid"),
                payload.get("category"),
            )
            return template

        if status_code == LambdaResponseStatusCode.BAD_REQUEST:
            raise CodeGeneratorBadRequest(detail=body)

        if status_code == LambdaResponseStatusCode.UNPROCESSABLE_ENTITY:
            raise CodeGeneratorUnprocessableEntity(detail=body)
