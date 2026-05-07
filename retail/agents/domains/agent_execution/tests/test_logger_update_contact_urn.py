"""Logger encapsulation tests.

``ExecutionLoggerService.update_contact_urn`` used to reach into the
buffer's private cache attribute to overwrite the metadata blob. With
the metadata living in a Redis Hash, the proper API is the public
``buffer.update_metadata(uuid, **fields)`` method. These tests pin
that contract: the logger always goes through the public method, and
never touches the buffer's private state.
"""

from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.agents.domains.agent_execution.context import (
    clear_execution_context,
    set_current_execution_uuid,
)
from retail.agents.domains.agent_execution.services.buffer import (
    ExecutionBufferService,
)
from retail.agents.domains.agent_execution.services.logger import (
    ExecutionLoggerService,
)


class LoggerUpdateContactUrnTests(TestCase):
    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)

        self.buffer = MagicMock(spec=ExecutionBufferService)
        self.logger = ExecutionLoggerService(buffer_service=self.buffer)

    def test_update_contact_urn_calls_public_update_metadata(self):
        execution_uuid = uuid4()
        set_current_execution_uuid(execution_uuid)

        self.logger.update_contact_urn(contact_urn="whatsapp:+5511999999999")

        self.buffer.update_metadata.assert_called_once_with(
            execution_uuid=execution_uuid,
            contact_urn="whatsapp:+5511999999999",
        )

    def test_update_contact_urn_with_explicit_uuid_overrides_context(self):
        explicit_uuid = uuid4()

        self.logger.update_contact_urn(
            contact_urn="whatsapp:+5511777777777",
            execution_uuid=explicit_uuid,
        )

        self.buffer.update_metadata.assert_called_once_with(
            execution_uuid=explicit_uuid,
            contact_urn="whatsapp:+5511777777777",
        )

    def test_update_contact_urn_no_context_no_explicit_uuid_is_a_noop(self):
        self.logger.update_contact_urn(contact_urn="whatsapp:+5511999999999")
        self.buffer.update_metadata.assert_not_called()

    def test_logger_does_not_touch_private_buffer_state(self):
        execution_uuid = uuid4()
        set_current_execution_uuid(execution_uuid)

        forbidden_attrs = ("_cache", "_serialize_execution", "_get_execution_key")
        accesses = []

        class TrackingBuffer:
            def __init__(self, real):
                self._real = real

            def __getattr__(self, name):
                if name in forbidden_attrs:
                    accesses.append(name)
                return getattr(self._real, name)

            def update_metadata(self, **kwargs):
                return True

            def get_execution(self, *_args, **_kwargs):
                return None

        wrapped = TrackingBuffer(self.buffer)
        logger = ExecutionLoggerService(buffer_service=wrapped)

        logger.update_contact_urn(
            contact_urn="whatsapp:+5511999999999",
            execution_uuid=execution_uuid,
        )

        self.assertEqual(
            accesses,
            [],
            f"logger reached into forbidden buffer internals: {accesses}",
        )


class LoggerCallsBufferUpdateStatusOnSuccessTests(TestCase):
    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)

    def test_log_broadcast_sent_uses_public_buffer_methods(self):
        buffer = MagicMock(spec=ExecutionBufferService)
        logger = ExecutionLoggerService(buffer_service=buffer)
        execution_uuid = uuid4()
        template_uuid = uuid4()

        logger.log_broadcast_sent(
            broadcast_response={"id": 42},
            template_uuid=template_uuid,
            broadcast_id=42,
            execution_uuid=execution_uuid,
        )

        buffer.add_trace.assert_called_once()
        buffer.update_status.assert_called_once()
        ((), kwargs) = buffer.update_status.call_args
        self.assertEqual(kwargs["execution_uuid"], execution_uuid)
        self.assertEqual(kwargs["template_uuid"], template_uuid)
        self.assertEqual(kwargs["broadcast_id"], 42)
