import json

from typing import Optional, Dict, Any, TypedDict, List

from enum import IntEnum

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
    CodeGeneratorInternalServerError,
)
from retail.agents.models import IntegratedAgent


class LambdaResponsePayload(TypedDict):
    statusCode: int
    body: Dict[str, Any]


class LambdaResponseStatusCode(IntEnum):
    OK = 200
    BAD_REQUEST = 400
    UNPROCESSABLE_ENTITY = 422


class ParameterData(TypedDict):
    name: str
    value: Any


class CreateCustomTemplateData(CreateTemplateData):
    parameters: List[ParameterData]
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

    def _invoke_code_generator(self, params: List[ParameterData]) -> Dict[str, Any]:
        payload = {
            "parameters": params,
        }

        response = self.lambda_service.invoke(
            function_name=self.lambda_code_generator, payload=payload
        )

        response_payload = json.loads(response["Payload"].read())

        return response_payload

    def _adapt_translation(
        self, template_translation: Dict[str, Any]
    ) -> Dict[str, Any]:
        return self.template_adapter.adapt(
            {
                "header": template_translation.get("template_header"),
                "body": template_translation.get("template_body"),
                "footer": template_translation.get("template_footer"),
                "buttons": template_translation.get("template_button"),
            }
        )

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
        display_name: str,
        start_condition: str,
    ) -> Template:
        template.integrated_agent = integrated_agent
        template.metadata = translation
        template.rule_code = body.get("generated_code")
        template.display_name = display_name
        template.start_condition = start_condition
        template.save()
        return template

    def _get_integrated_agent(self, integrated_agent_uuid: UUID):
        try:
            return IntegratedAgent.objects.get(
                uuid=integrated_agent_uuid, is_active=True
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Assigned agent not found: {integrated_agent_uuid}")

    def _handle_successful_code_generation(
        self, payload: CreateCustomTemplateData, body: Dict[str, Any]
    ) -> Template:
        template, version = self.build_template_and_version(payload)
        translation = self._adapt_translation(payload.get("template_translation"))
        integrated_agent = self._get_integrated_agent(
            payload.get("integrated_agent_uuid")
        )

        start_condition = next(
            (
                param.get("value")
                for param in payload.get("parameters")
                if param.get("name") == "start_condition"
            ),
            None,
        )

        template = self._update_template(
            template,
            body,
            translation,
            integrated_agent,
            payload.get("display_name"),
            start_condition,
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

    def execute(self, payload: CreateCustomTemplateData) -> Template:
        """
        Executes the custom template creation flow.

        Args:
            payload (CreateCustomTemplateData): The input data containing template content and rule code.

        Returns:
            Template: The created template instance.
        """
        response_payload = self._invoke_code_generator(payload["parameters"])

        status_code = response_payload.get("statusCode")
        body = response_payload.get("body")

        if status_code is not None:
            match status_code:
                case LambdaResponseStatusCode.OK:
                    return self._handle_successful_code_generation(payload, body)

                case LambdaResponseStatusCode.BAD_REQUEST:
                    raise CodeGeneratorBadRequest(detail=body)

                case LambdaResponseStatusCode.UNPROCESSABLE_ENTITY:
                    raise CodeGeneratorUnprocessableEntity(detail=body)

        raise CodeGeneratorInternalServerError(
            detail={"message": "Unknown error from lambda.", "error": response_payload}
        )
