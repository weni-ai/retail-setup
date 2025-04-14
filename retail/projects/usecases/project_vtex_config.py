from retail.projects.models import Project
from retail.projects.usecases.project_dto import ProjectVtexConfigDTO

from typing import Optional

import logging

logger = logging.getLogger(__name__)


class ProjectVtexConfigUseCase:
    @staticmethod
    def _get_project(project_uuid: str) -> Optional[Project]:
        try:
            return Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            return None

    @staticmethod
    def config_vtex_project(project_uuid: str, data: ProjectVtexConfigDTO) -> None:
        project = ProjectVtexConfigUseCase._get_project(project_uuid)

        if project is None:
            logger.info(f"Project {project_uuid} not found, skipping config")
            return

        project.vtex_account = data.account
        project.config["store_type"] = data.store_type
        project.save()
        logger.info("VTEX project configured successfully")
