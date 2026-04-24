from unittest.mock import MagicMock

from uuid import uuid4

from django.test import TestCase

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.broadcasts.models import BroadcastMessage, BroadcastStatus
from retail.broadcasts.usecases.record_broadcast_sent import (
    RecordBroadcastSentDTO,
    RecordBroadcastSentUseCase,
)
from retail.projects.models import Project


class RecordBroadcastSentUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Project A", uuid=uuid4())
        self.agent = Agent.objects.create(name="Agent A", project=self.project)
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
        )
        self.use_case = RecordBroadcastSentUseCase()

    def _template(
        self, name="abandoned_cart", version="weni_abandoned_cart_1768996789226396"
    ):
        template = MagicMock()
        template.name = name
        template.current_version.template_name = version
        return template

    def _build_dto(self, **overrides):
        defaults = dict(
            broadcast_id=12345,
            integrated_agent=self.integrated_agent,
            template=self._template(),
            contact_urn="whatsapp:5511999999999",
            channel_uuid=str(self.integrated_agent.channel_uuid),
            flows_template_uuid="0fb99299-3553-4c40-b174-6a66c647c12e",
            flows_response={"id": 12345},
        )
        defaults.update(overrides)
        return RecordBroadcastSentDTO(**defaults)

    def test_persists_broadcast_with_template_identity_split(self):
        result = self.use_case.execute(self._build_dto())

        self.assertIsNotNone(result)
        self.assertEqual(BroadcastMessage.objects.count(), 1)
        row = BroadcastMessage.objects.get()
        self.assertEqual(row.broadcast_id, 12345)
        self.assertEqual(row.project_id, self.project.pk)
        self.assertEqual(row.integrated_agent_id, self.integrated_agent.pk)
        self.assertEqual(row.status, BroadcastStatus.SENT)
        self.assertEqual(row.contact_urn, "whatsapp:5511999999999")
        self.assertEqual(row.template_name, "abandoned_cart")
        self.assertEqual(row.template_version, "weni_abandoned_cart_1768996789226396")
        self.assertEqual(
            str(row.flows_template_uuid), "0fb99299-3553-4c40-b174-6a66c647c12e"
        )

    def test_persists_even_when_broadcast_id_is_missing(self):
        result = self.use_case.execute(self._build_dto(broadcast_id=None))

        self.assertIsNotNone(result)
        row = BroadcastMessage.objects.get()
        self.assertIsNone(row.broadcast_id)

    def test_persists_when_template_is_missing(self):
        result = self.use_case.execute(
            self._build_dto(template=None, flows_template_uuid=None)
        )

        self.assertIsNotNone(result)
        row = BroadcastMessage.objects.get()
        self.assertEqual(row.template_name, "")
        self.assertEqual(row.template_version, "")
        self.assertIsNone(row.flows_template_uuid)

    def test_records_failed_when_broadcast_id_is_missing(self):
        result = self.use_case.execute(self._build_dto(broadcast_id=None))

        self.assertIsNotNone(result)
        row = BroadcastMessage.objects.get()
        self.assertEqual(row.status, BroadcastStatus.FAILED)
        self.assertIn("broadcast_id", row.error_message)

    def test_records_failed_when_error_message_is_provided(self):
        result = self.use_case.execute(
            self._build_dto(
                broadcast_id=None,
                error_message="ConnectionError: timeout",
                flows_response={"error": "ConnectionError: timeout"},
            )
        )

        self.assertIsNotNone(result)
        row = BroadcastMessage.objects.get()
        self.assertEqual(row.status, BroadcastStatus.FAILED)
        self.assertEqual(row.error_message, "ConnectionError: timeout")
        self.assertEqual(
            row.last_payload,
            {"flows_response": {"error": "ConnectionError: timeout"}},
        )
