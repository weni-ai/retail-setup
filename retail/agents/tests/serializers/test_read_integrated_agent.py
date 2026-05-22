"""Tests for ``ReadIntegratedAgentSerializer.direct_send`` (T019).

Pins the read-only ``direct_send`` field exposed on the integrated
agent read serializer, computed from
``obj.config.get("direct_send", False)`` per data-model.md §1
Decision (the wire shape is unchanged from US1's first
implementation; storage relocation is invisible to the consumer).
"""

from uuid import uuid4

from django.test import TestCase

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.serializers import (
    ReadIntegratedAgentSerializer,
)
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project


class ReadIntegratedAgentSerializerDirectSendTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(uuid=uuid4(), name="P")
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="A",
            project=self.project,
            credentials={},
        )

    def _build_integrated_agent(self, config):
        return IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
            is_active=True,
            config=config,
        )

    def test_serialized_output_includes_direct_send_true(self):
        ia = self._build_integrated_agent({"direct_send": True})
        data = ReadIntegratedAgentSerializer(ia).data
        self.assertTrue(data["direct_send"])

    def test_serialized_output_includes_direct_send_false_when_explicit(self):
        ia = self._build_integrated_agent({"direct_send": False})
        data = ReadIntegratedAgentSerializer(ia).data
        self.assertFalse(data["direct_send"])

    def test_serialized_output_defaults_to_false_when_key_absent(self):
        ia = self._build_integrated_agent({})
        data = ReadIntegratedAgentSerializer(ia).data
        self.assertFalse(data["direct_send"])
