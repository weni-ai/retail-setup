import logging

from typing import List, Optional, Dict


from retail.services.integrations.service import IntegrationsService
from retail.templates.models import Template, Version


logger = logging.getLogger(__name__)


class FetchTemplateMetricsUseCase:
    """
    Use case to fetch template metrics from the integrations service.
    """

    def __init__(self, service: Optional[IntegrationsService] = None):
        self.service = service or IntegrationsService()

    def execute(self, template_uuid: str, start: str, end: str) -> Dict:
        """
        Execute the use case to fetch metrics for a template and its versions.

        Args:
            template_uuid (str): UUID of the template
            start (str): Start date in YYYY-MM-DD format
            end (str): End date in YYYY-MM-DD format

        Returns:
            Dict: Response from the integrations client with metrics

        Raises:
            ValueError: If template, versions or integration app UUID are invalid
        """
        template = self._get_template_with_versions(template_uuid)
        version_uuids = self._get_version_uuids(template)
        app_uuid = self._get_integrations_app_uuid(template)

        return self.service.fetch_template_metrics(
            app_uuid=app_uuid,
            template_versions=version_uuids,
            start=start,
            end=end,
        )

    def _get_template_with_versions(self, template_uuid: str) -> Template:
        """
        Retrieve the template and its related versions.

        Raises:
            ValueError: If the template is not found or has no versions
        """
        try:
            template = Template.objects.prefetch_related("versions").get(
                uuid=template_uuid
            )
        except Template.DoesNotExist:
            logger.error(f"Template not found: {template_uuid}")
            raise ValueError("Template not found.")

        if not template.versions.exists():
            logger.error(f"No versions found for template: {template_uuid}")
            raise ValueError("No versions found for this template.")

        return template

    def _get_version_uuids(self, template: Template) -> List[str]:
        """
        Extract UUIDs from the template's versions.

        Returns:
            List[str]: List of version UUIDs as strings
        """
        return [str(version.uuid) for version in template.versions.all()]

    def _get_integrations_app_uuid(self, template: Template) -> str:
        """
        Retrieve the integrations app UUID from the first version.

        Raises:
            ValueError: If the integration app UUID is missing
        """
        first_version: Optional[Version] = template.versions.first()

        if not first_version or not first_version.integrations_app_uuid:
            logger.error(
                f"Missing integrations app UUID in first version for template: {template.uuid}"
            )
            raise ValueError("Integrations app UUID is missing in the first version.")

        return str(first_version.integrations_app_uuid)
