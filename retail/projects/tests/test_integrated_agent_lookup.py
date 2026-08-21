from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project
from retail.projects.usecases.onboarding_agents.integrated_agent_lookup import (
    _extract_uuids_from_team_response,
    get_integrated_agent_uuids,
)


class TestIntegratedAgentLookup(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        self.mock_nexus_service = MagicMock()

    def test_get_integrated_agent_uuids_from_team_agents(self):
        self.mock_nexus_service.list_team_agents.return_value = {
            "manager": {"uuid": "manager-uuid", "active": True},
            "agents": [
                {"uuid": "passive-1", "active": True},
                {"uuid": "passive-2", "active": True},
            ],
        }

        result = get_integrated_agent_uuids(
            str(self.project.uuid), self.mock_nexus_service
        )

        self.assertEqual(result, {"passive-1", "passive-2"})
        self.mock_nexus_service.list_team_agents.assert_called_once_with(
            str(self.project.uuid)
        )

    def test_get_integrated_agent_uuids_includes_retail_active_agents(self):
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
        self.mock_nexus_service.list_team_agents.return_value = {"agents": []}

        result = get_integrated_agent_uuids(
            str(self.project.uuid), self.mock_nexus_service
        )

        self.assertEqual(result, {str(retail_agent.uuid)})

    def test_get_integrated_agent_uuids_returns_empty_when_team_lookup_fails(self):
        self.mock_nexus_service.list_team_agents.return_value = None

        result = get_integrated_agent_uuids(
            str(self.project.uuid), self.mock_nexus_service
        )

        self.assertEqual(result, set())

    def test_extract_uuids_includes_inactive_integrations(self):
        response = {
            "agents": [
                {"uuid": "active-agent", "active": True},
                {"uuid": "inactive-agent", "active": False},
            ]
        }

        result = _extract_uuids_from_team_response(response)

        self.assertEqual(result, {"active-agent", "inactive-agent"})
