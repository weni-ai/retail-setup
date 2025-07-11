from retail.templates.models import Template

from retail.templates.usecases import TemplateBuilderMixin
from retail.templates.usecases import LibraryTemplateData, BaseLibraryTemplateUseCase


class CreateLibraryTemplateUseCase(TemplateBuilderMixin, BaseLibraryTemplateUseCase):
    """
    Use case responsible for creating a library template and its version.

    This class handles the creation of a library-based Meta template, including versioning,
    and delegates the integration trigger to an asynchronous task.
    """

    def execute(self, payload: LibraryTemplateData) -> Template:
        """
        Executes the library template creation flow.

        This method will:
        - Retrieve or create the base Template.
        - Create a new Version associated with the template.

        Args:
            payload (CreateLibraryTemplateData): The data required to create the library template.

        Returns:
            Template: The created or existing Template instance.
        """
        payload["template_name"] = payload["library_template_name"]
        template, version = self.build_template_and_version(
            payload, integrated_agent=payload.pop("integrated_agent", None)
        )
        return template, version
