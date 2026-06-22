from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.agent_builder_helpers import ProjectNotLinkedError
from retail.projects.usecases.upload_nexus_contents import (
    BATCH_MAX_FILES,
    FileUploadError,
    UploadNexusContentsUseCase,
    _sanitize_filename,
)


def _batch_upload_response(*file_uuids):
    return {
        "files": [
            {"uuid": uuid, "extension_file": "txt", "filename": f"file-{i}.txt"}
            for i, uuid in enumerate(file_uuids)
        ]
    }


def _batch_progress_response(
    *,
    is_complete=True,
    status="success",
    progress_percentage=100,
    failed_files=None,
):
    return {
        "total": 1,
        "completed": 1 if status == "success" else 0,
        "failed": 0,
        "remaining": 0 if is_complete else 1,
        "progress_percentage": progress_percentage,
        "is_complete": is_complete,
        "status": status,
        "failed_files": failed_files or [],
    }


class TestUploadNexusContentsUseCase(TestCase):
    """Background path triggered by the crawl.completed webhook."""

    def setUp(self):
        self.project = Project.objects.create(
            name="Test Project",
            uuid=uuid4(),
            vtex_account="mystore",
            language="pt-br",
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            current_step="NEXUS_CONFIG",
            progress=100,
        )
        self.mock_nexus_service = MagicMock()
        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": True}
        }
        self.usecase = UploadNexusContentsUseCase(nexus_client=MagicMock())
        self.usecase.nexus_service = self.mock_nexus_service

    def test_raises_error_when_project_not_linked(self):
        ProjectOnboarding.objects.create(vtex_account="noproject")

        with self.assertRaises(ProjectNotLinkedError):
            self.usecase.execute("noproject", [])

    def test_does_not_touch_progress_when_contents_empty(self):
        self.usecase.execute("mystore", [])

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.progress, 100)
        self.mock_nexus_service.upload_content_base_files_batch.assert_not_called()

    def test_ensures_agent_configured_before_upload(self):
        """
        Background-only entrypoint: if the inline manager step has not
        yet completed (e.g. webhook arrived early), the upload path must
        configure the manager itself idempotently.
        """
        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": False}
        }
        self.mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        self.usecase.execute("mystore", [])

        self.mock_nexus_service.check_agent_builder_exists.assert_called_once_with(
            str(self.project.uuid)
        )
        self.mock_nexus_service.configure_agent_attributes.assert_called_once()

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_uploads_files_in_single_batch(self, _mock_sleep):
        uuid_1, uuid_2 = str(uuid4()), str(uuid4())
        self.mock_nexus_service.upload_content_base_files_batch.return_value = (
            _batch_upload_response(uuid_1, uuid_2)
        )
        self.mock_nexus_service.get_content_base_batch_progress.return_value = (
            _batch_progress_response()
        )

        contents = [
            {
                "link": "https://www.mystore.com.br/",
                "title": "Home Page",
                "content": "Welcome to our store.",
            },
            {
                "link": "https://www.mystore.com.br/about",
                "title": "About Us",
                "content": "We sell great products.",
            },
        ]

        self.usecase.execute("mystore", contents)

        self.mock_nexus_service.upload_content_base_files_batch.assert_called_once()
        self.mock_nexus_service.get_content_base_batch_progress.assert_called_once()

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_file_contains_only_content(self, _mock_sleep):
        upload_uuid = str(uuid4())
        self.mock_nexus_service.upload_content_base_files_batch.return_value = (
            _batch_upload_response(upload_uuid)
        )
        self.mock_nexus_service.get_content_base_batch_progress.return_value = (
            _batch_progress_response()
        )

        contents = [
            {
                "link": "https://example.com/page",
                "title": "Test Page",
                "content": "Some content here.",
            }
        ]

        self.usecase.execute("mystore", contents)

        call_kwargs = self.mock_nexus_service.upload_content_base_files_batch.call_args[
            1
        ]
        batch_files = call_kwargs["files"]
        _, file_bytes, _ = batch_files[0]

        text = file_bytes.decode("utf-8")
        self.assertEqual(text, "Some content here.")
        self.assertNotIn("Title:", text)
        self.assertNotIn("Source:", text)

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_does_not_update_progress(self, _mock_sleep):
        """Background path must never touch ``onboarding.progress``."""
        upload_uuid = str(uuid4())
        self.mock_nexus_service.upload_content_base_files_batch.return_value = (
            _batch_upload_response(upload_uuid, str(uuid4()))
        )
        self.mock_nexus_service.get_content_base_batch_progress.return_value = (
            _batch_progress_response()
        )

        contents = [
            {"link": "https://a.com", "title": "A", "content": "a"},
            {"link": "https://b.com", "title": "B", "content": "b"},
        ]

        self.usecase.execute("mystore", contents)

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.progress, 100)
        snapshot = self.onboarding.config["content_base_progress"]
        self.assertEqual(snapshot["upload_percent"], 100)
        self.assertEqual(snapshot["status"], "complete")

    def test_stops_on_upload_failure(self):
        self.mock_nexus_service.upload_content_base_files_batch.return_value = None

        contents = [
            {"link": "https://a.com", "title": "A", "content": "a"},
            {"link": "https://b.com", "title": "B", "content": "b"},
        ]

        with self.assertRaises(FileUploadError):
            self.usecase.execute("mystore", contents)

        self.mock_nexus_service.upload_content_base_files_batch.assert_called_once()

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_passes_project_uuid_to_nexus(self, _mock_sleep):
        upload_uuid = str(uuid4())
        self.mock_nexus_service.upload_content_base_files_batch.return_value = (
            _batch_upload_response(upload_uuid)
        )
        self.mock_nexus_service.get_content_base_batch_progress.return_value = (
            _batch_progress_response()
        )

        contents = [
            {"link": "https://a.com", "title": "A", "content": "a"},
        ]

        self.usecase.execute("mystore", contents)

        call_kwargs = self.mock_nexus_service.upload_content_base_files_batch.call_args[
            1
        ]
        self.assertEqual(call_kwargs["project_uuid"], str(self.project.uuid))

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_waits_for_batch_processing_before_next_batch(self, _mock_sleep):
        """Ensures polling occurs until the batch is complete."""
        uuid_1, uuid_2 = str(uuid4()), str(uuid4())
        self.mock_nexus_service.upload_content_base_files_batch.side_effect = [
            _batch_upload_response(uuid_1),
            _batch_upload_response(uuid_2),
        ]
        self.mock_nexus_service.get_content_base_batch_progress.side_effect = [
            _batch_progress_response(
                is_complete=False, status="processing", progress_percentage=0
            ),
            _batch_progress_response(),
            _batch_progress_response(),
        ]

        contents = [
            {"link": f"https://a{i}.com", "title": f"A{i}", "content": f"a{i}"}
            for i in range(BATCH_MAX_FILES + 1)
        ]

        self.usecase.execute("mystore", contents)

        self.assertEqual(
            self.mock_nexus_service.upload_content_base_files_batch.call_count, 2
        )
        self.assertEqual(
            self.mock_nexus_service.get_content_base_batch_progress.call_count, 3
        )

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_retries_status_poll_when_status_unavailable(self, _mock_sleep):
        """A transient ``None`` progress response must not abort polling."""
        upload_uuid = str(uuid4())
        self.mock_nexus_service.upload_content_base_files_batch.return_value = (
            _batch_upload_response(upload_uuid)
        )
        self.mock_nexus_service.get_content_base_batch_progress.side_effect = [
            None,
            _batch_progress_response(),
        ]

        contents = [{"link": "https://a.com", "title": "A", "content": "a"}]

        self.usecase.execute("mystore", contents)

        self.assertEqual(
            self.mock_nexus_service.get_content_base_batch_progress.call_count, 2
        )

    @patch(
        "retail.projects.usecases.upload_nexus_contents.BATCH_STATUS_MAX_ATTEMPTS", 2
    )
    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_gives_up_after_max_attempts_without_terminal_status(self, _mock_sleep):
        """Polling stops (without raising) once the attempt budget runs out."""
        upload_uuid = str(uuid4())
        self.mock_nexus_service.upload_content_base_files_batch.return_value = (
            _batch_upload_response(upload_uuid)
        )
        self.mock_nexus_service.get_content_base_batch_progress.return_value = (
            _batch_progress_response(
                is_complete=False, status="processing", progress_percentage=0
            )
        )

        contents = [{"link": "https://a.com", "title": "A", "content": "a"}]

        self.usecase.execute("mystore", contents)

        self.assertEqual(
            self.mock_nexus_service.get_content_base_batch_progress.call_count, 2
        )

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_does_not_raise_on_processing_failure(self, _mock_sleep):
        """Best-effort: a failed batch is logged but does not abort the upload."""
        upload_uuid = str(uuid4())
        self.mock_nexus_service.upload_content_base_files_batch.return_value = (
            _batch_upload_response(upload_uuid)
        )
        self.mock_nexus_service.get_content_base_batch_progress.return_value = (
            _batch_progress_response(status="failed", progress_percentage=0)
        )

        contents = [
            {"link": "https://a.com", "title": "A", "content": "a"},
        ]

        self.usecase.execute("mystore", contents)

        self.onboarding.refresh_from_db()
        snapshot = self.onboarding.config["content_base_progress"]
        self.assertEqual(snapshot["status"], "complete")

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_logs_partial_batch_failures_without_raising(self, _mock_sleep):
        upload_uuid = str(uuid4())
        self.mock_nexus_service.upload_content_base_files_batch.return_value = (
            _batch_upload_response(upload_uuid)
        )
        self.mock_nexus_service.get_content_base_batch_progress.return_value = (
            _batch_progress_response(
                status="partial",
                progress_percentage=50,
                failed_files=[{"uuid": upload_uuid, "filename": "a.txt"}],
            )
        )

        contents = [{"link": "https://a.com", "title": "A", "content": "a"}]

        self.usecase.execute("mystore", contents)

        self.onboarding.refresh_from_db()
        snapshot = self.onboarding.config["content_base_progress"]
        self.assertEqual(snapshot["status"], "complete")

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_chunks_more_than_25_files(self, _mock_sleep):
        first_batch_uuids = [str(uuid4()) for _ in range(BATCH_MAX_FILES)]
        second_batch_uuid = str(uuid4())

        self.mock_nexus_service.upload_content_base_files_batch.side_effect = [
            _batch_upload_response(*first_batch_uuids),
            _batch_upload_response(second_batch_uuid),
        ]
        self.mock_nexus_service.get_content_base_batch_progress.return_value = (
            _batch_progress_response()
        )

        contents = [
            {"link": f"https://a{i}.com", "title": f"Page {i}", "content": f"c{i}"}
            for i in range(BATCH_MAX_FILES + 1)
        ]

        self.usecase.execute("mystore", contents)

        self.assertEqual(
            self.mock_nexus_service.upload_content_base_files_batch.call_count, 2
        )
        first_call_files = (
            self.mock_nexus_service.upload_content_base_files_batch.call_args_list[0][
                1
            ]["files"]
        )
        second_call_files = (
            self.mock_nexus_service.upload_content_base_files_batch.call_args_list[1][
                1
            ]["files"]
        )
        self.assertEqual(len(first_call_files), BATCH_MAX_FILES)
        self.assertEqual(len(second_call_files), 1)


class TestBuildFilesFromContents(TestCase):
    def test_builds_files_with_correct_structure(self):
        contents = [
            {
                "link": "https://example.com/page",
                "title": "Test Page",
                "content": "Some content here.",
            }
        ]

        files = UploadNexusContentsUseCase._build_files_from_contents(contents)

        self.assertEqual(len(files), 1)
        filename, file_bytes, content_type = files[0]
        self.assertEqual(filename, "000_test-page.txt")
        self.assertEqual(file_bytes, b"Some content here.")
        self.assertEqual(content_type, "text/plain")

    def test_uses_fallback_title_when_missing(self):
        contents = [{"link": "https://a.com", "content": "content"}]
        files = UploadNexusContentsUseCase._build_files_from_contents(contents)
        filename = files[0][0]
        self.assertIn("page-0", filename)

    def test_handles_empty_content(self):
        contents = [{"link": "https://a.com", "title": "Page"}]
        files = UploadNexusContentsUseCase._build_files_from_contents(contents)
        self.assertEqual(files[0][1], b"")

    def test_handles_null_title_from_crawler(self):
        contents = [{"link": "https://a.com", "title": None, "content": "body"}]
        files = UploadNexusContentsUseCase._build_files_from_contents(contents)
        self.assertEqual(files[0][0], "000_page-0.txt")

    def test_handles_null_content_from_crawler(self):
        contents = [{"link": "https://a.com", "title": "Page", "content": None}]
        files = UploadNexusContentsUseCase._build_files_from_contents(contents)
        self.assertEqual(files[0][1], b"")


class TestSanitizeFilename(TestCase):
    def test_basic_title(self):
        self.assertEqual(_sanitize_filename("About Us", 0), "000_about-us.txt")

    def test_special_characters(self):
        result = _sanitize_filename("C&A | Fornecedores!", 1)
        self.assertEqual(result, "001_ca-fornecedores.txt")

    def test_url_as_title(self):
        result = _sanitize_filename("https://www.cea.com.br/", 0)
        self.assertEqual(result, "000_httpswwwceacombr.txt")

    def test_empty_title(self):
        result = _sanitize_filename("", 5)
        self.assertEqual(result, "005_page.txt")

    def test_long_title_truncated(self):
        long_title = "A" * 200
        result = _sanitize_filename(long_title, 0)
        self.assertTrue(len(result) <= 89)

    def test_whitespace_collapsed(self):
        result = _sanitize_filename("Hello   World   Page", 2)
        self.assertEqual(result, "002_hello-world-page.txt")

    def test_strips_accents(self):
        result = _sanitize_filename("Promoção Ação Café", 0)
        self.assertEqual(result, "000_promocao-acao-cafe.txt")
