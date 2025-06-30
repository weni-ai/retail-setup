import json
import copy

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

from uuid import UUID

from enum import IntEnum

from django.conf import settings

from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService
from retail.templates.adapters.template_library_to_custom_adapter import (
    TemplateTranslationAdapter,
)
from retail.templates.models import Template
from retail.templates.tasks import task_create_template
from retail.templates.exceptions import (
    CodeGeneratorBadRequest,
    CodeGeneratorUnprocessableEntity,
    CodeGeneratorInternalServerError,
)
from retail.templates.usecases._base_template_creator import TemplateBuilderMixin


class LambdaResponseStatusCode(IntEnum):
    OK = 200
    BAD_REQUEST = 400
    UNPROCESSABLE_ENTITY = 422


class UpdateTemplateStrategy(ABC):
    """Abstract strategy for template updates"""

    def __init__(self, template_adapter: Optional[TemplateTranslationAdapter] = None):
        self.template_adapter = template_adapter or TemplateTranslationAdapter()

    @abstractmethod
    def update_template(self, template: Template, payload: Dict[str, Any]) -> Template:
        """Execute the template update strategy"""
        pass

    def _adapt_translation(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Common method to adapt template translation"""
        return self.template_adapter.adapt(metadata)

    def _notify_integrations(
        self,
        version_name: str,
        version_uuid: UUID,
        translation_payload: dict,
        app_uuid: str,
        project_uuid: str,
        category: str,
    ) -> None:
        """Common method to notify integrations"""
        if not all([version_name, app_uuid, project_uuid, version_uuid]):
            raise ValueError("Missing required data to notify integrations")

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


class UpdateNormalTemplateStrategy(UpdateTemplateStrategy, TemplateBuilderMixin):
    """Strategy for updating normal templates"""

    def update_template(self, template: Template, payload: Dict[str, Any]) -> Template:
        if not template.metadata:
            raise ValueError("Template metadata is missing")

        category = template.metadata.get("category")
        if not category:
            raise ValueError("Missing category in template metadata")

        updated_metadata = dict(template.metadata)

        updated_metadata["body"] = payload.get(
            "template_body", template.metadata.get("body")
        )
        updated_metadata["header"] = payload.get(
            "template_header", template.metadata.get("header")
        )
        updated_metadata["footer"] = payload.get(
            "template_footer", template.metadata.get("footer")
        )
        updated_metadata["buttons"] = payload.get(
            "template_button", template.metadata.get("buttons")
        )

        translation_payload = self._adapt_translation(updated_metadata)
        updated_metadata["buttons"] = translation_payload.get("buttons")

        template.metadata = updated_metadata
        template.save(update_fields=["metadata"])

        version = self._create_version(
            template=template,
            app_uuid=payload["app_uuid"],
            project_uuid=payload["project_uuid"],
        )

        self._notify_integrations(
            version_name=version.template_name,
            version_uuid=version.uuid,
            translation_payload=copy.deepcopy(translation_payload),
            app_uuid=payload["app_uuid"],
            project_uuid=payload["project_uuid"],
            category=category,
        )

        return template


class UpdateCustomTemplateStrategy(UpdateTemplateStrategy, TemplateBuilderMixin):
    """Strategy for updating custom templates"""

    def __init__(
        self,
        template_adapter: Optional[TemplateTranslationAdapter] = None,
        lambda_service: Optional[AwsLambdaServiceInterface] = None,
    ):
        super().__init__(template_adapter)
        self.lambda_service = lambda_service or AwsLambdaService(
            region_name=settings.LAMBDA_CODE_GENERATOR_REGION
        )
        self.lambda_code_generator = getattr(
            settings,
            "LAMBDA_CODE_GENERATOR",
            "arn:aws:lambda:us-east-1:123456789012:function:mock",
        )

    def update_template(self, template: Template, payload: Dict[str, Any]) -> Template:
        if not template.metadata:
            raise ValueError("Template metadata is missing")

        category = template.metadata.get("category")

        if not category:
            raise ValueError("Missing category in template metadata")

        if "parameters" in payload:
            generated_code = self._generate_code(payload["parameters"])
            template.rule_code = generated_code

        updated_metadata = dict(template.metadata)
        updated_metadata["body"] = payload.get(
            "template_body", template.metadata.get("body")
        )
        updated_metadata["header"] = payload.get(
            "template_header", template.metadata.get("header")
        )
        updated_metadata["footer"] = payload.get(
            "template_footer", template.metadata.get("footer")
        )
        updated_metadata["buttons"] = payload.get(
            "template_button", template.metadata.get("buttons")
        )

        translation_payload = self._adapt_translation(updated_metadata)
        updated_metadata["buttons"] = translation_payload.get("buttons")

        if "parameters" in payload:
            start_condition = next(
                (
                    param.get("value")
                    for param in payload["parameters"]
                    if param.get("name") == "start_condition"
                ),
                template.start_condition,
            )
            template.start_condition = start_condition

        template.metadata = updated_metadata
        template.save(update_fields=["metadata", "rule_code", "start_condition"])

        version = self._create_version(
            template=template,
            app_uuid=payload["app_uuid"],
            project_uuid=payload["project_uuid"],
        )

        self._notify_integrations(
            version_name=version.template_name,
            version_uuid=version.uuid,
            translation_payload=copy.deepcopy(translation_payload),
            app_uuid=payload["app_uuid"],
            project_uuid=payload["project_uuid"],
            category=category,
        )

        return template

    def _generate_code(self, parameters: List[Dict[str, Any]]) -> str:
        """Generate code using Lambda service"""
        response_payload = self._invoke_code_generator(parameters)

        status_code = response_payload.get("statusCode")
        body = response_payload.get("body")

        if status_code is not None:
            match status_code:
                case LambdaResponseStatusCode.OK:
                    return body.get("generated_code", "")
                case LambdaResponseStatusCode.BAD_REQUEST:
                    raise CodeGeneratorBadRequest(detail=body)
                case LambdaResponseStatusCode.UNPROCESSABLE_ENTITY:
                    raise CodeGeneratorUnprocessableEntity(detail=body)

        raise CodeGeneratorInternalServerError(
            detail={"message": "Unknown error from lambda.", "error": response_payload}
        )

    def _invoke_code_generator(self, params: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Invoke Lambda code generator"""
        payload = {"parameters": params}

        response = self.lambda_service.invoke(
            function_name=self.lambda_code_generator, payload=payload
        )

        response_payload = json.loads(response["Payload"].read())
        return response_payload


class UpdateTemplateStrategyFactory:
    """Factory for creating appropriate update template strategies"""

    @staticmethod
    def create_strategy(
        template: Template,
        template_adapter: Optional[TemplateTranslationAdapter] = None,
        lambda_service: Optional[AwsLambdaServiceInterface] = None,
    ) -> UpdateTemplateStrategy:
        """
        Create the appropriate strategy based on template type.

        Args:
            template: Template instance to determine strategy
            template_adapter: Optional adapter for template translation
            lambda_service: Optional lambda service for custom templates

        Returns:
            UpdateTemplateStrategy: The appropriate strategy instance
        """
        if template.is_custom:
            return UpdateCustomTemplateStrategy(
                template_adapter=template_adapter,
                lambda_service=lambda_service,
            )
        else:
            return UpdateNormalTemplateStrategy(
                template_adapter=template_adapter,
            )
