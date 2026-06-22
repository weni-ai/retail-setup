import logging
import re
import time
import unicodedata

from typing import List, Tuple

from retail.clients.nexus.client import NexusClient
from retail.interfaces.clients.nexus.client import NexusClientInterface
from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.agent_builder_helpers import (
    ensure_agent_manager_configured,
    load_onboarding_with_linked_project,
)
from retail.projects.usecases.content_base_progress_helpers import (
    STATUS_COMPLETE,
    STATUS_UPLOADING,
    persist_content_base_progress,
)
from retail.services.nexus.service import NexusService

logger = logging.getLogger(__name__)


class FileProcessingError(Exception):
    """Raised when Nexus reports a file processing failure."""


class FileUploadError(Exception):
    """Raised when a file upload to Nexus fails."""


FILE_STATUS_POLL_INTERVAL = 3  # seconds between status checks
FILE_STATUS_MAX_ATTEMPTS = 60  # ~3 minutes max wait per file


class UploadNexusContentsUseCase:
    """
    Background-only upload of crawled content files to the Nexus
    content base.

    Invoked by ``task_upload_nexus_contents`` when the crawl webhook
    arrives with ``crawl.completed``. Calls ``ensure_agent_manager_configured``
    first so the upload is safe to run even if the inline manager step
    (``ConfigureAgentBuilderUseCase``) has not yet completed -- e.g.
    the webhook arrived early.

    Background path: does NOT touch ``onboarding.progress`` -- the main
    wizard is decoupled from the crawl outcome.
    """

    def __init__(
        self,
        nexus_client: NexusClientInterface = None,
    ):
        self.nexus_service = NexusService(nexus_client=nexus_client or NexusClient())

    def execute(self, vtex_account: str, contents: list) -> None:
        """
        Args:
            vtex_account: The VTEX account identifier for the onboarding.
            contents: List of dicts with 'link', 'title', and 'content' keys.

        Raises:
            ProjectNotLinkedError: If the onboarding has no project linked.
        """
        onboarding = load_onboarding_with_linked_project(vtex_account)
        project_uuid = str(onboarding.project.uuid)
        language = onboarding.project.language or ""

        ensure_agent_manager_configured(
            project_uuid, vtex_account, language, self.nexus_service
        )
        self._upload_contents(onboarding, project_uuid, contents)

    def _upload_contents(
        self,
        onboarding: ProjectOnboarding,
        project_uuid: str,
        contents: list,
    ) -> None:
        """
        Converts crawled content to .txt files and uploads them to Nexus.

        Background-only: does NOT update ``onboarding.progress``. The
        ``onboarding`` argument is kept for log context.
        """
        if not contents:
            logger.warning(
                f"No contents found in crawl result for onboarding={onboarding.uuid}"
            )
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
                raise FileUploadError(
                    f"Failed to upload {filename} to Nexus for project={project_uuid}"
                )

            file_uuid = response.get("uuid")
            logger.info(
                f"Uploaded {filename} to Nexus for project={project_uuid}: "
                f"file_uuid={file_uuid}, response={response}"
            )

            if file_uuid:
                self._wait_for_processing(project_uuid, file_uuid, filename)

            upload_percent = round((index + 1) / total * 100)
            persist_content_base_progress(
                onboarding,
                upload_percent=upload_percent,
                status=STATUS_UPLOADING,
            )

        persist_content_base_progress(
            onboarding,
            upload_percent=100,
            status=STATUS_COMPLETE,
        )
        logger.info(
            f"Content base upload completed for project={project_uuid} "
            f"({total} files uploaded)"
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
            title = item.get("title") or f"page_{index}"
            content = item.get("content") or ""

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
