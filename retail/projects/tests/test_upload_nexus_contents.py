from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.agent_builder_helpers import ProjectNotLinkedError
from retail.projects.usecases.upload_nexus_contents import (
    FileProcessingError,
    FileUploadError,
    UploadNexusContentsUseCase,
    _sanitize_filename,
)


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
        self.mock_nexus_service.upload_content_base_file.assert_not_called()

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
    def test_uploads_files_for_each_content(self, _mock_sleep):
        upload_uuid = str(uuid4())
        self.mock_nexus_service.upload_content_base_file.return_value = {
            "uuid": upload_uuid,
            "extension_file": "txt",
        }
        self.mock_nexus_service.get_content_base_file_status.return_value = {
            "uuid": upload_uuid,
            "status": "success",
        }

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

        self.assertEqual(self.mock_nexus_service.upload_content_base_file.call_count, 2)
        self.assertEqual(
            self.mock_nexus_service.get_content_base_file_status.call_count, 2
        )

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_file_contains_only_content(self, _mock_sleep):
        upload_uuid = str(uuid4())
        self.mock_nexus_service.upload_content_base_file.return_value = {
            "uuid": upload_uuid,
            "extension_file": "txt",
        }
        self.mock_nexus_service.get_content_base_file_status.return_value = {
            "uuid": upload_uuid,
            "status": "success",
        }

        contents = [
            {
                "link": "https://example.com/page",
                "title": "Test Page",
                "content": "Some content here.",
            }
        ]

        self.usecase.execute("mystore", contents)

        call_kwargs = self.mock_nexus_service.upload_content_base_file.call_args[1]
        _, file_bytes, _ = call_kwargs["file"]

        text = file_bytes.decode("utf-8")
        self.assertEqual(text, "Some content here.")
        self.assertNotIn("Title:", text)
        self.assertNotIn("Source:", text)

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_does_not_update_progress(self, _mock_sleep):
        """Background path must never touch ``onboarding.progress``."""
        upload_uuid = str(uuid4())
        self.mock_nexus_service.upload_content_base_file.return_value = {
            "uuid": upload_uuid,
            "extension_file": "txt",
        }
        self.mock_nexus_service.get_content_base_file_status.return_value = {
            "uuid": upload_uuid,
            "status": "success",
        }

        contents = [
            {"link": "https://a.com", "title": "A", "content": "a"},
            {"link": "https://b.com", "title": "B", "content": "b"},
        ]

        self.usecase.execute("mystore", contents)

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.progress, 100)

    def test_stops_on_upload_failure(self):
        self.mock_nexus_service.upload_content_base_file.side_effect = [
            None,
            {"uuid": str(uuid4()), "extension_file": "txt"},
        ]

        contents = [
            {"link": "https://a.com", "title": "A", "content": "a"},
            {"link": "https://b.com", "title": "B", "content": "b"},
        ]

        with self.assertRaises(FileUploadError):
            self.usecase.execute("mystore", contents)

        self.assertEqual(self.mock_nexus_service.upload_content_base_file.call_count, 1)

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_passes_project_uuid_to_nexus(self, _mock_sleep):
        upload_uuid = str(uuid4())
        self.mock_nexus_service.upload_content_base_file.return_value = {
            "uuid": upload_uuid,
            "extension_file": "txt",
        }
        self.mock_nexus_service.get_content_base_file_status.return_value = {
            "uuid": upload_uuid,
            "status": "success",
        }

        contents = [
            {"link": "https://a.com", "title": "A", "content": "a"},
        ]

        self.usecase.execute("mystore", contents)

        call_kwargs = self.mock_nexus_service.upload_content_base_file.call_args[1]
        self.assertEqual(call_kwargs["project_uuid"], str(self.project.uuid))

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_waits_for_processing_before_next_upload(self, _mock_sleep):
        """Ensures polling occurs between consecutive uploads."""
        uuid_1, uuid_2 = str(uuid4()), str(uuid4())
        self.mock_nexus_service.upload_content_base_file.side_effect = [
            {"uuid": uuid_1, "extension_file": "txt"},
            {"uuid": uuid_2, "extension_file": "txt"},
        ]
        self.mock_nexus_service.get_content_base_file_status.side_effect = [
            {"uuid": uuid_1, "status": "Processing"},
            {"uuid": uuid_1, "status": "success"},
            {"uuid": uuid_2, "status": "success"},
        ]

        contents = [
            {"link": "https://a.com", "title": "A", "content": "a"},
            {"link": "https://b.com", "title": "B", "content": "b"},
        ]

        self.usecase.execute("mystore", contents)

        self.assertEqual(
            self.mock_nexus_service.get_content_base_file_status.call_count, 3
        )

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_retries_status_poll_when_status_unavailable(self, _mock_sleep):
        """A transient ``None`` status response must not abort polling."""
        upload_uuid = str(uuid4())
        self.mock_nexus_service.upload_content_base_file.return_value = {
            "uuid": upload_uuid,
            "extension_file": "txt",
        }
        self.mock_nexus_service.get_content_base_file_status.side_effect = [
            None,
            {"uuid": upload_uuid, "status": "success"},
        ]

        contents = [{"link": "https://a.com", "title": "A", "content": "a"}]

        self.usecase.execute("mystore", contents)

        self.assertEqual(
            self.mock_nexus_service.get_content_base_file_status.call_count, 2
        )

    @patch("retail.projects.usecases.upload_nexus_contents.FILE_STATUS_MAX_ATTEMPTS", 2)
    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_gives_up_after_max_attempts_without_terminal_status(self, _mock_sleep):
        """Polling stops (without raising) once the attempt budget runs out."""
        upload_uuid = str(uuid4())
        self.mock_nexus_service.upload_content_base_file.return_value = {
            "uuid": upload_uuid,
            "extension_file": "txt",
        }
        self.mock_nexus_service.get_content_base_file_status.return_value = {
            "uuid": upload_uuid,
            "status": "processing",
        }

        contents = [{"link": "https://a.com", "title": "A", "content": "a"}]

        self.usecase.execute("mystore", contents)

        self.assertEqual(
            self.mock_nexus_service.get_content_base_file_status.call_count, 2
        )

    @patch("retail.projects.usecases.upload_nexus_contents.time.sleep")
    def test_raises_on_processing_failure(self, _mock_sleep):
        upload_uuid = str(uuid4())
        self.mock_nexus_service.upload_content_base_file.return_value = {
            "uuid": upload_uuid,
            "extension_file": "txt",
        }
        self.mock_nexus_service.get_content_base_file_status.return_value = {
            "uuid": upload_uuid,
            "status": "failed",
        }

        contents = [
            {"link": "https://a.com", "title": "A", "content": "a"},
        ]

        with self.assertRaises(FileProcessingError):
            self.usecase.execute("mystore", contents)


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
