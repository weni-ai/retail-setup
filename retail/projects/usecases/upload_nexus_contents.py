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
    compute_upload_percent,
    persist_content_base_progress,
)
from retail.services.nexus.service import NexusService

logger = logging.getLogger(__name__)


class FileUploadError(Exception):
    """Raised when a file upload to Nexus fails."""


BATCH_MAX_FILES = 25
BATCH_STATUS_POLL_INTERVAL = 3  # seconds between status checks
BATCH_STATUS_MAX_ATTEMPTS = 300  # ~15 minutes max wait per batch


class UploadNexusContentsUseCase:
    """
    Background-only upload of crawled content files to the Nexus
    content base via the inline batch direct-ingest API.

    Invoked by ``task_upload_nexus_contents`` when the crawl webhook
    arrives with ``crawl.completed``. Calls ``ensure_agent_manager_configured``
    first so the upload is safe to run even if the inline manager step
    (``ConfigureAgentBuilderUseCase``) has not yet completed -- e.g.
    the webhook arrived early.

    Partial ingestion failures within a batch are logged but do not
    abort the upload when at least one file succeeds (best-effort).

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
        Converts crawled content to .txt files and uploads them to Nexus
        in batches of up to 25 files.

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
        batches = _chunk_files(files, BATCH_MAX_FILES)
        uploaded_file_uuids: List[str] = []

        logger.info(
            f"Uploading {total} content files to Nexus for project={project_uuid} "
            f"in {len(batches)} batch(es)"
        )

        for batch_index, batch in enumerate(batches):
            response = self.nexus_service.upload_content_base_files_batch(
                project_uuid=project_uuid,
                files=batch,
            )

            if response is None:
                raise FileUploadError(
                    f"Failed to batch upload files to Nexus for project={project_uuid}"
                )

            uploaded_files = response.get("files") or []
            if not uploaded_files:
                raise FileUploadError(
                    f"No files were uploaded to Nexus for project={project_uuid}"
                )

            for error in response.get("errors") or []:
                logger.warning(
                    f"Batch upload error for project={project_uuid}: "
                    f"filename={error.get('filename')} message={error.get('message')}"
                )

            batch_file_uuids = [
                entry["uuid"] for entry in uploaded_files if entry.get("uuid")
            ]
            uploaded_file_uuids.extend(batch_file_uuids)

            logger.info(
                f"Batch {batch_index + 1}/{len(batches)} uploaded for "
                f"project={project_uuid}: file_uuids={batch_file_uuids}"
            )

            self._wait_for_batch_processing(
                onboarding,
                project_uuid,
                batch_file_uuids,
                batch_index=batch_index,
                batch_size=len(batch),
                total_files=total,
            )

        if not uploaded_file_uuids:
            raise FileUploadError(
                f"No file UUIDs returned from Nexus for project={project_uuid}"
            )

        persist_content_base_progress(
            onboarding,
            upload_percent=100,
            status=STATUS_COMPLETE,
        )
        logger.info(
            f"Content base upload completed for project={project_uuid} "
            f"({len(uploaded_file_uuids)} files uploaded)"
        )

    def _wait_for_batch_processing(
        self,
        onboarding: ProjectOnboarding,
        project_uuid: str,
        file_uuids: List[str],
        *,
        batch_index: int,
        batch_size: int,
        total_files: int,
    ) -> int:
        """
        Polls Nexus until the batch reaches a terminal state.

        Persists ``upload_percent`` on every successful poll so clients
        see real-time progress. Returns the final ``progress_percentage``
        from Nexus. Partial and failed batches are logged but do not raise.
        """
        for attempt in range(1, BATCH_STATUS_MAX_ATTEMPTS + 1):
            time.sleep(BATCH_STATUS_POLL_INTERVAL)

            progress_response = self.nexus_service.get_content_base_batch_progress(
                project_uuid, file_uuids
            )

            if progress_response is None:
                logger.warning(
                    f"Could not fetch batch progress for project={project_uuid} "
                    f"batch={batch_index + 1} "
                    f"(attempt {attempt}/{BATCH_STATUS_MAX_ATTEMPTS})"
                )
                continue

            status = progress_response.get("status", "").lower()
            progress_pct = progress_response.get("progress_percentage", 0)
            is_complete = progress_response.get("is_complete", False)

            upload_percent = compute_upload_percent(
                batch_index, batch_size, total_files, progress_pct
            )
            persist_content_base_progress(
                onboarding,
                upload_percent=upload_percent,
                status=STATUS_UPLOADING,
            )

            logger.info(
                f"Batch {batch_index + 1} progress for project={project_uuid}: "
                f"status={status} progress={progress_pct}% "
                f"upload_percent={upload_percent}% "
                f"(attempt {attempt}/{BATCH_STATUS_MAX_ATTEMPTS})"
            )

            if not is_complete:
                continue

            if status == "partial":
                failed_files = progress_response.get("failed_files") or []
                logger.warning(
                    f"Batch {batch_index + 1} completed with partial failures "
                    f"for project={project_uuid}: failed_files={failed_files}"
                )
            elif status == "failed":
                logger.error(
                    f"Batch {batch_index + 1} ingestion failed for "
                    f"project={project_uuid}: file_uuids={file_uuids}"
                )

            return progress_pct

        logger.error(
            f"Timed out waiting for batch {batch_index + 1} "
            f"project={project_uuid} after {BATCH_STATUS_MAX_ATTEMPTS} attempts"
        )
        return 0

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


def _chunk_files(
    files: List[Tuple[str, bytes, str]], chunk_size: int
) -> List[List[Tuple[str, bytes, str]]]:
    return [files[i : i + chunk_size] for i in range(0, len(files), chunk_size)]  # noqa: E203


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
