"""End-to-end coverage of the high-level logger surface.

The logger is the public façade other apps call into. These tests
exercise every public method (lambda req/resp, broadcast, error,
skip), the contact-URN extraction heuristics on the webhook payload,
the explicit-vs-context UUID resolution, and the fallback to no-op
when neither is set.
"""

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.agents.domains.agent_execution.context import (
    clear_execution_context,
    get_current_execution_uuid,
    set_current_execution_uuid,
)
from retail.agents.domains.agent_execution.models import AgentExecutionStatus
from retail.agents.domains.agent_execution.services.buffer import (
    ExecutionBufferService,
)
from retail.agents.domains.agent_execution.services.logger import (
    ExecutionLoggerService,
)
from retail.agents.domains.agent_execution.types import ExecutionTraceType


class LoggerWebhookReceivedTests(TestCase):
    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)
        self.buffer = MagicMock(spec=ExecutionBufferService)
        self.new_uuid = uuid4()
        self.buffer.start_execution.return_value = self.new_uuid
        self.logger = ExecutionLoggerService(buffer_service=self.buffer)

    def test_log_webhook_received_starts_execution_and_sets_context(self):
        agent = MagicMock(uuid=uuid4())

        returned = self.logger.log_webhook_received(
            integrated_agent=agent,
            payload={"order_id": "abc"},
            contact_urn="whatsapp:+5511999999999",
            order_id="abc",
            amount=Decimal("10.00"),
            currency="BRL",
        )

        self.assertEqual(returned, self.new_uuid)
        self.assertEqual(get_current_execution_uuid(), self.new_uuid)
        self.buffer.start_execution.assert_called_once_with(
            integrated_agent_uuid=agent.uuid,
            contact_urn="whatsapp:+5511999999999",
            webhook_payload={"order_id": "abc"},
            order_id="abc",
            amount=Decimal("10.00"),
            currency="BRL",
        )

    def test_log_webhook_received_passes_none_currency_by_default(self):
        agent = MagicMock(uuid=uuid4())

        self.logger.log_webhook_received(
            integrated_agent=agent,
            payload={"order_id": "abc"},
            contact_urn="whatsapp:+5511999999999",
        )

        kwargs = self.buffer.start_execution.call_args.kwargs
        self.assertIsNone(kwargs["currency"])

    def test_update_order_info_sets_amount_and_currency(self):
        execution_uuid = uuid4()
        self.logger.update_order_info(
            amount=Decimal("199.90"),
            currency="USD",
            execution_uuid=execution_uuid,
        )

        self.buffer.update_metadata.assert_called_once_with(
            execution_uuid=execution_uuid,
            amount=Decimal("199.90"),
            currency="USD",
        )

    def test_update_order_info_no_op_without_uuid_or_context(self):
        self.logger.update_order_info(amount=Decimal("1.00"), currency="BRL")
        self.buffer.update_metadata.assert_not_called()

    def test_log_webhook_received_passes_unknown_contact_urn_when_unresolved(self):
        self.logger.log_webhook_received(
            integrated_agent=None,
            payload={},
        )
        kwargs = self.buffer.start_execution.call_args.kwargs
        self.assertEqual(kwargs["contact_urn"], "unknown")
        self.assertIsNone(kwargs["integrated_agent_uuid"])

    def test_log_webhook_received_extracts_contact_urn_when_present(self):
        self.logger.log_webhook_received(
            integrated_agent=None,
            payload={"contact_urn": "whatsapp:+5511777777777"},
        )
        kwargs = self.buffer.start_execution.call_args.kwargs
        self.assertEqual(kwargs["contact_urn"], "whatsapp:+5511777777777")

    def test_log_webhook_received_normalises_phone_to_whatsapp_urn(self):
        self.logger.log_webhook_received(
            integrated_agent=None,
            payload={"phone": "+5511666666666"},
        )
        kwargs = self.buffer.start_execution.call_args.kwargs
        self.assertEqual(kwargs["contact_urn"], "whatsapp:+5511666666666")

    def test_log_webhook_received_keeps_existing_whatsapp_prefix(self):
        self.logger.log_webhook_received(
            integrated_agent=None,
            payload={"phone": "whatsapp:+5511666666666"},
        )
        kwargs = self.buffer.start_execution.call_args.kwargs
        self.assertEqual(kwargs["contact_urn"], "whatsapp:+5511666666666")


class LoggerLambdaTraceTests(TestCase):
    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)
        self.buffer = MagicMock(spec=ExecutionBufferService)
        self.logger = ExecutionLoggerService(buffer_service=self.buffer)
        self.execution_uuid = uuid4()
        set_current_execution_uuid(self.execution_uuid)

    def test_log_lambda_request_uses_enum_trace_type(self):
        self.logger.log_lambda_request(request_data={"k": "v"})
        self.buffer.add_trace.assert_called_once_with(
            execution_uuid=self.execution_uuid,
            trace_type=ExecutionTraceType.LAMBDA_REQUEST.value,
            data={"k": "v"},
        )

    def test_log_lambda_response_uses_enum_trace_type(self):
        self.logger.log_lambda_response(response_data={"status": 0})
        self.buffer.add_trace.assert_called_once_with(
            execution_uuid=self.execution_uuid,
            trace_type=ExecutionTraceType.LAMBDA_RESPONSE.value,
            data={"status": 0},
        )

    def test_log_lambda_response_attaches_lambda_log_tail_when_provided(self):
        # The tail comes from AWS LogType="Tail" (last ~4 KB of stdout)
        # and is folded into the existing LAMBDA_RESPONSE trace so
        # readers find the Lambda's prints next to the parsed response.
        self.logger.log_lambda_response(
            response_data={"status": 0, "template": "t1"},
            log_tail="START RequestId\nhello\nEND RequestId\n",
        )
        self.buffer.add_trace.assert_called_once_with(
            execution_uuid=self.execution_uuid,
            trace_type=ExecutionTraceType.LAMBDA_RESPONSE.value,
            data={
                "status": 0,
                "template": "t1",
                "lambda_log_tail": "START RequestId\nhello\nEND RequestId\n",
            },
        )

    def test_log_lambda_response_omits_lambda_log_tail_when_none_or_empty(self):
        self.logger.log_lambda_response(
            response_data={"status": 0},
            log_tail=None,
        )
        self.logger.log_lambda_response(
            response_data={"status": 0},
            log_tail="",
        )
        for call in self.buffer.add_trace.call_args_list:
            self.assertNotIn("lambda_log_tail", call.kwargs["data"])

    def test_log_methods_noop_without_execution_uuid(self):
        clear_execution_context()
        self.logger.log_lambda_request(request_data={"k": "v"})
        self.logger.log_lambda_response(response_data={"k": "v"})
        self.buffer.add_trace.assert_not_called()


class LoggerBroadcastTests(TestCase):
    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)
        self.buffer = MagicMock(spec=ExecutionBufferService)
        self.logger = ExecutionLoggerService(buffer_service=self.buffer)

    def test_log_broadcast_sent_writes_trace_then_marks_success(self):
        execution_uuid = uuid4()
        template_uuid = uuid4()
        broadcast_message_uuid = uuid4()

        self.logger.log_broadcast_sent(
            broadcast_response={"id": 99},
            template_uuid=template_uuid,
            broadcast_id=99,
            broadcast_message_uuid=broadcast_message_uuid,
            execution_uuid=execution_uuid,
        )

        self.buffer.add_trace.assert_called_once_with(
            execution_uuid=execution_uuid,
            trace_type=ExecutionTraceType.BROADCAST_RESPONSE.value,
            data={"id": 99},
        )
        self.buffer.update_metadata.assert_called_once_with(
            execution_uuid=execution_uuid,
            status=AgentExecutionStatus.SUCCESS,
            template_uuid=template_uuid,
            broadcast_id=99,
            broadcast_message_uuid=broadcast_message_uuid,
        )

    def test_log_broadcast_sent_threads_none_broadcast_message_uuid_by_default(self):
        # The dispatcher may fail to persist BroadcastMessage defensively;
        # in that case we still log the success but the FK stays NULL.
        execution_uuid = uuid4()

        self.logger.log_broadcast_sent(
            broadcast_response={"id": 1},
            template_uuid=None,
            broadcast_id=1,
            execution_uuid=execution_uuid,
        )

        kwargs = self.buffer.update_metadata.call_args.kwargs
        self.assertIsNone(kwargs["broadcast_message_uuid"])

    def test_log_broadcast_sent_uses_context_when_uuid_not_passed(self):
        execution_uuid = uuid4()
        set_current_execution_uuid(execution_uuid)

        self.logger.log_broadcast_sent(
            broadcast_response={},
            template_uuid=None,
            broadcast_id=None,
        )

        self.buffer.add_trace.assert_called_once()
        self.assertEqual(
            self.buffer.add_trace.call_args.kwargs["execution_uuid"], execution_uuid
        )

    def test_log_broadcast_sent_noop_without_context(self):
        self.logger.log_broadcast_sent(
            broadcast_response={},
            template_uuid=None,
            broadcast_id=None,
        )
        self.buffer.add_trace.assert_not_called()
        self.buffer.update_metadata.assert_not_called()


class LoggerErrorAndSkipTests(TestCase):
    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)
        self.buffer = MagicMock(spec=ExecutionBufferService)
        self.logger = ExecutionLoggerService(buffer_service=self.buffer)

    def test_log_execution_error_emits_error_trace_and_marks_status(self):
        execution_uuid = uuid4()

        self.logger.log_execution_error(
            error_message="boom",
            error_data={"trace_id": "x"},
            execution_uuid=execution_uuid,
        )

        self.buffer.add_trace.assert_called_once_with(
            execution_uuid=execution_uuid,
            trace_type=ExecutionTraceType.ERROR.value,
            data={"error_message": "boom", "details": {"trace_id": "x"}},
        )
        self.buffer.update_metadata.assert_called_once_with(
            execution_uuid=execution_uuid,
            status=AgentExecutionStatus.ERROR,
            error_message="boom",
        )

    def test_log_execution_error_omits_details_when_no_data(self):
        execution_uuid = uuid4()

        self.logger.log_execution_error(
            error_message="boom",
            execution_uuid=execution_uuid,
        )

        self.buffer.add_trace.assert_called_once_with(
            execution_uuid=execution_uuid,
            trace_type=ExecutionTraceType.ERROR.value,
            data={"error_message": "boom"},
        )

    def test_log_execution_skip_emits_skip_trace_and_marks_status(self):
        execution_uuid = uuid4()

        self.logger.log_execution_skip(
            reason="not allowed",
            skip_data={"why": "policy"},
            execution_uuid=execution_uuid,
        )

        self.buffer.add_trace.assert_called_once_with(
            execution_uuid=execution_uuid,
            trace_type=ExecutionTraceType.SKIP.value,
            data={"reason": "not allowed", "details": {"why": "policy"}},
        )
        self.buffer.update_metadata.assert_called_once_with(
            execution_uuid=execution_uuid,
            status=AgentExecutionStatus.SKIP,
        )

    def test_skip_and_error_noop_without_uuid(self):
        self.logger.log_execution_error(error_message="boom")
        self.logger.log_execution_skip(reason="nope")
        self.buffer.add_trace.assert_not_called()
        self.buffer.update_metadata.assert_not_called()
