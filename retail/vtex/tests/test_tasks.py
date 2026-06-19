from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project
from retail.vtex.tasks import (
    _is_purchase_confirmed,
    is_payment_approved,
    task_mark_broadcast_converted,
    task_order_status_update,
)


class IsPurchaseConfirmedTest(TestCase):
    """Guards the canonical set of VTEX states that confirm a purchase.

    Kept in sync with ``PURCHASED_ORDER_STATUSES`` used by the cart
    abandonment service; widening this set is a deliberate decision
    that should also update the abandonment filter.
    """

    def test_invoiced_is_a_confirmed_purchase(self):
        self.assertTrue(_is_purchase_confirmed("invoiced"))

    def test_intermediate_states_are_not_confirmed_purchases(self):
        for state in (
            "order-created",
            "ready-for-handling",
            "payment-approved",
            "payment-pending",
            "canceled",
            "",
        ):
            self.assertFalse(_is_purchase_confirmed(state), state)

    def test_payment_approved_is_distinct_from_invoiced(self):
        """Sanity guard against accidentally collapsing the two
        triggers (CAPI vs broadcast conversion) into the same state."""
        self.assertTrue(is_payment_approved("payment-approved"))
        self.assertFalse(_is_purchase_confirmed("payment-approved"))


class TaskOrderStatusUpdateConversionTriggerTest(TestCase):
    """Validates that the ``invoiced`` state schedules the conversion
    attribution task without coupling it to the CAPI flow or the agent
    webhook flow.
    """

    def setUp(self):
        self.project = Project.objects.create(
            name="Project A", uuid=uuid4(), vtex_account="testaccount"
        )
        self.dto_payload = {
            "recorder": {},
            "domain": "Marketplace",
            "orderId": "order-99",
            "currentState": "invoiced",
            "lastState": "ready-for-handling",
            "currentChangeDate": "2026-05-07T12:00:00",
            "lastChangeDate": "2026-05-07T11:55:00",
            "vtexAccount": "testaccount",
        }

    @patch("retail.vtex.tasks.task_mark_broadcast_converted.apply_async")
    @patch("retail.vtex.tasks.AgentOrderStatusUpdateUsecase")
    def test_invoiced_schedules_conversion_task(
        self, mock_use_case_cls, mock_apply_async
    ):
        mock_use_case = MagicMock()
        mock_use_case.get_project_by_vtex_account.return_value = self.project
        mock_use_case.get_integrated_agent_if_exists.return_value = None
        mock_use_case_cls.return_value = mock_use_case

        task_order_status_update(self.dto_payload)

        mock_apply_async.assert_called_once_with(
            args=["order-99", str(self.project.uuid)],
            queue="vtex-io-orders-update-events",
        )

    @patch("retail.vtex.tasks.task_mark_broadcast_converted.apply_async")
    @patch("retail.vtex.tasks.AgentOrderStatusUpdateUsecase")
    def test_non_invoiced_does_not_schedule_conversion_task(
        self, mock_use_case_cls, mock_apply_async
    ):
        mock_use_case = MagicMock()
        mock_use_case.get_project_by_vtex_account.return_value = self.project
        mock_use_case.get_integrated_agent_if_exists.return_value = None
        mock_use_case_cls.return_value = mock_use_case

        for state in ("order-created", "payment-approved", "canceled"):
            mock_apply_async.reset_mock()
            payload = dict(self.dto_payload, currentState=state)

            task_order_status_update(payload)

            mock_apply_async.assert_not_called()

    @patch("retail.vtex.tasks.task_mark_broadcast_converted.apply_async")
    @patch("retail.vtex.tasks.handle_purchase_event_task.apply_async")
    @patch("retail.vtex.tasks.AgentOrderStatusUpdateUsecase")
    def test_payment_approved_schedules_capi_but_not_conversion(
        self,
        mock_use_case_cls,
        mock_capi_apply_async,
        mock_conversion_apply_async,
    ):
        """CAPI (payment-approved) and broadcast conversion (invoiced)
        are independent triggers; one must not imply the other."""
        mock_use_case = MagicMock()
        mock_use_case.get_project_by_vtex_account.return_value = self.project
        mock_use_case.get_integrated_agent_if_exists.return_value = None
        mock_use_case_cls.return_value = mock_use_case

        payload = dict(self.dto_payload, currentState="payment-approved")
        task_order_status_update(payload)

        mock_capi_apply_async.assert_called_once()
        mock_conversion_apply_async.assert_not_called()

    @patch("retail.vtex.tasks.task_mark_broadcast_converted.apply_async")
    @patch("retail.vtex.tasks.AgentOrderStatusUpdateUsecase")
    def test_skips_conversion_when_project_not_found(
        self, mock_use_case_cls, mock_apply_async
    ):
        mock_use_case = MagicMock()
        mock_use_case.get_project_by_vtex_account.return_value = None
        mock_use_case_cls.return_value = mock_use_case

        task_order_status_update(self.dto_payload)

        mock_apply_async.assert_not_called()


class TaskMarkBroadcastConvertedTest(TestCase):
    """Smoke test that the Celery task is a thin wrapper around the
    use case; the use case has its own dedicated test suite."""

    @patch("retail.vtex.tasks.MarkBroadcastConvertedUseCase")
    def test_delegates_to_use_case(self, mock_use_case_cls):
        mock_instance = MagicMock()
        mock_use_case_cls.return_value = mock_instance

        task_mark_broadcast_converted("order-1", "project-uuid-1")

        mock_use_case_cls.assert_called_once_with()
        mock_instance.execute.assert_called_once_with(
            order_id="order-1", project_uuid="project-uuid-1"
        )
