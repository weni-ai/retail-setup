"""Retrieve-execution use case contract.

Single-execution lookup that returns ``None`` for missing rows and
never raises.
"""

from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.usecases.retrieve_execution import (
    RetrieveExecutionUseCase,
)


class RetrieveExecutionUseCaseTests(TestCase):
    def setUp(self):
        super().setUp()
        self.use_case = RetrieveExecutionUseCase()

    def test_returns_execution_when_present(self):
        execution = AgentExecution.objects.create(
            uuid=uuid4(),
            contact_urn="whatsapp:+5511999999999",
            status=AgentExecutionStatus.SUCCESS,
        )
        result = self.use_case.execute(execution.uuid)
        self.assertEqual(result, execution)

    def test_returns_none_when_missing(self):
        self.assertIsNone(self.use_case.execute(uuid4()))

    def test_accepts_uuid_string(self):
        execution = AgentExecution.objects.create(
            uuid=uuid4(),
            contact_urn="whatsapp:+5511999999999",
            status=AgentExecutionStatus.SUCCESS,
        )
        result = self.use_case.execute(str(execution.uuid))
        self.assertEqual(result, execution)

    def test_returns_none_for_invalid_uuid_string(self):
        """The URL dispatcher can forward any ``{uuid}`` path segment;
        feeding a malformed string to Django raises ``ValidationError``
        before the query even runs. The use case swallows that the
        same way it swallows ``DoesNotExist`` so views never 500 on a
        bad URL.
        """
        self.assertIsNone(self.use_case.execute("not-a-uuid"))

    def test_returns_none_when_get_raises_value_error(self):
        """``uuid.UUID`` raises ``ValueError`` on inputs the ORM never
        sees; the defensive catch keeps callers safe even when a
        collaborator hands us something pre-parsed and malformed.
        """
        with patch.object(
            AgentExecution.objects,
            "get",
            side_effect=ValueError("malformed UUID"),
        ):
            self.assertIsNone(self.use_case.execute("whatever"))
