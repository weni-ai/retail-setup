import logging
import traceback

from celery import shared_task

from retail.services.integrations.service import IntegrationsService

from typing import Optional, List, Dict, Any


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
        # TODO: on exception, delete the template on integrations


@shared_task
def task_create_library_template(
    name: str,
    app_uuid: str,
    project_uuid: str,
    category: str,
    language: str,
    library_template_name: str,
    gallery_version: str,
    library_template_button_inputs: Optional[List[Dict[str, Any]]] = None,
):
    payload = {
        "library_template_name": library_template_name,
        "name": name,
        "language": language,
        "category": category,
        "gallery_version": gallery_version,
    }
    if library_template_button_inputs:
        payload["library_template_button_inputs"] = library_template_button_inputs

    try:
        integrations_service = IntegrationsService()
        integrations_service.create_library_template(
            app_uuid=app_uuid,
            project_uuid=project_uuid,
            template_data=payload,
        )
    except Exception as e:
        logger.error(
            f"Error creating library template: {library_template_name} "
            f"for App: {app_uuid} - {category} - version: {gallery_version} {e}"
            f"Error: {traceback.format_exc()}"
        )
