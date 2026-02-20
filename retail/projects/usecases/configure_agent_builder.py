import logging
import re

from typing import List, Tuple

from retail.clients.nexus.client import NexusClient
from retail.interfaces.clients.nexus.client import NexusClientInterface
from retail.projects.models import ProjectOnboarding
from retail.services.nexus.service import NexusService

logger = logging.getLogger(__name__)


class ProjectNotLinkedError(Exception):
    """Raised when Agent Builder configuration is attempted without a linked project."""


MAX_UPLOAD_PROGRESS = 80  # File uploads occupy 0-80% of NEXUS_CONFIG


class ConfigureAgentBuilderUseCase:
    """
    Uploads crawled page contents to the Nexus content base.

    Converts each page into a .txt file and uploads it via the
    inline-content-base-file API.  Progress is tracked from 0% to 80%
    of the NEXUS_CONFIG step — the remaining 20% is reserved for the
    WWC channel creation that follows.
    """

    def __init__(
        self,
        nexus_client: NexusClientInterface = None,
    ):
        self.nexus_service = NexusService(nexus_client=nexus_client or NexusClient())

    def execute(self, vtex_account: str, contents: list) -> None:
        """
        Converts crawled contents into text files and uploads each one
        to the Nexus content base for the linked project.

        Updates NEXUS_CONFIG progress proportionally from 0% to 80%.

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

        onboarding.current_step = "NEXUS_CONFIG"
        onboarding.progress = 0
        onboarding.save(update_fields=["current_step", "progress"])

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

        Each file contains the page title, link, and the scraped content.

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
