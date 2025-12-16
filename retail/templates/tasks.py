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
    from retail.templates.usecases.update_template import UpdateTemplateUseCase

    try:
        integrations_service = IntegrationsService()

        logger.info(
            f"[task_create_template] Starting template creation: {template_name} "
            f"app={app_uuid} version={version_uuid}"
        )

        template_uuid = integrations_service.create_template(
            app_uuid=app_uuid,
            project_uuid=project_uuid,
            name=template_name,
            category=category,
            gallery_version=version_uuid,
        )

        logger.info(
            f"[task_create_template] Template created successfully: {template_name} "
            f"template_uuid={template_uuid} - now creating translation..."
        )

        integrations_service.create_template_translation(
            app_uuid=app_uuid,
            project_uuid=project_uuid,
            template_uuid=template_uuid,
            payload=template_translation,
        )

        logger.info(
            f"[task_create_template] Translation created successfully: {template_name} "
            f"template_uuid={template_uuid} version={version_uuid}"
        )
    except Exception as e:
        logger.error(
            f"Error creating template: {template_name} for App: {app_uuid} - {category} - version: {version_uuid}\n"
            f"Error: {e}\n"
            f"Traceback: {traceback.format_exc()}\n"
            f"Translation payload: {template_translation}"
        )
        payload = {"version_uuid": version_uuid, "status": "REJECTED"}
        update_template_use_case = UpdateTemplateUseCase()
        update_template_use_case.execute(payload=payload)
        logger.info(
            f"Template {template_name}, Version {version_uuid} has been marked as REJECTED."
        )


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
    from retail.templates.usecases.update_template import UpdateTemplateUseCase

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
        payload = {"version_uuid": gallery_version, "status": "REJECTED"}
        update_template_use_case = UpdateTemplateUseCase()
        update_template_use_case.execute(payload=payload)
        logger.info(
            f"Library Template {library_template_name}, Version {gallery_version} has been marked as REJECTED."
        )
