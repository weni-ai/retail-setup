from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase
from rest_framework.test import APIClient

from retail.projects.models import Project, ProjectOnboarding


def _auth_bypass(original_cls):
    """Patches JWTModuleAuthentication to always pass without a real token."""
    return patch(
        "retail.internal.jwt_authenticators.JWTModuleAuthentication.authenticate",
        return_value=(None, None),
    )


class TestStartOnboardingView(TestCase):
    def setUp(self):
        self.client = APIClient()

    @_auth_bypass(None)
    @patch("retail.projects.views.StartOnboardingUseCase")
    def test_returns_201_on_success(self, mock_usecase_cls, _mock_auth):
        mock_instance = MagicMock()
        mock_usecase_cls.return_value = mock_instance

        response = self.client.post(
            "/api/onboard/mystore/start-crawling/",
            {"crawl_url": "https://www.mystore.com.br/"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"status": "started"})
        mock_instance.execute.assert_called_once()

    @_auth_bypass(None)
    def test_returns_400_when_crawl_url_missing(self, _mock_auth):
        response = self.client.post(
            "/api/onboard/mystore/start-crawling/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    @_auth_bypass(None)
    @patch("retail.projects.views.StartOnboardingUseCase")
    def test_returns_502_when_crawler_fails(self, mock_usecase_cls, _mock_auth):
        from retail.projects.usecases.start_crawl import CrawlerStartError

        mock_instance = MagicMock()
        mock_instance.execute.side_effect = CrawlerStartError("Crawler down")
        mock_usecase_cls.return_value = mock_instance

        response = self.client.post(
            "/api/onboard/mystore/start-crawling/",
            {"crawl_url": "https://www.mystore.com.br/"},
            format="json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("Crawler down", response.json()["detail"])


class TestCrawlerWebhookView(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            current_step="CRAWL",
        )

    @patch(
        "retail.projects.usecases.update_onboarding_progress.acquire_task_lock",
        return_value=True,
    )
    @patch("retail.projects.usecases.update_onboarding_progress.task_configure_nexus")
    def test_returns_200_on_valid_webhook(self, mock_task, mock_lock):
        response = self.client.post(
            f"/api/onboard/{self.project.uuid}/webhook/",
            {
                "task_id": "task-1",
                "event": "crawl.subpage.progress",
                "timestamp": "2026-01-01T00:00:00Z",
                "url": "https://mystore.com.br/",
                "progress": 50,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["progress"], 50)

    def test_returns_404_for_unknown_project(self):
        response = self.client.post(
            f"/api/onboard/{uuid4()}/webhook/",
            {
                "task_id": "task-1",
                "event": "crawl.subpage.progress",
                "timestamp": "2026-01-01T00:00:00Z",
                "url": "https://mystore.com.br/",
                "progress": 10,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_returns_400_for_invalid_payload(self):
        response = self.client.post(
            f"/api/onboard/{self.project.uuid}/webhook/",
            {"invalid": "data"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)


class TestOnboardingStatusView(TestCase):
    def setUp(self):
        self.client = APIClient()

    @_auth_bypass(None)
    def test_returns_existing_onboarding(self, _mock_auth):
        project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=project,
            current_step="CRAWL",
            progress=50,
        )

        response = self.client.get("/api/onboard/mystore/status/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["vtex_account"], "mystore")
        self.assertEqual(data["progress"], 50)
        self.assertEqual(data["current_step"], "CRAWL")
        self.assertEqual(data["project_uuid"], str(project.uuid))

    @_auth_bypass(None)
    def test_creates_onboarding_if_not_exists(self, _mock_auth):
        response = self.client.get("/api/onboard/newstore/status/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["vtex_account"], "newstore")
        self.assertEqual(data["progress"], 0)
        self.assertEqual(data["current_step"], "")
        self.assertIsNone(data["project_uuid"])
        self.assertEqual(data["config"], {})

    @_auth_bypass(None)
    def test_response_contains_config_field(self, _mock_auth):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            config={"integrated_apps": {"wwc": str(uuid4())}},
        )

        response = self.client.get("/api/onboard/mystore/status/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("integrated_apps", response.json()["config"])


class TestOnboardingPatchView(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
        )

    @_auth_bypass(None)
    def test_patches_completed_field(self, _mock_auth):
        response = self.client.patch(
            "/api/onboard/mystore/",
            {"completed": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.onboarding.refresh_from_db()
        self.assertTrue(self.onboarding.completed)

    @_auth_bypass(None)
    def test_patches_current_page_field(self, _mock_auth):
        response = self.client.patch(
            "/api/onboard/mystore/",
            {"current_page": "setup_channel"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.current_page, "setup_channel")

    @_auth_bypass(None)
    def test_partial_patch_only_completed(self, _mock_auth):
        self.onboarding.current_page = "initial_page"
        self.onboarding.save()

        response = self.client.patch(
            "/api/onboard/mystore/",
            {"completed": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.onboarding.refresh_from_db()
        self.assertTrue(self.onboarding.completed)
        self.assertEqual(self.onboarding.current_page, "initial_page")

    @_auth_bypass(None)
    def test_returns_404_for_unknown_vtex_account(self, _mock_auth):
        response = self.client.patch(
            "/api/onboard/unknown/",
            {"completed": True},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
