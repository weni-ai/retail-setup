"""Tests for the explicit `execution_uuid` contract on
`task_agent_webhook`.

Some callers (cart abandonment) start the execution earlier in the
chain and pass the UUID in. Others (the async webhook view) don't,
and need the task to mint a fresh UUID via `log_webhook_received`.

These tests pin both branches:
  - With explicit `execution_uuid`: reuse it, set the contextvar,
    do NOT create a second AgentExecution.
  - Without `execution_uuid`: behave like a webhook entrypoint and
    create one.
"""

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from django.test import TestCase

from retail.agents.domains.agent_execution.context import (
    clear_execution_context,
    get_current_execution_uuid,
)


class TaskAgentWebhookExecutionUuidTests(TestCase):
    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)

    @patch("retail.vtex.tasks.AgentWebhookUseCase")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_with_explicit_uuid_does_not_create_new_execution(
        self, mock_logger_factory, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_agent_webhook

        existing_uuid = uuid4()
        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        mock_use_case = MagicMock()
        mock_agent = MagicMock(uuid=uuid4(), ignore_templates=[])
        mock_use_case._get_integrated_agent.return_value = mock_agent
        mock_use_case._addapt_credentials.return_value = {}
        mock_use_case_cls.return_value = mock_use_case

        task_agent_webhook(
            integrated_agent_uuid=str(mock_agent.uuid),
            payload={"a": 1},
            params={},
            execution_uuid=str(existing_uuid),
        )

        mock_logger.log_webhook_received.assert_not_called()

        self.assertEqual(get_current_execution_uuid(), existing_uuid)

    @patch("retail.vtex.tasks.AgentWebhookUseCase")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_without_explicit_uuid_creates_new_execution(
        self, mock_logger_factory, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_agent_webhook

        new_uuid = uuid4()
        mock_logger = MagicMock()
        mock_logger.log_webhook_received.return_value = new_uuid
        mock_logger_factory.return_value = mock_logger

        mock_use_case = MagicMock()
        mock_agent = MagicMock(uuid=uuid4(), ignore_templates=[])
        mock_use_case._get_integrated_agent.return_value = mock_agent
        mock_use_case._addapt_credentials.return_value = {}
        mock_use_case_cls.return_value = mock_use_case

        task_agent_webhook(
            integrated_agent_uuid=str(mock_agent.uuid),
            payload={"a": 1},
            params={},
        )

        mock_logger.log_webhook_received.assert_called_once()

    @patch("retail.vtex.tasks.AgentWebhookUseCase")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_explicit_uuid_string_is_parsed_into_uuid(
        self, mock_logger_factory, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_agent_webhook

        existing_uuid = uuid4()
        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        mock_use_case = MagicMock()
        mock_agent = MagicMock(uuid=uuid4(), ignore_templates=[])
        mock_use_case._get_integrated_agent.return_value = mock_agent
        mock_use_case._addapt_credentials.return_value = {}
        mock_use_case_cls.return_value = mock_use_case

        task_agent_webhook(
            integrated_agent_uuid=str(mock_agent.uuid),
            payload={"a": 1},
            params={},
            execution_uuid=str(existing_uuid),
        )

        ctx = get_current_execution_uuid()
        self.assertIsInstance(ctx, UUID)
        self.assertEqual(ctx, existing_uuid)


class TaskAgentWebhookEarlyReturnAndErrorTests(TestCase):
    """Defensive branches around `task_agent_webhook`.

    These pin behavior the dispatch view depends on:
      - When the integrated agent can't be resolved, the task must
        short-circuit BEFORE minting an execution and BEFORE running
        the use case (otherwise we'd leak orphan AgentExecution rows).
      - When the use case raises after the execution is minted,
        `log_execution_error` must be called with the exact UUID that
        was minted, so the row reaches a terminal ERROR state instead
        of staying STARTED forever.
    """

    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)

    @patch("retail.vtex.tasks.AgentWebhookUseCase")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_missing_integrated_agent_short_circuits(
        self, mock_logger_factory, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_agent_webhook

        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        mock_use_case = MagicMock()
        mock_use_case._get_integrated_agent.return_value = None
        mock_use_case_cls.return_value = mock_use_case

        task_agent_webhook(
            integrated_agent_uuid=str(uuid4()),
            payload={"a": 1},
            params={},
        )

        # No execution should be minted — there's nothing to attach it to.
        mock_logger.log_webhook_received.assert_not_called()
        # And the use case must NOT advance past the early return.
        mock_use_case._addapt_credentials.assert_not_called()
        mock_use_case.execute.assert_not_called()
        mock_logger.log_execution_error.assert_not_called()
        # Premise 4: standalone path must not open a row for a missing agent
        # and must not emit a skip against a non-existent execution.
        mock_logger.log_execution_skip.assert_not_called()

    @patch("retail.vtex.tasks.AgentWebhookUseCase")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_missing_integrated_agent_with_forwarded_uuid_logs_skip(
        self, mock_logger_factory, mock_use_case_cls
    ):
        """When an upstream task already opened an AgentExecution and
        forwards its UUID in, but the agent has been deleted/blocked
        between the two steps, the existing row must be closed with
        ``log_execution_skip`` instead of timing out."""
        from retail.vtex.tasks import task_agent_webhook

        forwarded_uuid = uuid4()
        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        mock_use_case = MagicMock()
        mock_use_case._get_integrated_agent.return_value = None
        mock_use_case_cls.return_value = mock_use_case

        agent_uuid = str(uuid4())
        task_agent_webhook(
            integrated_agent_uuid=agent_uuid,
            payload={"a": 1},
            params={},
            execution_uuid=str(forwarded_uuid),
        )

        # We must not open a NEW row
        mock_logger.log_webhook_received.assert_not_called()
        # The use case must NOT advance.
        mock_use_case._addapt_credentials.assert_not_called()
        mock_use_case.execute.assert_not_called()
        # And the forwarded row must be closed as skip.
        mock_logger.log_execution_skip.assert_called_once()
        kwargs = mock_logger.log_execution_skip.call_args.kwargs
        self.assertEqual(kwargs.get("execution_uuid"), forwarded_uuid)
        self.assertEqual(kwargs.get("reason"), "integrated_agent_missing_or_blocked")
        self.assertEqual(kwargs.get("skip_data"), {"integrated_agent_uuid": agent_uuid})

    @patch("retail.vtex.tasks.AgentWebhookUseCase")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_use_case_exception_is_logged_with_minted_uuid(
        self, mock_logger_factory, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_agent_webhook

        new_uuid = uuid4()
        mock_logger = MagicMock()
        mock_logger.log_webhook_received.return_value = new_uuid
        mock_logger_factory.return_value = mock_logger

        mock_use_case = MagicMock()
        mock_agent = MagicMock(uuid=uuid4(), ignore_templates=[])
        mock_use_case._get_integrated_agent.return_value = mock_agent
        mock_use_case._addapt_credentials.return_value = {}
        mock_use_case.execute.side_effect = RuntimeError("downstream boom")
        mock_use_case_cls.return_value = mock_use_case

        agent_uuid = str(mock_agent.uuid)
        # Must not raise — the task is fire-and-forget from the view.
        task_agent_webhook(
            integrated_agent_uuid=agent_uuid,
            payload={"a": 1},
            params={},
        )

        mock_logger.log_execution_error.assert_called_once()
        kwargs = mock_logger.log_execution_error.call_args.kwargs
        self.assertEqual(kwargs.get("execution_uuid"), new_uuid)
        self.assertEqual(kwargs.get("error_message"), "downstream boom")
        self.assertEqual(
            kwargs.get("error_data"), {"integrated_agent_uuid": agent_uuid}
        )

    @patch("retail.vtex.tasks.AgentWebhookUseCase")
    @patch("retail.vtex.tasks.ExecutionLoggerService")
    def test_use_case_exception_with_inherited_uuid_logs_against_it(
        self, mock_logger_factory, mock_use_case_cls
    ):
        """When the parent task already minted the UUID, errors must
        attach to it instead of being silently dropped."""
        from retail.vtex.tasks import task_agent_webhook

        existing_uuid = uuid4()
        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        mock_use_case = MagicMock()
        mock_agent = MagicMock(uuid=uuid4(), ignore_templates=[])
        mock_use_case._get_integrated_agent.return_value = mock_agent
        mock_use_case._addapt_credentials.return_value = {}
        mock_use_case.execute.side_effect = ValueError("inner boom")
        mock_use_case_cls.return_value = mock_use_case

        task_agent_webhook(
            integrated_agent_uuid=str(mock_agent.uuid),
            payload={"a": 1},
            params={},
            execution_uuid=str(existing_uuid),
        )

        mock_logger.log_webhook_received.assert_not_called()
        mock_logger.log_execution_error.assert_called_once()
        kwargs = mock_logger.log_execution_error.call_args.kwargs
        self.assertEqual(kwargs.get("execution_uuid"), existing_uuid)
        self.assertEqual(kwargs.get("error_message"), "inner boom")
