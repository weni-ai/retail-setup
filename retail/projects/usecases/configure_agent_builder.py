import logging
import re
import time
import unicodedata

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


class FileProcessingError(Exception):
    """Raised when Nexus reports a file processing failure."""


CHANNEL_PROGRESS_OFFSET = 10
MAX_UPLOAD_PROGRESS = 75

FILE_STATUS_POLL_INTERVAL = 3  # seconds between status checks
FILE_STATUS_MAX_ATTEMPTS = 60  # ~3 minutes max wait per file


class ConfigureAgentBuilderUseCase:
    """
    Configures the Nexus Agent Builder for a project.

    Steps executed in order:
      1. Check if the agent manager attributes are already set.
      2. If not, set them (name, goal, role, personality) using the
         project language for translation.
      3. Upload crawled content files to the Nexus content base.

    Progress is tracked from 10% (after channel) to 75%.
    Agent integration (75-100%) follows as a separate step.
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
        Updates progress proportionally from CHANNEL_PROGRESS_OFFSET to MAX_UPLOAD_PROGRESS.
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

            if response is None:
                logger.error(
                    f"Failed to upload {filename} to Nexus for project={project_uuid}"
                )
            else:
                file_uuid = response.get("uuid")
                logger.info(
                    f"Uploaded {filename} to Nexus for project={project_uuid}: "
                    f"file_uuid={file_uuid}, response={response}"
                )

                if file_uuid:
                    self._wait_for_processing(project_uuid, file_uuid, filename)

            upload_range = MAX_UPLOAD_PROGRESS - CHANNEL_PROGRESS_OFFSET
            onboarding.progress = CHANNEL_PROGRESS_OFFSET + int(
                ((index + 1) / total) * upload_range
            )
            onboarding.save(update_fields=["progress"])

        logger.info(
            f"Content base upload completed for project={project_uuid} "
            f"({total} files uploaded, progress={onboarding.progress}%)"
        )

    def _wait_for_processing(
        self, project_uuid: str, file_uuid: str, filename: str
    ) -> None:
        """
        Polls Nexus until the uploaded file reaches a terminal status
        (``success`` or ``failed``) before allowing the next upload.
        """
        for attempt in range(1, FILE_STATUS_MAX_ATTEMPTS + 1):
            time.sleep(FILE_STATUS_POLL_INTERVAL)

            status_response = self.nexus_service.get_content_base_file_status(
                project_uuid, file_uuid
            )

            if status_response is None:
                logger.warning(
                    f"Could not fetch status for file_uuid={file_uuid} "
                    f"(attempt {attempt}/{FILE_STATUS_MAX_ATTEMPTS})"
                )
                continue

            status = status_response.get("status", "").lower()

            logger.info(
                f"File {filename} (uuid={file_uuid}) status={status} "
                f"(attempt {attempt}/{FILE_STATUS_MAX_ATTEMPTS})"
            )

            if status == "success":
                return

            if status == "failed":
                raise FileProcessingError(
                    f"Nexus reported processing failure for "
                    f"file_uuid={file_uuid} ({filename})"
                )

        logger.error(
            f"Timed out waiting for file_uuid={file_uuid} ({filename}) "
            f"after {FILE_STATUS_MAX_ATTEMPTS} attempts"
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

    Strips accents via NFKD normalization, removes special characters,
    limits length, and appends the index to guarantee uniqueness.

    Args:
        title: The page title to convert into a filename.
        index: Numeric index for uniqueness.

    Returns:
        A sanitized .txt filename.
    """
    normalized = unicodedata.normalize("NFKD", title)
    ascii_title = normalized.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^\w\s-]", "", ascii_title).strip().lower()
    name = re.sub(r"[\s_]+", "-", name)
    name = name[:80] if name else "page"
    return f"{index:03d}_{name}.txt"
