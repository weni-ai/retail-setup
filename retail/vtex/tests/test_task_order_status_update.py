"""Tests for ``task_order_status_update``.

Mirrors the structure of
``retail/agents/domains/agent_execution/tests/test_task_agent_webhook.py``
and pins down each branch of the task entrypoint:

- Project missing for the VTEX account → early return, no agent calls.
- Payment approved → ``handle_purchase_event_task.apply_async`` is
  scheduled on the ``vtex-io-orders-update-events`` queue.
- Integrated agent present → ``log_webhook_received`` is called and the
  agent use case ``execute`` runs.
- No integrated agent → legacy ``OrderStatusUseCase.process_notification``
  runs instead.
- ``ValidationError`` is swallowed (so beat-driven retries don't crash).
- Any other unexpected error after an execution UUID was minted hits
  ``log_execution_error`` with the stored UUID.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from retail.agents.domains.agent_execution.context import (
    clear_execution_context,
    set_current_execution_uuid,
)


def _mock_log_webhook_received(execution_uuid):
    """Build a ``log_webhook_received`` side effect that mirrors prod.

    The real service sets the execution UUID into the contextvar so
    downstream calls can pick it up without explicit threading; mocks
    need to do the same for the task-error path to find the active
    execution.
    """

    def _set_and_return(*args, **kwargs):
        set_current_execution_uuid(execution_uuid)
        return execution_uuid

    return _set_and_return


def _build_order_update_data(state: str = "invoiced") -> dict:
    return {
        "recorder": {},
        "domain": "Marketplace",
        "orderId": "order-123",
        "currentState": state,
        "lastState": "ready-for-handling",
        "currentChangeDate": "2024-01-01T00:00:00",
        "lastChangeDate": "2024-01-01T00:00:00",
        "vtexAccount": "acct",
    }


class TaskOrderStatusUpdateTests(TestCase):
    """Cover every branch of ``task_order_status_update``."""

    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)

    @patch("retail.vtex.tasks.AgentOrderStatusUpdateUsecase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_returns_early_when_project_not_found(
        self, mock_logger_factory, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_order_status_update

        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        mock_use_case = MagicMock()
        mock_use_case.get_project_by_vtex_account.return_value = None
        mock_use_case_cls.return_value = mock_use_case

        task_order_status_update(_build_order_update_data())

        mock_use_case.get_integrated_agent_if_exists.assert_not_called()
        mock_use_case.execute.assert_not_called()
        mock_logger.log_webhook_received.assert_not_called()
        mock_logger.log_execution_error.assert_not_called()

    @patch("retail.vtex.tasks.handle_purchase_event_task")
    @patch("retail.vtex.tasks.AgentOrderStatusUpdateUsecase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_payment_approved_dispatches_handle_purchase_event(
        self, mock_logger_factory, mock_use_case_cls, mock_handle_task
    ):
        from retail.vtex.tasks import task_order_status_update

        mock_logger = MagicMock()
        mock_logger.log_webhook_received.return_value = uuid4()
        mock_logger_factory.return_value = mock_logger

        project = MagicMock(uuid=uuid4())
        agent = MagicMock(uuid=uuid4())
        mock_use_case = MagicMock()
        mock_use_case.get_project_by_vtex_account.return_value = project
        mock_use_case.get_integrated_agent_if_exists.return_value = agent
        mock_use_case_cls.return_value = mock_use_case

        order_data = _build_order_update_data(state="payment-approved")
        task_order_status_update(order_data)

        mock_handle_task.apply_async.assert_called_once_with(
            args=[order_data["orderId"], str(project.uuid)],
            queue="vtex-io-orders-update-events",
        )

    @patch("retail.vtex.tasks.handle_purchase_event_task")
    @patch("retail.vtex.tasks.AgentOrderStatusUpdateUsecase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_non_payment_approved_does_not_dispatch_handle_purchase_event(
        self, mock_logger_factory, mock_use_case_cls, mock_handle_task
    ):
        from retail.vtex.tasks import task_order_status_update

        mock_logger = MagicMock()
        mock_logger.log_webhook_received.return_value = uuid4()
        mock_logger_factory.return_value = mock_logger

        mock_use_case = MagicMock()
        mock_use_case.get_project_by_vtex_account.return_value = MagicMock(uuid=uuid4())
        mock_use_case.get_integrated_agent_if_exists.return_value = MagicMock(
            uuid=uuid4()
        )
        mock_use_case_cls.return_value = mock_use_case

        task_order_status_update(_build_order_update_data(state="invoiced"))

        mock_handle_task.apply_async.assert_not_called()

    @patch("retail.vtex.tasks.AgentOrderStatusUpdateUsecase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_runs_agent_path_when_integrated_agent_exists(
        self, mock_logger_factory, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_order_status_update

        execution_uuid = uuid4()
        mock_logger = MagicMock()
        mock_logger.log_webhook_received.side_effect = _mock_log_webhook_received(execution_uuid)
        mock_logger_factory.return_value = mock_logger

        project = MagicMock(uuid=uuid4())
        agent = MagicMock(uuid=uuid4())
        mock_use_case = MagicMock()
        mock_use_case.get_project_by_vtex_account.return_value = project
        mock_use_case.get_integrated_agent_if_exists.return_value = agent
        mock_use_case_cls.return_value = mock_use_case

        order_data = _build_order_update_data()
        task_order_status_update(order_data)

        mock_logger.log_webhook_received.assert_called_once()
        kwargs = mock_logger.log_webhook_received.call_args.kwargs
        self.assertEqual(kwargs.get("integrated_agent"), agent)
        self.assertEqual(kwargs.get("payload"), order_data)
        self.assertEqual(kwargs.get("order_id"), order_data["orderId"])

        mock_use_case.execute.assert_called_once()
        execute_args = mock_use_case.execute.call_args.args
        self.assertEqual(execute_args[0], agent)

    @patch("retail.vtex.tasks.OrderStatusUseCase")
    @patch("retail.vtex.tasks.AgentOrderStatusUpdateUsecase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_falls_back_to_legacy_use_case_when_no_integrated_agent(
        self, mock_logger_factory, mock_use_case_cls, mock_legacy_cls
    ):
        from retail.vtex.tasks import task_order_status_update

        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        project = MagicMock(uuid=uuid4())
        mock_use_case = MagicMock()
        mock_use_case.get_project_by_vtex_account.return_value = project
        mock_use_case.get_integrated_agent_if_exists.return_value = None
        mock_use_case_cls.return_value = mock_use_case

        legacy_use_case = MagicMock()
        mock_legacy_cls.return_value = legacy_use_case

        task_order_status_update(_build_order_update_data())

        mock_legacy_cls.assert_called_once()
        legacy_use_case.process_notification.assert_called_once_with(project)
        mock_logger.log_webhook_received.assert_not_called()
        mock_use_case.execute.assert_not_called()

    @patch("retail.vtex.tasks.AgentOrderStatusUpdateUsecase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_validation_error_is_swallowed(
        self, mock_logger_factory, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_order_status_update

        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        mock_use_case = MagicMock()
        mock_use_case.get_project_by_vtex_account.side_effect = ValidationError("boom")
        mock_use_case_cls.return_value = mock_use_case

        # Must not raise — `ValidationError` is intentionally swallowed.
        task_order_status_update(_build_order_update_data())

        mock_logger.log_execution_error.assert_not_called()

    @patch("retail.vtex.tasks.AgentOrderStatusUpdateUsecase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_validation_error_is_logged_when_execution_uuid_exists(
        self, mock_logger_factory, mock_use_case_cls
    ):
        """If a ValidationError fires AFTER ``log_webhook_received``
        already minted an execution UUID, the row would otherwise time
        out at the ZSET deadline. The task must close it as ``error``
        before swallowing the exception."""
        from retail.vtex.tasks import task_order_status_update

        execution_uuid = uuid4()
        mock_logger = MagicMock()
        mock_logger.log_webhook_received.side_effect = _mock_log_webhook_received(execution_uuid)
        mock_logger_factory.return_value = mock_logger

        project = MagicMock(uuid=uuid4())
        agent = MagicMock(uuid=uuid4())
        mock_use_case = MagicMock()
        mock_use_case.get_project_by_vtex_account.return_value = project
        mock_use_case.get_integrated_agent_if_exists.return_value = agent
        mock_use_case.execute.side_effect = ValidationError("downstream invalid")
        mock_use_case_cls.return_value = mock_use_case

        order_data = _build_order_update_data()
        # Must not raise — ValidationError is still swallowed.
        task_order_status_update(order_data)

        mock_logger.log_execution_error.assert_called_once()
        kwargs = mock_logger.log_execution_error.call_args.kwargs
        self.assertEqual(kwargs.get("execution_uuid"), execution_uuid)
        self.assertIn("downstream invalid", kwargs.get("error_message", ""))
        self.assertEqual(kwargs.get("error_data"), {"order_update_data": order_data})

    @patch("retail.vtex.tasks.AgentOrderStatusUpdateUsecase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_unexpected_error_after_execution_uuid_logs_error(
        self, mock_logger_factory, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_order_status_update

        execution_uuid = uuid4()
        mock_logger = MagicMock()
        mock_logger.log_webhook_received.side_effect = _mock_log_webhook_received(execution_uuid)
        mock_logger_factory.return_value = mock_logger

        project = MagicMock(uuid=uuid4())
        agent = MagicMock(uuid=uuid4())
        mock_use_case = MagicMock()
        mock_use_case.get_project_by_vtex_account.return_value = project
        mock_use_case.get_integrated_agent_if_exists.return_value = agent
        mock_use_case.execute.side_effect = RuntimeError("boom")
        mock_use_case_cls.return_value = mock_use_case

        order_data = _build_order_update_data()
        task_order_status_update(order_data)

        mock_logger.log_execution_error.assert_called_once()
        kwargs = mock_logger.log_execution_error.call_args.kwargs
        self.assertEqual(kwargs.get("execution_uuid"), execution_uuid)
        self.assertEqual(kwargs.get("error_message"), "boom")
        self.assertEqual(kwargs.get("error_data"), {"order_update_data": order_data})

    @patch("retail.vtex.tasks.AgentOrderStatusUpdateUsecase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_unexpected_error_without_execution_uuid_does_not_log(
        self, mock_logger_factory, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_order_status_update

        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        mock_use_case = MagicMock()
        # Raise BEFORE we have the chance to mint an execution_uuid.
        mock_use_case.get_project_by_vtex_account.side_effect = RuntimeError("boom")
        mock_use_case_cls.return_value = mock_use_case

        # Must not raise — top-level except logs and returns.
        task_order_status_update(_build_order_update_data())

        mock_logger.log_execution_error.assert_not_called()
