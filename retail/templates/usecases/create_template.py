from typing import TypedDict, Dict, Any
from uuid import UUID

from retail.templates.models import Template
from retail.templates.tasks import task_create_template

from ._base_template_creator import TemplateBuilderMixin


class CreateTemplateData(TypedDict):
    template_translation: Dict[str, Any]
    template_name: str
    start_condition: str
    category: str
    app_uuid: str
    project_uuid: str


class CreateTemplateUseCase(TemplateBuilderMixin):
    """
    Use case responsible for creating a Meta template and its version.

    This class handles the logic of checking whether a template already exists,
    creating one if necessary, creating a new version, and notifying the
    asynchronous integration process.
    """

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
