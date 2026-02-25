from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.manager_defaults import (
    MANAGER_DEFAULTS,
    MANAGER_PERSONALITY,
)
from retail.projects.usecases.configure_agent_builder import (
    ConfigureAgentBuilderUseCase,
    ProjectNotLinkedError,
    MAX_UPLOAD_PROGRESS,
    _sanitize_filename,
)


class TestConfigureAgentBuilderUseCase(TestCase):
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
        )
        self.mock_nexus_service = MagicMock()
        self.usecase = ConfigureAgentBuilderUseCase(
            nexus_client=MagicMock(),
        )
        self.usecase.nexus_service = self.mock_nexus_service

    def test_raises_error_when_project_not_linked(self):
        ProjectOnboarding.objects.create(
            vtex_account="noproject",
        )

        with self.assertRaises(ProjectNotLinkedError):
            self.usecase.execute("noproject", [])

    def test_sets_progress_to_max_upload_when_contents_empty(self):
        self.usecase.execute("mystore", [])

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.progress, MAX_UPLOAD_PROGRESS)
        self.mock_nexus_service.upload_content_base_file.assert_not_called()

    def test_uploads_files_for_each_content(self):
        self.mock_nexus_service.upload_content_base_file.return_value = {"status": "ok"}

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

    def test_file_contains_only_content(self):
        self.mock_nexus_service.upload_content_base_file.return_value = {"status": "ok"}

        contents = [
            {
                "link": "https://example.com/page",
                "title": "Test Page",
                "content": "Some content here.",
            }
        ]

        self.usecase.execute("mystore", contents)

        call_args = self.mock_nexus_service.upload_content_base_file.call_args
        _, file_tuple = call_args[1]["project_uuid"], call_args[1]["file"]
        filename, file_bytes, content_type = file_tuple

        text = file_bytes.decode("utf-8")
        self.assertEqual(text, "Some content here.")
        self.assertNotIn("Title:", text)
        self.assertNotIn("Source:", text)

    def test_progress_updates_proportionally(self):
        self.mock_nexus_service.upload_content_base_file.return_value = {"status": "ok"}

        contents = [
            {"link": "https://a.com", "title": "A", "content": "a"},
            {"link": "https://b.com", "title": "B", "content": "b"},
            {"link": "https://c.com", "title": "C", "content": "c"},
            {"link": "https://d.com", "title": "D", "content": "d"},
        ]

        self.usecase.execute("mystore", contents)

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.progress, MAX_UPLOAD_PROGRESS)

    def test_continues_on_upload_failure(self):
        self.mock_nexus_service.upload_content_base_file.side_effect = [
            None,
            {"status": "ok"},
        ]

        contents = [
            {"link": "https://a.com", "title": "A", "content": "a"},
            {"link": "https://b.com", "title": "B", "content": "b"},
        ]

        self.usecase.execute("mystore", contents)
        self.assertEqual(self.mock_nexus_service.upload_content_base_file.call_count, 2)

    def test_passes_project_uuid_to_nexus(self):
        self.mock_nexus_service.upload_content_base_file.return_value = {"status": "ok"}

        contents = [
            {"link": "https://a.com", "title": "A", "content": "a"},
        ]

        self.usecase.execute("mystore", contents)

        call_kwargs = self.mock_nexus_service.upload_content_base_file.call_args[1]
        self.assertEqual(call_kwargs["project_uuid"], str(self.project.uuid))


class TestAgentConfiguration(TestCase):
    """Tests for the check/configure agent manager flow."""

    def setUp(self):
        self.project = Project.objects.create(
            name="Test Project",
            uuid=uuid4(),
            vtex_account="flowstore",
            language="pt-br",
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="flowstore",
            project=self.project,
        )
        self.mock_nexus_service = MagicMock()
        self.usecase = ConfigureAgentBuilderUseCase(nexus_client=MagicMock())
        self.usecase.nexus_service = self.mock_nexus_service

    def test_skips_configure_when_agent_already_exists(self):
        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": True, "name": "Flowstore Manager"}
        }

        self.usecase.execute("flowstore", [])

        self.mock_nexus_service.check_agent_builder_exists.assert_called_once_with(
            str(self.project.uuid)
        )
        self.mock_nexus_service.configure_agent_attributes.assert_not_called()

    def test_configures_agent_when_not_exists(self):
        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": False}
        }
        self.mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        self.usecase.execute("flowstore", [])

        self.mock_nexus_service.configure_agent_attributes.assert_called_once()
        payload = self.mock_nexus_service.configure_agent_attributes.call_args[0][1]
        self.assertEqual(payload["agent"]["name"], "Flowstore Manager")
        self.assertEqual(payload["agent"]["personality"], MANAGER_PERSONALITY)
        self.assertEqual(payload["agent"]["role"], MANAGER_DEFAULTS["pt"]["role"])
        self.assertEqual(payload["agent"]["goal"], MANAGER_DEFAULTS["pt"]["goal"])
        self.assertEqual(payload["links"], [])

    def test_configures_agent_with_english_fallback(self):
        self.project.language = "ja-jp"
        self.project.save()

        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": False}
        }
        self.mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        self.usecase.execute("flowstore", [])

        payload = self.mock_nexus_service.configure_agent_attributes.call_args[0][1]
        self.assertEqual(payload["agent"]["role"], MANAGER_DEFAULTS["en"]["role"])
        self.assertEqual(payload["agent"]["goal"], MANAGER_DEFAULTS["en"]["goal"])

    def test_configures_agent_with_spanish(self):
        self.project.language = "es"
        self.project.save()

        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": False}
        }
        self.mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        self.usecase.execute("flowstore", [])

        payload = self.mock_nexus_service.configure_agent_attributes.call_args[0][1]
        self.assertEqual(payload["agent"]["role"], MANAGER_DEFAULTS["es"]["role"])

    def test_configures_agent_when_check_returns_none(self):
        """If the check endpoint fails, we still attempt to configure."""
        self.mock_nexus_service.check_agent_builder_exists.return_value = None
        self.mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        self.usecase.execute("flowstore", [])

        self.mock_nexus_service.configure_agent_attributes.assert_called_once()

    def test_configures_agent_with_null_language_falls_back_to_en(self):
        self.project.language = None
        self.project.save()

        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": False}
        }
        self.mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        self.usecase.execute("flowstore", [])

        payload = self.mock_nexus_service.configure_agent_attributes.call_args[0][1]
        self.assertEqual(payload["agent"]["role"], MANAGER_DEFAULTS["en"]["role"])


class TestBuildFilesFromContents(TestCase):
    def test_builds_files_with_correct_structure(self):
        contents = [
            {
                "link": "https://example.com/page",
                "title": "Test Page",
                "content": "Some content here.",
            }
        ]

        files = ConfigureAgentBuilderUseCase._build_files_from_contents(contents)

        self.assertEqual(len(files), 1)
        filename, file_bytes, content_type = files[0]
        self.assertEqual(filename, "000_test-page.txt")
        self.assertEqual(file_bytes, b"Some content here.")
        self.assertEqual(content_type, "text/plain")

    def test_uses_fallback_title_when_missing(self):
        contents = [{"link": "https://a.com", "content": "content"}]
        files = ConfigureAgentBuilderUseCase._build_files_from_contents(contents)
        filename = files[0][0]
        self.assertIn("page-0", filename)

    def test_handles_empty_content(self):
        contents = [{"link": "https://a.com", "title": "Page"}]
        files = ConfigureAgentBuilderUseCase._build_files_from_contents(contents)
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
