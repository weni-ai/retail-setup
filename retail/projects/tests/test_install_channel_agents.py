from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.install_channel_agents import (
    InstallChannelAgentsError,
    InstallChannelAgentsUseCase,
)
from retail.projects.usecases.onboarding_agents.base import PassiveAgent
from retail.projects.usecases.onboarding_dto import InstallChannelAgentsDTO


class StubAgent(PassiveAgent):
    def __init__(self, uuid, name):
        self.uuid = uuid
        self.name = name


class TestInstallChannelAgentsUseCase(TestCase):
    def setUp(self):
        self._agentic_patcher = patch(
            "retail.projects.tasks.task_activate_agentic_cx_script"
        )
        self._agentic_patcher.start()

        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"wwc": {"app_uuid": "wwc-uuid"}}},
            completed=True,
        )
        self.mock_nexus_client = MagicMock()
        self.mock_integrations_client = MagicMock()
        self.usecase = InstallChannelAgentsUseCase(
            nexus_client=self.mock_nexus_client,
            integrations_client=self.mock_integrations_client,
        )
        self.usecase.integrations_service = MagicMock()
        self.usecase.nexus_service = MagicMock()

    def tearDown(self):
        self._agentic_patcher.stop()

    def _build_dto(self, channel="wpp-cloud", channel_data=None):
        return InstallChannelAgentsDTO(
            vtex_account="mystore",
            channel=channel,
            channel_data=channel_data
            or {
                "auth_code": "abc123",
                "waba_id": "waba-1",
                "phone_number_id": "phone-1",
            },
        )

    @patch(
        "retail.projects.usecases.install_channel_agents.get_channel_agents",
        return_value=[
            StubAgent("uuid-1", "Agent A"),
            StubAgent("uuid-2", "Agent B"),
        ],
    )
    def test_creates_channel_and_integrates_agents(self, _mock_agents):
        self.usecase.integrations_service.create_wpp_cloud_channel.return_value = {
            "app_uuid": "wpp-app-uuid",
            "flow_object_uuid": "wpp-channel-uuid",
        }
        self.usecase.nexus_service.list_integrated_agents.return_value = []
        self.usecase.nexus_service.integrate_agent.return_value = {"ok": True}

        self.usecase.execute(self._build_dto())

        self.usecase.integrations_service.create_wpp_cloud_channel.assert_called_once_with(
            project_uuid=str(self.project.uuid),
            auth_code="abc123",
            waba_id="waba-1",
            phone_number_id="phone-1",
        )

        self.onboarding.refresh_from_db()
        self.assertEqual(
            self.onboarding.config["channels"]["wpp-cloud"]["app_uuid"],
            "wpp-app-uuid",
        )
        self.assertEqual(self.usecase.nexus_service.integrate_agent.call_count, 2)

    @patch(
        "retail.projects.usecases.install_channel_agents.get_channel_agents",
        return_value=[
            StubAgent("uuid-1", "Agent A"),
            StubAgent("uuid-2", "Agent B"),
            StubAgent("uuid-3", "Agent C"),
        ],
    )
    def test_skips_already_integrated_agents(self, _mock_agents):
        self.usecase.integrations_service.create_wpp_cloud_channel.return_value = {
            "app_uuid": "wpp-app-uuid",
            "flow_object_uuid": "wpp-channel-uuid",
        }
        self.usecase.nexus_service.list_integrated_agents.return_value = [
            {"uuid": "uuid-1"},
            {"uuid": "uuid-3"},
        ]
        self.usecase.nexus_service.integrate_agent.return_value = {"ok": True}

        self.usecase.execute(self._build_dto())

        self.usecase.nexus_service.integrate_agent.assert_called_once()
        call_args = self.usecase.nexus_service.integrate_agent.call_args
        self.assertEqual(call_args[0][1], "uuid-2")

    @patch(
        "retail.projects.usecases.install_channel_agents.get_channel_agents",
        return_value=[
            StubAgent("uuid-1", "Agent A"),
            StubAgent("uuid-2", "Agent B"),
        ],
    )
    def test_skips_all_when_all_already_integrated(self, _mock_agents):
        self.usecase.integrations_service.create_wpp_cloud_channel.return_value = {
            "app_uuid": "wpp-app-uuid",
            "flow_object_uuid": "wpp-channel-uuid",
        }
        self.usecase.nexus_service.list_integrated_agents.return_value = [
            {"uuid": "uuid-1"},
            {"uuid": "uuid-2"},
        ]

        self.usecase.execute(self._build_dto())

        self.usecase.nexus_service.integrate_agent.assert_not_called()

    @patch(
        "retail.projects.usecases.install_channel_agents.get_channel_agents",
        return_value=[],
    )
    def test_skips_integration_when_no_agents_configured(self, _mock_agents):
        self.usecase.integrations_service.create_wpp_cloud_channel.return_value = {
            "app_uuid": "wpp-app-uuid",
            "flow_object_uuid": "wpp-channel-uuid",
        }

        self.usecase.execute(self._build_dto())

        self.usecase.nexus_service.integrate_agent.assert_not_called()
        self.onboarding.refresh_from_db()
        self.assertEqual(
            self.onboarding.config["channels"]["wpp-cloud"]["app_uuid"],
            "wpp-app-uuid",
        )

    def test_raises_error_when_no_project_linked(self):
        ProjectOnboarding.objects.create(vtex_account="noproject")

        dto = InstallChannelAgentsDTO(
            vtex_account="noproject",
            channel="wpp-cloud",
            channel_data={"auth_code": "x"},
        )

        with self.assertRaises(InstallChannelAgentsError) as ctx:
            self.usecase.execute(dto)

        self.assertIn("no project linked", str(ctx.exception))

    def test_raises_error_on_unsupported_channel(self):
        dto = InstallChannelAgentsDTO(
            vtex_account="mystore",
            channel="telegram",
            channel_data={},
        )

        with self.assertRaises(ValueError) as ctx:
            self.usecase.execute(dto)

        self.assertIn("Unsupported channel", str(ctx.exception))

    def test_raises_error_when_onboarding_not_found(self):
        dto = InstallChannelAgentsDTO(
            vtex_account="nonexistent",
            channel="wpp-cloud",
            channel_data={},
        )

        with self.assertRaises(ProjectOnboarding.DoesNotExist):
            self.usecase.execute(dto)

    @patch(
        "retail.projects.usecases.install_channel_agents.get_channel_agents",
        return_value=[StubAgent("uuid-1", "Agent A")],
    )
    def test_raises_error_when_channel_creation_fails(self, _mock_agents):
        self.usecase.integrations_service.create_wpp_cloud_channel.return_value = None

        with self.assertRaises(InstallChannelAgentsError) as ctx:
            self.usecase.execute(self._build_dto())

        self.assertIn("Failed to create", str(ctx.exception))

    @patch(
        "retail.projects.usecases.install_channel_agents.get_channel_agents",
        return_value=[StubAgent("uuid-1", "Agent A")],
    )
    def test_raises_error_when_agent_integration_fails(self, _mock_agents):
        self.usecase.integrations_service.create_wpp_cloud_channel.return_value = {
            "app_uuid": "wpp-app-uuid",
            "flow_object_uuid": "wpp-channel-uuid",
        }
        self.usecase.nexus_service.list_integrated_agents.return_value = []
        self.usecase.nexus_service.integrate_agent.return_value = None

        with self.assertRaises(InstallChannelAgentsError) as ctx:
            self.usecase.execute(self._build_dto())

        self.assertIn("Failed to integrate agent", str(ctx.exception))

    @patch(
        "retail.projects.usecases.install_channel_agents.get_channel_agents",
        return_value=[StubAgent("uuid-1", "Agent A")],
    )
    def test_preserves_existing_channels_in_config(self, _mock_agents):
        self.usecase.integrations_service.create_wpp_cloud_channel.return_value = {
            "app_uuid": "wpp-app-uuid",
            "flow_object_uuid": "wpp-channel-uuid",
        }
        self.usecase.nexus_service.list_integrated_agents.return_value = []
        self.usecase.nexus_service.integrate_agent.return_value = {"ok": True}

        self.usecase.execute(self._build_dto())

        self.onboarding.refresh_from_db()
        self.assertIn("wwc", self.onboarding.config["channels"])
        self.assertEqual(
            self.onboarding.config["channels"]["wwc"]["app_uuid"], "wwc-uuid"
        )
        self.assertIn("wpp-cloud", self.onboarding.config["channels"])

    @patch(
        "retail.projects.usecases.install_channel_agents.get_channel_agents",
        return_value=[
            StubAgent("uuid-1", "Agent A"),
            StubAgent("uuid-2", "Agent B"),
        ],
    )
    def test_handles_nexus_list_agents_returning_none(self, _mock_agents):
        """When Nexus list fails (returns None), all agents should be integrated."""
        self.usecase.integrations_service.create_wpp_cloud_channel.return_value = {
            "app_uuid": "wpp-app-uuid",
            "flow_object_uuid": "wpp-channel-uuid",
        }
        self.usecase.nexus_service.list_integrated_agents.return_value = None
        self.usecase.nexus_service.integrate_agent.return_value = {"ok": True}

        self.usecase.execute(self._build_dto())

        self.assertEqual(self.usecase.nexus_service.integrate_agent.call_count, 2)

    @patch(
        "retail.projects.usecases.install_channel_agents.get_channel_agents",
        return_value=[StubAgent("uuid-1", "Agent A")],
    )
    def test_handles_nexus_list_agents_with_results_key(self, _mock_agents):
        """Handles Nexus response wrapped in a 'results' key."""
        self.usecase.integrations_service.create_wpp_cloud_channel.return_value = {
            "app_uuid": "wpp-app-uuid",
            "flow_object_uuid": "wpp-channel-uuid",
        }
        self.usecase.nexus_service.list_integrated_agents.return_value = {
            "results": [{"uuid": "uuid-1"}]
        }

        self.usecase.execute(self._build_dto())

        self.usecase.nexus_service.integrate_agent.assert_not_called()

    @patch(
        "retail.projects.usecases.install_channel_agents.get_channel_agents",
    )
    def test_skips_agent_already_integrated_via_retail(self, mock_get_agents):
        """Agents integrated via Retail (active) should also be skipped."""
        retail_agent = Agent.objects.create(
            uuid=uuid4(),
            name="Active Agent",
            slug="active",
            description="",
            project=self.project,
        )
        IntegratedAgent.objects.create(
            agent=retail_agent,
            project=self.project,
            is_active=True,
        )

        mock_get_agents.return_value = [
            StubAgent(str(retail_agent.uuid), "Active Agent"),
            StubAgent("new-uuid", "New Agent"),
        ]
        self.usecase.integrations_service.create_wpp_cloud_channel.return_value = {
            "app_uuid": "wpp-app-uuid",
            "flow_object_uuid": "wpp-channel-uuid",
        }
        self.usecase.nexus_service.list_integrated_agents.return_value = []
        self.usecase.nexus_service.integrate_agent.return_value = {"ok": True}

        self.usecase.execute(self._build_dto())

        self.usecase.nexus_service.integrate_agent.assert_called_once()
        call_args = self.usecase.nexus_service.integrate_agent.call_args
        self.assertEqual(call_args[0][1], "new-uuid")

    @patch(
        "retail.projects.usecases.install_channel_agents.get_channel_agents",
    )
    def test_inactive_retail_agents_are_not_skipped(self, mock_get_agents):
        """Agents deactivated in Retail should NOT be skipped."""
        retail_agent = Agent.objects.create(
            uuid=uuid4(),
            name="Inactive Agent",
            slug="inactive",
            description="",
            project=self.project,
        )
        IntegratedAgent.objects.create(
            agent=retail_agent,
            project=self.project,
            is_active=False,
        )

        mock_get_agents.return_value = [
            StubAgent(str(retail_agent.uuid), "Inactive Agent"),
        ]
        self.usecase.integrations_service.create_wpp_cloud_channel.return_value = {
            "app_uuid": "wpp-app-uuid",
            "flow_object_uuid": "wpp-channel-uuid",
        }
        self.usecase.nexus_service.list_integrated_agents.return_value = []
        self.usecase.nexus_service.integrate_agent.return_value = {"ok": True}

        self.usecase.execute(self._build_dto())

        self.usecase.nexus_service.integrate_agent.assert_called_once()

    @patch(
        "retail.projects.usecases.install_channel_agents.get_channel_agents",
        return_value=[],
    )
    def test_wwc_channel_is_configured_after_creation(self, _mock_agents):
        """WWC channels require a configure step after creation."""
        self.usecase.integrations_service.create_channel_app.return_value = {
            "uuid": "wwc-new-uuid"
        }
        self.usecase.integrations_service.configure_channel_app.return_value = {
            "uuid": "wwc-new-uuid"
        }

        self.usecase.execute(self._build_dto(channel="wwc", channel_data={}))

        self.usecase.integrations_service.configure_channel_app.assert_called_once()
        call_args = self.usecase.integrations_service.configure_channel_app.call_args
        self.assertEqual(call_args[0][0], "wwc")
        self.assertEqual(call_args[0][1], "wwc-new-uuid")

    @patch(
        "retail.projects.usecases.install_channel_agents.get_channel_agents",
        return_value=[],
    )
    def test_wpp_cloud_skips_configure_step(self, _mock_agents):
        """WPP-Cloud channels do not need a separate configure step."""
        self.usecase.integrations_service.create_wpp_cloud_channel.return_value = {
            "app_uuid": "wpp-app-uuid",
            "flow_object_uuid": "wpp-channel-uuid",
        }

        self.usecase.execute(self._build_dto())

        self.usecase.integrations_service.configure_channel_app.assert_not_called()

    @patch(
        "retail.projects.usecases.install_channel_agents.get_channel_agents",
        return_value=[],
    )
    def test_raises_error_when_wwc_configure_fails(self, _mock_agents):
        """Should raise when WWC configure step fails."""
        self.usecase.integrations_service.create_channel_app.return_value = {
            "uuid": "wwc-new-uuid"
        }
        self.usecase.integrations_service.configure_channel_app.return_value = None

        with self.assertRaises(InstallChannelAgentsError) as ctx:
            self.usecase.execute(self._build_dto(channel="wwc", channel_data={}))

        self.assertIn("Failed to configure", str(ctx.exception))
