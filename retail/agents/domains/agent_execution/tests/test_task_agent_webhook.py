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
from uuid import uuid4

from django.test import TestCase

from retail.agents.domains.agent_execution.context import (
    clear_execution_context,
)


class TaskAgentWebhookDelegationTests(TestCase):
    """The task is glue: every argument is forwarded to
    ``AgentWebhookUseCase.execute_from_task`` which owns the orchestration.
    Tests for that orchestration live in ``test_agent_webhook.py``.
    """

    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)

    @patch("retail.vtex.tasks.AgentWebhookUseCase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_task_forwards_execution_uuid_to_use_case(
        self, mock_logger_factory, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_agent_webhook

        existing_uuid = uuid4()
        mock_use_case = MagicMock()
        mock_use_case_cls.return_value = mock_use_case

        agent_uuid = str(uuid4())
        task_agent_webhook(
            integrated_agent_uuid=agent_uuid,
            payload={"a": 1},
            params={"q": "v"},
            execution_uuid=str(existing_uuid),
        )

        mock_use_case.execute_from_task.assert_called_once_with(
            integrated_agent_uuid=agent_uuid,
            payload={"a": 1},
            params={"q": "v"},
            forwarded_execution_uuid=str(existing_uuid),
        )

    @patch("retail.vtex.tasks.AgentWebhookUseCase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_task_forwards_none_when_no_execution_uuid_supplied(
        self, mock_logger_factory, mock_use_case_cls
    ):
        from retail.vtex.tasks import task_agent_webhook

        mock_use_case = MagicMock()
        mock_use_case_cls.return_value = mock_use_case

        agent_uuid = str(uuid4())
        task_agent_webhook(
            integrated_agent_uuid=agent_uuid,
            payload={"a": 1},
            params={},
        )

        mock_use_case.execute_from_task.assert_called_once_with(
            integrated_agent_uuid=agent_uuid,
            payload={"a": 1},
            params={},
            forwarded_execution_uuid=None,
        )


class TaskAgentWebhookErrorScopeTests(TestCase):
    """The task wraps ``execute_from_task`` in ``execution_log_scope``.

    The scope is responsible for finalising an active execution row
    when the body raises, so this test just verifies the scope picks
    up an active contextvar and forwards the error to the logger.
    Orchestration tests for ``execute_from_task`` itself live in
    ``test_agent_webhook.py``.
    """

    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)

    @patch("retail.vtex.tasks.AgentWebhookUseCase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_use_case_exception_with_inherited_uuid_logs_against_it(
        self, mock_logger_factory, mock_use_case_cls
    ):
        """When the parent task already minted the UUID, errors must
        attach to it instead of being silently dropped."""
        from retail.agents.domains.agent_execution.context import (
            set_current_execution_uuid,
        )
        from retail.vtex.tasks import task_agent_webhook

        existing_uuid = uuid4()
        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        mock_use_case = MagicMock()

        # Simulate ``execute_from_task`` advancing the contextvar and
        # then raising — the scope should catch it and log the error.
        def _execute(*args, **kwargs):
            set_current_execution_uuid(existing_uuid)
            raise ValueError("inner boom")

        mock_use_case.execute_from_task.side_effect = _execute
        mock_use_case_cls.return_value = mock_use_case

        task_agent_webhook(
            integrated_agent_uuid=str(uuid4()),
            payload={"a": 1},
            params={},
            execution_uuid=str(existing_uuid),
        )

        mock_logger.log_execution_error.assert_called_once()
        kwargs = mock_logger.log_execution_error.call_args.kwargs
        self.assertEqual(kwargs.get("execution_uuid"), existing_uuid)
        self.assertEqual(kwargs.get("error_message"), "inner boom")
