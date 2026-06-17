from decimal import Decimal
from uuid import uuid4

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.broadcasts.models import (
    BroadcastConversion,
    BroadcastMessage,
    BroadcastStatus,
    ProjectBroadcastCounter,
)
from retail.projects.models import Project


class ProjectBroadcastCounterReprTest(TestCase):
    """Covers the two branches of __str__ used by Django admin and logs."""

    def setUp(self):
        self.project = Project.objects.create(name="Project A", uuid=uuid4())

    def test_repr_when_not_blocked(self):
        counter = ProjectBroadcastCounter.objects.create(
            project=self.project, total_delivered=42
        )
        text = str(counter)

        self.assertIn(str(self.project.uuid), text)
        self.assertIn("total_delivered=42", text)
        self.assertIn("blocked=False", text)

    def test_repr_when_blocked(self):
        counter = ProjectBroadcastCounter.objects.create(
            project=self.project,
            total_delivered=100,
            blocked_at=timezone.now(),
        )
        text = str(counter)

        self.assertIn(str(self.project.uuid), text)
        self.assertIn("total_delivered=100", text)
        self.assertIn("blocked_at=", text)
        self.assertNotIn("blocked=False", text)


class BroadcastMessageOrderIdentifiersTest(TestCase):
    """Schema-level checks for the commercial-origin columns.

    The conversion attribution itself lives on ``BroadcastConversion``;
    these columns just capture what the dispatch knew at send time so
    a later ``invoiced`` event can be matched back.
    """

    def setUp(self):
        self.project = Project.objects.create(name="Project A", uuid=uuid4())
        self.agent = Agent.objects.create(name="Agent A", project=self.project)
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
        )

    def test_defaults_are_null(self):
        broadcast = BroadcastMessage.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            status=BroadcastStatus.QUEUED,
        )

        self.assertIsNone(broadcast.order_form_id)
        self.assertIsNone(broadcast.order_id)

    def test_persists_both_identifiers_when_supplied(self):
        broadcast = BroadcastMessage.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            status=BroadcastStatus.DELIVERED,
            order_id="order-9",
            order_form_id="of-9",
        )

        broadcast.refresh_from_db()
        self.assertEqual(broadcast.order_id, "order-9")
        self.assertEqual(broadcast.order_form_id, "of-9")


class BroadcastConversionTest(TestCase):
    """Schema-level tests for the conversion table.

    Validates defaults, Decimal round-trip, the unique constraint on
    ``(project, order_id)`` (idempotency at the DB level), and the
    string representation used by Django admin/logs.
    """

    def setUp(self):
        self.project = Project.objects.create(name="Project A", uuid=uuid4())
        self.other_project = Project.objects.create(name="Project B", uuid=uuid4())
        self.agent = Agent.objects.create(name="Agent A", project=self.project)
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
        )

    def test_defaults_for_optional_fields(self):
        conversion = BroadcastConversion.objects.create(
            project=self.project,
            order_id="order-42",
        )

        self.assertIsNone(conversion.integrated_agent)
        self.assertIsNone(conversion.order_form_id)
        self.assertIsNone(conversion.value)
        self.assertEqual(conversion.currency, "")
        self.assertIsNone(conversion.order_created_at)
        self.assertIsNone(conversion.payment_at)
        self.assertEqual(conversion.payment_type, "")
        self.assertIsNotNone(conversion.converted_at)

    def test_persists_full_payload(self):
        order_created_at = timezone.now()
        payment_at = timezone.now()
        conversion = BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            order_id="order-1",
            order_form_id="of-1",
            value=Decimal("199.99"),
            currency="BRL",
            order_created_at=order_created_at,
            payment_at=payment_at,
            payment_type="Pix",
        )

        conversion.refresh_from_db()
        self.assertEqual(conversion.integrated_agent, self.integrated_agent)
        self.assertEqual(conversion.order_id, "order-1")
        self.assertEqual(conversion.order_form_id, "of-1")
        self.assertEqual(conversion.value, Decimal("199.99"))
        self.assertEqual(conversion.currency, "BRL")
        self.assertEqual(conversion.order_created_at, order_created_at)
        self.assertEqual(conversion.payment_at, payment_at)
        self.assertEqual(conversion.payment_type, "Pix")

    def test_unique_constraint_on_project_and_order_id(self):
        BroadcastConversion.objects.create(
            project=self.project, order_id="order-duplicate"
        )

        with self.assertRaises(IntegrityError):
            BroadcastConversion.objects.create(
                project=self.project, order_id="order-duplicate"
            )

    def test_same_order_id_allowed_across_projects(self):
        """Multi-tenant safety: VTEX order ids may collide between
        VTEX accounts, so the constraint scope is (project, order_id)
        rather than order_id alone."""
        BroadcastConversion.objects.create(
            project=self.project, order_id="order-shared"
        )
        BroadcastConversion.objects.create(
            project=self.other_project, order_id="order-shared"
        )

        self.assertEqual(BroadcastConversion.objects.count(), 2)

    def test_repr_includes_uuid_and_order_id(self):
        conversion = BroadcastConversion.objects.create(
            project=self.project, order_id="order-repr"
        )

        text = str(conversion)
        self.assertIn(str(conversion.uuid), text)
        self.assertIn("order-repr", text)
