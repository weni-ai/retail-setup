from typing import Optional, TypedDict, List, Dict, Any
from uuid import UUID

from retail.templates.models import Template
from retail.templates.tasks import task_create_library_template

from ._base_template_creator import TemplateBuilderMixin


class CreateLibraryTemplateData(TypedDict):
    template_name: str
    library_template_name: str
    category: str
    language: str
    app_uuid: str
    project_uuid: str
    start_condition: str
    library_template_button_inputs: Optional[List[Dict[str, Any]]] = None


class CreateLibraryTemplateUseCase(TemplateBuilderMixin):
    """
    Use case responsible for creating a library template and its version.

    This class handles the creation of a library-based Meta template, including versioning,
    and delegates the integration trigger to an asynchronous task.
    """

    def _notify_integrations(
        self, version_name: str, version_uuid: UUID, payload: CreateLibraryTemplateData
    ) -> None:
        """
        Notifies the integration layer to asynchronously create the library template.

        Args:
            version_name (str): The generated name of the template version.
            version_uuid (UUID): UUID of the created version, used as gallery_version.
            payload (CreateLibraryTemplateData): All template data required for the integration.

        Raises:
            ValueError: If required fields for integration are missing.
        """
        if (
            not version_name
            or not payload.get("app_uuid")
            or not payload.get("project_uuid")
            or not version_uuid
        ):
            raise ValueError("Missing required data to notify integrations")

        task_create_library_template.delay(
            name=version_name,
            app_uuid=payload["app_uuid"],
            project_uuid=payload["project_uuid"],
            category=payload["category"],
            language=payload["language"],
            library_template_name=payload["library_template_name"],
            gallery_version=str(version_uuid),
            library_template_button_inputs=payload.get(
                "library_template_button_inputs"
            ),
        )

    def execute(self, payload: CreateLibraryTemplateData) -> Template:
        """
        Executes the library template creation flow.

        This method will:
        - Retrieve or create the base Template.
        - Create a new Version associated with the template.
        - Trigger the asynchronous task to notify Meta integrations.

        Args:
            payload (CreateLibraryTemplateData): The data required to create the library template.

        Returns:
            Template: The created or existing Template instance.
        """
        payload["template_name"] = payload["library_template_name"]
        template, version = self.build_template_and_version(payload)
        self._notify_integrations(version.template_name, version.uuid, payload)
        return template
