import logging

from celery import shared_task

from retail.templates.services.integrations import IntegrationsService


logger = logging.getLogger(__name__)


@shared_task
def task_create_template(
    template_name: str,
    app_uuid: str,
    project_uuid: str,
    category: str,
    version_uuid: str,
    template_translation: dict,
):
    try:
        integrations_service = IntegrationsService()

        template_uuid = integrations_service.create_template(
            app_uuid=app_uuid,
            project_uuid=project_uuid,
            name=template_name,
            category=category,
            gallery_version=version_uuid,
        )
        integrations_service.create_template_translation(
            app_uuid=app_uuid,
            project_uuid=project_uuid,
            template_uuid=template_uuid,
            payload=template_translation,
        )
        logger.info(
            f"Template created: {template_name} for App: {app_uuid} - {category} - version: {version_uuid}"
        )
    except Exception as e:
        logger.error(
            f"Error creating template: {template_name} for App: {app_uuid} - {category} - version: {version_uuid} {e}"
        )
