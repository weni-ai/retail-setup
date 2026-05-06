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
from retail.projects.models import Project


class HandleStatusUpdateUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Project A", uuid=uuid4())
        self.agent = Agent.objects.create(name="Agent A", project=self.project)
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent, project=self.project
        )
        self.broadcast_id = 42058
        self.external_message_id = "msg-20260422-001"
        self.message = BroadcastMessage.objects.create(
            broadcast_id=self.broadcast_id,
            project=self.project,
            integrated_agent=self.integrated_agent,
            status=BroadcastStatus.SENT,
        )
        self.limit_guard = MagicMock()
        self.limit_guard.should_block.return_value = False
        self.use_case = HandleStatusUpdateUseCase(limit_guard=self.limit_guard)

    def _event(self, **kwargs):
        defaults = dict(
            message_id=self.external_message_id,
            broadcast_id=self.broadcast_id,
            status=BroadcastStatus.SENT,
            payload={"message_id": self.external_message_id},
        )
        defaults.update(kwargs)
        return BroadcastStatusEvent(**defaults)

    def test_create_event_links_message_id_and_updates_status(self):
        event = self._event(status=BroadcastStatus.SENT)

        self.use_case.execute(event)

        self.message.refresh_from_db()
        self.assertEqual(self.message.external_message_id, self.external_message_id)
        self.assertEqual(self.message.status, BroadcastStatus.SENT)
        self.assertIsNotNone(self.message.status_updated_at)

    def test_transition_persists_previous_status_field(self):
        """Verifies that previous_status is saved to the model on every transition."""
        event = self._event(status=BroadcastStatus.DELIVERED)

        self.use_case.execute(event)

        self.message.refresh_from_db()
        self.assertEqual(self.message.status, BroadcastStatus.DELIVERED)
        self.assertEqual(self.message.previous_status, BroadcastStatus.SENT)

    def test_create_event_unknown_broadcast_id_is_ignored(self):
        event = self._event(broadcast_id=999999)

        self.use_case.execute(event)

        self.assertEqual(BroadcastMessage.objects.count(), 1)
        self.message.refresh_from_db()
        self.assertIsNone(self.message.external_message_id)

    def test_status_only_event_updates_status_by_external_id(self):
        self.message.external_message_id = self.external_message_id
        self.message.save(update_fields=["external_message_id"])

        event = self._event(broadcast_id=None, status=BroadcastStatus.DELIVERED)

        self.use_case.execute(event)

        self.message.refresh_from_db()
        self.assertEqual(self.message.status, BroadcastStatus.DELIVERED)

    def test_status_only_event_unknown_message_id_is_ignored(self):
        event = self._event(broadcast_id=None, message_id="unknown-id")

        self.use_case.execute(event)

        self.message.refresh_from_db()
        self.assertEqual(self.message.status, BroadcastStatus.SENT)

    def test_delivered_transition_increments_counter_once(self):
        self.message.external_message_id = self.external_message_id
        self.message.status = BroadcastStatus.SENT
        self.message.save()

        delivered_event = self._event(
            broadcast_id=None, status=BroadcastStatus.DELIVERED
        )
        self.use_case.execute(delivered_event)
        # Replay — idempotent since status is already DELIVERED.
        self.use_case.execute(delivered_event)

        counter = ProjectBroadcastCounter.objects.get(project_id=self.project.pk)
        self.assertEqual(counter.total_delivered, 1)

    def test_delivered_transition_increments_integrated_agent_counter(self):
        self.message.external_message_id = self.external_message_id
        self.message.status = BroadcastStatus.SENT
        self.message.save()

        delivered_event = self._event(
            broadcast_id=None, status=BroadcastStatus.DELIVERED
        )
        self.use_case.execute(delivered_event)
        self.use_case.execute(delivered_event)

        self.integrated_agent.refresh_from_db()
        self.assertEqual(self.integrated_agent.broadcasts_delivered, 1)

    def test_delivered_without_integrated_agent_still_increments_project(self):
        self.message.integrated_agent = None
        self.message.external_message_id = self.external_message_id
        self.message.status = BroadcastStatus.SENT
        self.message.save()

        event = self._event(broadcast_id=None, status=BroadcastStatus.DELIVERED)
        self.use_case.execute(event)

        counter = ProjectBroadcastCounter.objects.get(project_id=self.project.pk)
        self.assertEqual(counter.total_delivered, 1)
        self.integrated_agent.refresh_from_db()
        self.assertEqual(self.integrated_agent.broadcasts_delivered, 0)

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1)
    def test_triggers_block_when_limit_reached(self):
        self.limit_guard.should_block.return_value = True
        self.message.external_message_id = self.external_message_id
        self.message.save(update_fields=["external_message_id"])

        event = self._event(broadcast_id=None, status=BroadcastStatus.DELIVERED)
        self.use_case.execute(event)

        self.limit_guard.trigger_block.assert_called_once_with(self.project.pk)

    def test_missing_ids_are_silently_ignored(self):
        event = BroadcastStatusEvent(
            message_id=None,
            broadcast_id=None,
            status=BroadcastStatus.DELIVERED,
            payload={},
        )

        self.use_case.execute(event)

        self.message.refresh_from_db()
        self.assertEqual(self.message.status, BroadcastStatus.SENT)

    def test_create_event_with_conflicting_message_id_logs_warning(self):
        """When the same broadcast_id arrives with a message_id different
        from the one we already stored, a warning is emitted and the
        new value overrides the previous one."""
        self.message.external_message_id = "previous-meta-id"
        self.message.save(update_fields=["external_message_id"])

        event = self._event(
            broadcast_id=self.broadcast_id,
            message_id="incoming-meta-id",
            status=BroadcastStatus.SENT,
        )

        with self.assertLogs(
            "retail.broadcasts.usecases.handle_status_update", level="WARNING"
        ) as captured:
            self.use_case.execute(event)

        self.assertTrue(any("message_id_conflict" in line for line in captured.output))
        self.message.refresh_from_db()
        self.assertEqual(self.message.external_message_id, "incoming-meta-id")

    def test_event_without_status_does_not_change_persisted_status(self):
        """Status-only events that arrive with no status payload are
        silently no-op."""
        self.message.external_message_id = self.external_message_id
        self.message.save(update_fields=["external_message_id"])

        event = self._event(broadcast_id=None, status=None)
        self.use_case.execute(event)

        self.message.refresh_from_db()
        self.assertEqual(self.message.status, BroadcastStatus.SENT)

    def test_failed_transition_extracts_error_from_payload(self):
        self.message.external_message_id = self.external_message_id
        self.message.save(update_fields=["external_message_id"])

        event = BroadcastStatusEvent(
            message_id=self.external_message_id,
            broadcast_id=None,
            status=BroadcastStatus.FAILED,
            payload={
                "message_id": self.external_message_id,
                "status": "F",
                "error": "channel_revoked",
            },
        )
        self.use_case.execute(event)

        self.message.refresh_from_db()
        self.assertEqual(self.message.status, BroadcastStatus.FAILED)
        self.assertEqual(self.message.error_message, "channel_revoked")

    def test_errored_transition_uses_synthetic_reason_when_payload_lacks_error(self):
        self.message.external_message_id = self.external_message_id
        self.message.save(update_fields=["external_message_id"])

        event = self._event(broadcast_id=None, status=BroadcastStatus.ERRORED)
        self.use_case.execute(event)

        self.message.refresh_from_db()
        self.assertEqual(self.message.status, BroadcastStatus.ERRORED)
        self.assertIn("status=", self.message.error_message)

    def test_unknown_status_event_persists_as_unknown(self):
        """When the consumer maps an unrecognized courier letter to UNKNOWN,
        the use case must persist it (not drop) so the payload can be
        analyzed and the enum extended later if needed."""
        self.message.external_message_id = self.external_message_id
        self.message.save(update_fields=["external_message_id"])

        event = self._event(broadcast_id=None, status=BroadcastStatus.UNKNOWN)
        self.use_case.execute(event)

        self.message.refresh_from_db()
        self.assertEqual(self.message.status, BroadcastStatus.UNKNOWN)

    def test_event_payload_is_preserved_on_transition(self):
        self.message.external_message_id = self.external_message_id
        self.message.save(update_fields=["external_message_id"])

        payload = {
            "status": "X",
            "message_id": self.external_message_id,
        }
        event = BroadcastStatusEvent(
            message_id=self.external_message_id,
            broadcast_id=None,
            status=BroadcastStatus.UNKNOWN,
            payload=payload,
        )
        self.use_case.execute(event)

        self.message.refresh_from_db()
        self.assertEqual(self.message.last_payload, payload)


class HandleStatusUpdateIdempotencyTest(TestCase):
    """Guards that the consumer does not double-count deliveries on replay."""

    def setUp(self):
        self.project = Project.objects.create(name="Project A", uuid=uuid4())
        self.message = BroadcastMessage.objects.create(
            broadcast_id=1,
            external_message_id="ext-1",
            project=self.project,
            status=BroadcastStatus.SENT,
        )
        self.use_case = HandleStatusUpdateUseCase(
            limit_guard=MagicMock(should_block=lambda _c: False)
        )

    def test_replay_delivered_does_not_double_count(self):
        event = BroadcastStatusEvent(
            message_id="ext-1",
            broadcast_id=None,
            status=BroadcastStatus.DELIVERED,
            payload={},
        )

        self.use_case.execute(event)
        self.use_case.execute(event)
        self.use_case.execute(event)

        counter = ProjectBroadcastCounter.objects.get(project_id=self.project.pk)
        self.assertEqual(counter.total_delivered, 1)
