import logging
import re

from typing import List, Tuple

from retail.clients.nexus.client import NexusClient
from retail.interfaces.clients.nexus.client import NexusClientInterface
from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.manager_defaults import (
    MANAGER_PERSONALITY,
    get_manager_defaults,
)
from retail.services.nexus.service import NexusService

logger = logging.getLogger(__name__)


class ProjectNotLinkedError(Exception):
    """Raised when Agent Builder configuration is attempted without a linked project."""


MAX_UPLOAD_PROGRESS = 80


class ConfigureAgentBuilderUseCase:
    """
    Configures the Nexus Agent Builder for a project.

    Steps executed in order:
      1. Check if the agent manager attributes are already set.
      2. If not, set them (name, goal, role, personality) using the
         project language for translation.
      3. Upload crawled content files to the Nexus content base.

    Progress is tracked from 0% to 80% of the NEXUS_CONFIG step —
    the remaining percentage is reserved for the WWC channel setup
    that follows.
    """

    def __init__(
        self,
        nexus_client: NexusClientInterface = None,
    ):
        self.nexus_service = NexusService(nexus_client=nexus_client or NexusClient())

    def execute(self, vtex_account: str, contents: list) -> None:
        """
        Full Nexus configuration flow: set agent attributes then upload files.

        Args:
            vtex_account: The VTEX account identifier for the onboarding.
            contents: List of dicts with 'link', 'title', and 'content' keys.

        Raises:
            ProjectNotLinkedError: If the onboarding has no project linked.
        """
        onboarding = ProjectOnboarding.objects.select_related("project").get(
            vtex_account=vtex_account
        )

        if onboarding.project is None:
            raise ProjectNotLinkedError(
                f"Onboarding {onboarding.uuid} has no project linked yet."
            )

        project_uuid = str(onboarding.project.uuid)
        language = onboarding.project.language or ""

        onboarding.current_step = "NEXUS_CONFIG"
        onboarding.progress = 0
        onboarding.save(update_fields=["current_step", "progress"])

        self._ensure_agent_configured(project_uuid, vtex_account, language)
        self._upload_contents(onboarding, project_uuid, contents)

    def _ensure_agent_configured(
        self, project_uuid: str, vtex_account: str, language: str
    ) -> None:
        """
        Checks whether the agent manager is already configured; if not,
        sends the translated attributes to Nexus.
        """
        response = self.nexus_service.check_agent_builder_exists(project_uuid)

        if response and response.get("data", {}).get("has_agent"):
            logger.info(f"Agent manager already configured for project={project_uuid}")
            return

        defaults = get_manager_defaults(language)

        payload = {
            "agent": {
                "name": f"{vtex_account.title()} Manager",
                "goal": defaults["goal"],
                "role": defaults["role"],
                "personality": MANAGER_PERSONALITY,
            },
            "links": [],
        }

        result = self.nexus_service.configure_agent_attributes(project_uuid, payload)

        if result is not None:
            logger.info(
                f"Agent manager attributes set for project={project_uuid}: {result}"
            )
        else:
            logger.error(
                f"Failed to set agent manager attributes for project={project_uuid}"
            )

    def _upload_contents(
        self,
        onboarding: ProjectOnboarding,
        project_uuid: str,
        contents: list,
    ) -> None:
        """
        Converts crawled content to .txt files and uploads them to Nexus.
        Updates progress proportionally from 0% to MAX_UPLOAD_PROGRESS.
        """
        if not contents:
            logger.warning(
                f"No contents found in crawl result for onboarding={onboarding.uuid}"
            )
            onboarding.progress = MAX_UPLOAD_PROGRESS
            onboarding.save(update_fields=["progress"])
            return

        files = self._build_files_from_contents(contents)
        total = len(files)

        logger.info(
            f"Uploading {total} content files to Nexus for project={project_uuid}"
        )

        for index, (filename, file_bytes, content_type) in enumerate(files):
            response = self.nexus_service.upload_content_base_file(
                project_uuid=project_uuid,
                file=(filename, file_bytes, content_type),
            )

            if response is not None:
                logger.info(f"Uploaded {filename} to Nexus for project={project_uuid}")
            else:
                logger.error(
                    f"Failed to upload {filename} to Nexus for project={project_uuid}"
                )

            onboarding.progress = int(((index + 1) / total) * MAX_UPLOAD_PROGRESS)
            onboarding.save(update_fields=["progress"])

        logger.info(
            f"Content base upload completed for project={project_uuid} "
            f"({total} files uploaded, progress={onboarding.progress}%)"
        )

    @staticmethod
    def _build_files_from_contents(
        contents: list,
    ) -> List[Tuple[str, bytes, str]]:
        """
        Converts a list of crawled page contents into in-memory .txt files.

        Each file contains the scraped content for a single page.

        Args:
            contents: List of dicts with 'link', 'title', and 'content' keys.

        Returns:
            List of tuples (filename, file_bytes, content_type).
        """
        files = []

        for index, item in enumerate(contents):
            title = item.get("title", f"page_{index}")
            content = item.get("content", "")

            file_bytes = content.encode("utf-8")

            filename = _sanitize_filename(title, index)
            files.append((filename, file_bytes, "text/plain"))

        return files


def _sanitize_filename(title: str, index: int) -> str:
    """
    Generates a safe filename from a page title.

    Removes special characters, limits length, and appends the index
    to guarantee uniqueness.

    Args:
        title: The page title to convert into a filename.
        index: Numeric index for uniqueness.

    Returns:
        A sanitized .txt filename.
    """
    name = re.sub(r"[^\w\s-]", "", title).strip()
    name = re.sub(r"[\s]+", "_", name)
    name = name[:80] if name else "page"
    return f"{index:03d}_{name}.txt"
