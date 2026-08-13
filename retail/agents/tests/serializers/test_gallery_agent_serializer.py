from django.test import TestCase
from django.utils import timezone

from uuid import uuid4

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_management.serializers import GalleryAgentSerializer
from retail.projects.models import Project


class GalleryAgentSerializerTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Project", uuid=uuid4())
        self.agent = Agent.objects.create(
            name="Cart Recovery",
            slug="active_cart_abandonment",
            description="Abandoned cart agent",
            project=self.project,
            is_oficial=True,
        )

    def test_assigned_gallery_agent_exposes_integrated_identifiers(self):
        channel_uuid = uuid4()
        integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=channel_uuid,
            is_active=True,
        )

        data = GalleryAgentSerializer(
            self.agent,
            context={"project_uuid": str(self.project.uuid)},
        ).data

        self.assertTrue(data["assigned"])
        self.assertEqual(data["assigned_agent_uuid"], str(integrated_agent.uuid))
        self.assertEqual(data["channel_uuid"], str(channel_uuid))
        self.assertIsNone(data["first_successful_sent_at"])

    def test_assigned_gallery_agent_returns_first_successful_sent_at(self):
        stamped = timezone.now()
        integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            is_active=True,
            first_successful_sent_at=stamped,
        )
        integrated_agent.refresh_from_db()

        data = GalleryAgentSerializer(
            self.agent,
            context={"project_uuid": str(self.project.uuid)},
        ).data

        self.assertEqual(
            data["first_successful_sent_at"],
            integrated_agent.first_successful_sent_at,
        )

    def test_unassigned_gallery_agent_returns_null_integrated_identifiers(self):
        data = GalleryAgentSerializer(
            self.agent,
            context={"project_uuid": str(self.project.uuid)},
        ).data

        self.assertFalse(data["assigned"])
        self.assertIsNone(data["assigned_agent_uuid"])
        self.assertIsNone(data["channel_uuid"])
        self.assertIsNone(data["first_successful_sent_at"])
        data = GalleryAgentSerializer(
            self.agent,
            context={"project_uuid": str(self.project.uuid)},
        ).data

        self.assertFalse(data["assigned"])
        self.assertIsNone(data["assigned_agent_uuid"])
        self.assertIsNone(data["channel_uuid"])
