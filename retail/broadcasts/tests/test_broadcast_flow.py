"""Full broadcast lifecycle integration test.

Tests the end-to-end flow without mocking internal layers:

  1. Dispatch recorded  → BroadcastMessage(status=SENT) created
  2. Courier create event → broadcast_id linked to Meta message_id
  3. Status events        → transitions logged (sent → delivered)
  4. DELIVERED transition → project + agent counters incremented
  5. Limit reached        → project.is_blocked=True, suspension invoked

Only TrialSuspensionService.suspend is mocked (external call to Connect).
All DB models are real; no patches on internal use cases.
"""
from unittest.mock import MagicMock

from uuid import uuid4

from django.test import TestCase, override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.broadcasts.models import (
    BroadcastMessage,
    BroadcastStatus,
    ProjectBroadcastCounter,
)
from retail.broadcasts.usecases.handle_status_update import (
    BroadcastStatusEvent,
    HandleStatusUpdateUseCase,
)
from retail.broadcasts.usecases.record_broadcast_sent import (
    RecordBroadcastSentDTO,
    RecordBroadcastSentUseCase,
)
from retail.projects.models import Project


class BroadcastLifecycleFlowTest(TestCase):
    """Simulates a single broadcast from dispatch to delivery."""

    BROADCAST_ID = 171535537
    EXTERNAL_MESSAGE_ID = "msg-20260422-001"

    def setUp(self):
        self.project = Project.objects.create(name="Store A", uuid=uuid4())
        self.agent = Agent.objects.create(
            name="Abandoned Cart Agent", project=self.project
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
        )
        self.flows_response = {
            "id": self.BROADCAST_ID,
            "status": "sent",
            "urns": ["whatsapp:5511950944479"],
            "channel": 15387,
            "metadata": {
                "template": {
                    "name": "weni_abandoned_cart_1768996789226396",
                    "uuid": "0fb99299-3553-4c40-b174-6a66c647c12e",
                }
            },
        }
        self.record_use_case = RecordBroadcastSentUseCase()
        # Inject mocked services so we can assert behavior without
        # hitting Connect for trial status nor for suspension.
        self.mock_suspension = MagicMock()
        self.mock_trial_status = MagicMock()
        self.mock_trial_status.is_trial_active.return_value = True

        from retail.broadcasts.services.broadcast_limit_resolver import (
            BroadcastLimitResolver,
        )
        from retail.broadcasts.usecases.project_limit_guard import ProjectLimitGuard

        self.use_case = HandleStatusUpdateUseCase(
            limit_guard=ProjectLimitGuard(
                limit_resolver=BroadcastLimitResolver(
                    trial_status_service=self.mock_trial_status
                ),
                suspension_service=self.mock_suspension,
            )
        )

    # ------------------------------------------------------------------
    # Step 1: dispatch
    # ------------------------------------------------------------------

    def _dispatch(self) -> BroadcastMessage:
        dto = RecordBroadcastSentDTO(
            broadcast_id=self.BROADCAST_ID,
            integrated_agent=self.integrated_agent,
            template=None,
            contact_urn="whatsapp:5511950944479",
            channel_uuid=str(self.integrated_agent.channel_uuid),
            flows_template_uuid="0fb99299-3553-4c40-b174-6a66c647c12e",
            flows_response=self.flows_response,
        )
        return self.record_use_case.execute(dto)

    # ------------------------------------------------------------------
    # Step 2 & 3: courier events
    # ------------------------------------------------------------------

    def _create_event(self, status="sent") -> BroadcastStatusEvent:
        return BroadcastStatusEvent(
            broadcast_id=self.BROADCAST_ID,
            message_id=self.EXTERNAL_MESSAGE_ID,
            status=status,
            payload={
                "broadcast_id": self.BROADCAST_ID,
                "message_id": self.EXTERNAL_MESSAGE_ID,
                "status": status,
            },
        )

    def _status_event(self, status: str) -> BroadcastStatusEvent:
        return BroadcastStatusEvent(
            broadcast_id=None,
            message_id=self.EXTERNAL_MESSAGE_ID,
            status=status,
            payload={"message_id": self.EXTERNAL_MESSAGE_ID, "status": status},
        )

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_dispatch_creates_sent_broadcast_message(self):
        message = self._dispatch()

        self.assertIsNotNone(message)
        self.assertEqual(message.status, BroadcastStatus.SENT)
        self.assertEqual(message.broadcast_id, self.BROADCAST_ID)
        self.assertEqual(message.project, self.project)
        self.assertEqual(message.integrated_agent, self.integrated_agent)

    def test_create_event_links_meta_message_id(self):
        self._dispatch()

        self.use_case.execute(self._create_event(status="sent"))

        message = BroadcastMessage.objects.get(broadcast_id=self.BROADCAST_ID)
        self.assertEqual(message.external_message_id, self.EXTERNAL_MESSAGE_ID)
        self.assertEqual(message.status, BroadcastStatus.SENT)

    def test_previous_status_is_tracked_on_each_transition(self):
        self._dispatch()
        self.use_case.execute(self._create_event(status="delivered"))

        message = BroadcastMessage.objects.get(broadcast_id=self.BROADCAST_ID)
        self.assertEqual(message.status, BroadcastStatus.DELIVERED)
        self.assertEqual(message.previous_status, BroadcastStatus.SENT)

    def test_full_status_progression(self):
        self._dispatch()
        self.use_case.execute(self._create_event(status="sent"))
        self.use_case.execute(self._status_event("delivered"))

        message = BroadcastMessage.objects.get(broadcast_id=self.BROADCAST_ID)
        self.assertEqual(message.status, BroadcastStatus.DELIVERED)
        self.assertIsNotNone(message.status_updated_at)

    def test_delivered_increments_project_counter(self):
        self._dispatch()
        self.use_case.execute(self._create_event(status="sent"))
        self.use_case.execute(self._status_event("delivered"))

        counter = ProjectBroadcastCounter.objects.get(project=self.project)
        self.assertEqual(counter.total_delivered, 1)

    def test_delivered_increments_agent_counter(self):
        self._dispatch()
        self.use_case.execute(self._create_event(status="sent"))
        self.use_case.execute(self._status_event("delivered"))

        self.integrated_agent.refresh_from_db()
        self.assertEqual(self.integrated_agent.broadcasts_delivered, 1)

    def test_replay_delivered_does_not_double_count(self):
        self._dispatch()
        self.use_case.execute(self._create_event(status="sent"))
        delivered = self._status_event("delivered")
        self.use_case.execute(delivered)
        self.use_case.execute(delivered)
        self.use_case.execute(delivered)

        counter = ProjectBroadcastCounter.objects.get(project=self.project)
        self.assertEqual(counter.total_delivered, 1)

    def test_unknown_status_saved_not_dropped(self):
        self._dispatch()
        self.use_case.execute(self._create_event(status="sent"))
        self.use_case.execute(self._status_event("some-future-courier-status"))

        message = BroadcastMessage.objects.get(broadcast_id=self.BROADCAST_ID)
        self.assertEqual(message.status, BroadcastStatus.UNKNOWN)

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1)
    def test_reaching_dispatch_limit_blocks_project(self):
        self._dispatch()
        self.use_case.execute(self._create_event(status="sent"))
        self.use_case.execute(self._status_event("delivered"))

        self.project.refresh_from_db()
        self.assertTrue(self.project.is_blocked)

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1)
    def test_reaching_limit_invokes_suspension_service(self):
        self._dispatch()
        self.use_case.execute(self._create_event(status="sent"))
        self.use_case.execute(self._status_event("delivered"))

        self.mock_suspension.suspend.assert_called_once_with(
            project_uuid=str(self.project.uuid), limit=1
        )

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=2)
    def test_below_limit_does_not_block_project(self):
        self._dispatch()
        self.use_case.execute(self._create_event(status="sent"))
        self.use_case.execute(self._status_event("delivered"))

        self.project.refresh_from_db()
        self.assertFalse(self.project.is_blocked)
        self.mock_suspension.suspend.assert_not_called()

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1)
    def test_blocked_project_counter_has_blocked_at_set(self):
        self._dispatch()
        self.use_case.execute(self._create_event(status="sent"))
        self.use_case.execute(self._status_event("delivered"))

        counter = ProjectBroadcastCounter.objects.get(project=self.project)
        self.assertIsNotNone(counter.blocked_at)


class BroadcastFlowUnknownEventTest(TestCase):
    """Events that do not match any local broadcast are silently ignored."""

    def setUp(self):
        self.project = Project.objects.create(name="Store B", uuid=uuid4())
        self.use_case = HandleStatusUpdateUseCase()

    def test_create_event_for_unknown_broadcast_id_creates_no_rows(self):
        event = BroadcastStatusEvent(
            broadcast_id=99999999,
            message_id="ext-unknown",
            status="sent",
            payload={},
        )
        self.use_case.execute(event)

        self.assertEqual(BroadcastMessage.objects.count(), 0)

    def test_status_event_for_unknown_message_id_creates_no_rows(self):
        event = BroadcastStatusEvent(
            broadcast_id=None,
            message_id="ext-unknown",
            status="delivered",
            payload={},
        )
        self.use_case.execute(event)

        self.assertEqual(BroadcastMessage.objects.count(), 0)
        self.assertFalse(ProjectBroadcastCounter.objects.exists())
