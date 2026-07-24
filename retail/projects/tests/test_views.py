from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase
from rest_framework.test import APIClient
from weni_commons.auth import WeniAuthContext, WeniAuthUser

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.install_channel_agents import InstallChannelAgentsError


def auth_bypass(**auth_kwargs):
    """Patch retail auth and populate ``WeniAuthContext`` for view tests."""

    def decorator(test_func):
        vtex_account = auth_kwargs.get("vtex_account", "mystore")
        user_email = auth_kwargs.get("user_email", "test@example.com")
        auth_context = WeniAuthContext(
            project_uuid=auth_kwargs.get("project_uuid"),
            vtex_account=vtex_account,
            user_email=user_email,
            token_type=auth_kwargs.get("token_type", "jwt"),
        )
        return patch(
            "retail.internal.authenticators.RetailAuthentication.authenticate",
            return_value=(WeniAuthUser(email=user_email), auth_context),
        )(test_func)

    return decorator


class TestStartSetupView(TestCase):
    def setUp(self):
        self.client = APIClient()

    @auth_bypass()
    @patch("retail.projects.views.StartSetupUseCase")
    def test_returns_201_on_success(self, mock_usecase_cls, _mock_auth):
        mock_instance = MagicMock()
        mock_usecase_cls.return_value = mock_instance

        response = self.client.post(
            "/api/onboard/mystore/start-setup/",
            {"crawl_url": "https://www.mystore.com.br/", "channel": "wwc"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"status": "started"})
        mock_instance.execute.assert_called_once()

    @auth_bypass()
    def test_returns_400_when_crawl_url_missing(self, _mock_auth):
        response = self.client.post(
            "/api/onboard/mystore/start-setup/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    @auth_bypass()
    @patch("retail.projects.views.StartSetupUseCase")
    def test_returns_201_with_wpp_cloud_channel_data(
        self, mock_usecase_cls, _mock_auth
    ):
        mock_instance = MagicMock()
        mock_usecase_cls.return_value = mock_instance

        response = self.client.post(
            "/api/onboard/mystore/start-setup/",
            {
                "crawl_url": "https://www.mystore.com.br/",
                "channel": "wpp-cloud",
                "channel_data": {
                    "auth_code": "abc123",
                    "waba_id": "waba456",
                    "phone_number_id": "phone789",
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        mock_instance.execute.assert_called_once()

    @auth_bypass()
    def test_returns_400_when_wpp_cloud_without_channel_data(self, _mock_auth):
        response = self.client.post(
            "/api/onboard/mystore/start-setup/",
            {
                "crawl_url": "https://www.mystore.com.br/",
                "channel": "wpp-cloud",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    @auth_bypass()
    def test_stores_failure_snapshot_on_validation_error(self, _mock_auth):
        """When the payload is invalid, the snapshot must be persisted in config."""
        payload = {
            "crawl_url": "https://www.mystore.com.br/",
            "channel": "wpp-cloud",
        }

        response = self.client.post(
            "/api/onboard/mystore/start-setup/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        last_failure = onboarding.config["last_failure"]
        self.assertEqual(last_failure["stage"], "start_setup_validation")
        self.assertEqual(last_failure["payload"], payload)
        self.assertIn("channel_data", last_failure["errors"])


class TestCrawlerWebhookView(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            current_step="NEXUS_CONFIG",
        )

    @patch(
        "retail.projects.usecases.update_onboarding_progress.acquire_task_lock",
        return_value=True,
    )
    @patch(
        "retail.projects.usecases.update_onboarding_progress.task_upload_nexus_contents"
    )
    def test_returns_200_on_valid_webhook(self, mock_task, mock_lock):
        """
        Background crawl progress events do NOT touch the main
        ``progress`` -- the response reflects the onboarding's current
        main progress (set by the inline orchestrator path), not the
        crawl-local percentage in the webhook payload.
        """
        self.onboarding.progress = 100
        self.onboarding.current_step = "NEXUS_CONFIG"
        self.onboarding.save(update_fields=["progress", "current_step"])

        response = self.client.post(
            f"/api/onboard/{self.onboarding.uuid}/webhook/",
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
        self.assertEqual(response.json()["progress"], 100)

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
            f"/api/onboard/{self.onboarding.uuid}/webhook/",
            {"invalid": "data"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)


class TestOnboardingStatusView(TestCase):
    def setUp(self):
        self.client = APIClient()

    @auth_bypass()
    def test_returns_existing_onboarding(self, _mock_auth):
        project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=project,
            current_step="NEXUS_CONFIG",
            progress=50,
        )

        response = self.client.get("/api/onboard/mystore/status/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["vtex_account"], "mystore")
        self.assertEqual(data["progress"], 50)
        self.assertEqual(data["current_step"], "NEXUS_CONFIG")
        self.assertEqual(data["project_uuid"], str(project.uuid))

    @auth_bypass()
    def test_creates_onboarding_if_not_exists(self, _mock_auth):
        response = self.client.get("/api/onboard/mystore/status/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["vtex_account"], "mystore")
        self.assertEqual(data["progress"], 0)
        self.assertEqual(data["current_step"], "")
        self.assertIsNone(data["project_uuid"])
        self.assertEqual(data["config"], {})

    @auth_bypass()
    def test_response_contains_config_field(self, _mock_auth):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            config={"channels": {"wwc": {"app_uuid": str(uuid4())}}},
        )

        response = self.client.get("/api/onboard/mystore/status/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("channels", response.json()["config"])


class TestContentBaseProgressView(TestCase):
    def setUp(self):
        self.client = APIClient()

    @auth_bypass()
    def test_returns_weighted_progress(self, _mock_auth):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            config={
                "content_base_progress": {
                    "crawl_percent": 100,
                    "upload_percent": 50,
                    "status": "uploading",
                }
            },
        )

        response = self.client.get("/api/onboard/mystore/content-base-progress/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"progress": 66})

    @auth_bypass(vtex_account="unknown")
    def test_returns_404_when_onboarding_missing(self, _mock_auth):
        response = self.client.get("/api/onboard/unknown/content-base-progress/")

        self.assertEqual(response.status_code, 404)


class TestOnboardingPatchView(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
        )

    @auth_bypass()
    @patch("retail.projects.tasks.task_activate_agentic_cx_script")
    def test_patches_completed_field(self, _mock_task, _mock_auth):
        response = self.client.patch(
            "/api/onboard/mystore/",
            {"completed": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.onboarding.refresh_from_db()
        self.assertTrue(self.onboarding.completed)

    @auth_bypass()
    def test_patches_current_page_field(self, _mock_auth):
        response = self.client.patch(
            "/api/onboard/mystore/",
            {"current_page": "setup_channel"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.current_page, "setup_channel")

    @auth_bypass()
    @patch("retail.projects.tasks.task_activate_agentic_cx_script")
    def test_partial_patch_only_completed(self, _mock_task, _mock_auth):
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

    @auth_bypass(vtex_account="unknown")
    @patch("retail.projects.tasks.task_activate_agentic_cx_script")
    def test_returns_404_for_unknown_vtex_account(self, _mock_task, _mock_auth):
        response = self.client.patch(
            "/api/onboard/unknown/",
            {"completed": True},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    @auth_bypass(vtex_account=None)
    def test_missing_tenant_returns_403(self, _mock_auth):
        response = self.client.get("/api/onboard/other-store/status/")

        self.assertEqual(response.status_code, 403)


class TestOnboardingSupportContactView(TestCase):
    def setUp(self):
        self.client = APIClient()

    @auth_bypass()
    @patch("retail.projects.views.RequestOnboardingSupportUseCase")
    def test_returns_202_and_dispatches_use_case(self, mock_use_case_cls, _mock_auth):
        mock_instance = MagicMock()
        mock_use_case_cls.return_value = mock_instance

        response = self.client.post(
            "/api/onboard/mystore/support-contact/",
            {"data": {"message": "stuck on channel setup", "screen": "wpp_setup"}},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"status": "received"})
        mock_instance.execute.assert_called_once()
        dto = mock_instance.execute.call_args.args[0]
        self.assertEqual(dto.vtex_account, "mystore")
        self.assertEqual(
            dto.data, {"message": "stuck on channel setup", "screen": "wpp_setup"}
        )

    @auth_bypass()
    @patch("retail.projects.views.RequestOnboardingSupportUseCase")
    def test_accepts_empty_body(self, mock_use_case_cls, _mock_auth):
        mock_instance = MagicMock()
        mock_use_case_cls.return_value = mock_instance

        response = self.client.post(
            "/api/onboard/mystore/support-contact/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        dto = mock_instance.execute.call_args.args[0]
        self.assertEqual(dto.data, {})

    @auth_bypass()
    def test_returns_400_when_data_is_not_an_object(self, _mock_auth):
        response = self.client.post(
            "/api/onboard/mystore/support-contact/",
            {"data": "not-a-dict"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)


class TestInstallChannelAgentsView(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/onboard/mystore/wwc/install-agents/"
        self.valid_payload = {"channel_data": {"app_uuid": str(uuid4())}}

    @auth_bypass()
    @patch("retail.projects.views.InstallChannelAgentsUseCase")
    def test_returns_201_and_uses_tenant_from_auth(self, mock_use_case_cls, _mock_auth):
        mock_instance = MagicMock()
        mock_use_case_cls.return_value = mock_instance

        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"success": True})
        dto = mock_instance.execute.call_args.args[0]
        self.assertEqual(dto.vtex_account, "mystore")
        self.assertEqual(dto.channel, "wwc")

    @auth_bypass()
    @patch("retail.projects.views.InstallChannelAgentsUseCase")
    def test_returns_404_when_onboarding_missing(self, mock_use_case_cls, _mock_auth):
        mock_use_case_cls.return_value.execute.side_effect = (
            ProjectOnboarding.DoesNotExist
        )

        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, 404)

    @auth_bypass()
    @patch("retail.projects.views.InstallChannelAgentsUseCase")
    def test_returns_400_on_install_error(self, mock_use_case_cls, _mock_auth):
        mock_use_case_cls.return_value.execute.side_effect = InstallChannelAgentsError(
            "channel creation failed"
        )

        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, 400)

    @auth_bypass()
    def test_returns_400_when_channel_data_missing(self, _mock_auth):
        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, 400)

    @auth_bypass(vtex_account=None)
    def test_missing_tenant_returns_403(self, _mock_auth):
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, 403)


class TestVtexAccountLookupView(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/projects/vtex-account/"
        self.project_uuid = str(uuid4())

    @auth_bypass(project_uuid="11111111-1111-1111-1111-111111111111")
    @patch("retail.projects.views.GetProjectVtexAccountUseCase")
    def test_returns_vtex_account_from_project_uuid(
        self, mock_use_case_cls, _mock_auth
    ):
        mock_use_case_cls.return_value.execute.return_value = "mystore"

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"vtex_account": "mystore"})
        mock_use_case_cls.return_value.execute.assert_called_once_with(
            "11111111-1111-1111-1111-111111111111"
        )

    @auth_bypass(project_uuid="11111111-1111-1111-1111-111111111111")
    @patch("retail.projects.views.GetProjectVtexAccountUseCase")
    def test_returns_400_when_account_not_found(self, mock_use_case_cls, _mock_auth):
        mock_use_case_cls.return_value.execute.return_value = None

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 400)

    @auth_bypass(project_uuid=None)
    def test_missing_project_uuid_returns_403(self, _mock_auth):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)
