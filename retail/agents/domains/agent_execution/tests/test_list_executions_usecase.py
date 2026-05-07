"""List-executions use case contract.

Filters mirror the ORM query patterns the documentation surfaces, but
they live behind a use case so future analytics views can call into
a single point and the model doesn't grow business logic.
"""

from datetime import timedelta
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.usecases.list_executions import (
    ListExecutionsFilter,
    ListExecutionsUseCase,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project


def _make_execution(
    *,
    contact_urn: str = "whatsapp:+5511999999999",
    status: str = AgentExecutionStatus.SUCCESS,
    days_old: int = 0,
    integrated_agent=None,
) -> AgentExecution:
    execution = AgentExecution.objects.create(
        uuid=uuid4(),
        contact_urn=contact_urn,
        status=status,
        integrated_agent=integrated_agent,
    )
    if days_old:
        AgentExecution.objects.filter(uuid=execution.uuid).update(
            created_on=timezone.now() - timedelta(days=days_old)
        )
        execution.refresh_from_db()
    return execution


class ListExecutionsUseCaseTests(TestCase):
    def setUp(self):
        super().setUp()
        self.use_case = ListExecutionsUseCase()

    def test_no_filter_returns_recent_executions(self):
        old = _make_execution(days_old=2)
        recent = _make_execution(days_old=0)

        result = self.use_case.execute(ListExecutionsFilter())

        uuids = [e.uuid for e in result]
        self.assertIn(old.uuid, uuids)
        self.assertIn(recent.uuid, uuids)
        # Default ordering: -created_on. Recent first.
        self.assertEqual(result[0].uuid, recent.uuid)

    def test_filter_by_contact_urn(self):
        match = _make_execution(contact_urn="whatsapp:+5511111111111")
        _make_execution(contact_urn="whatsapp:+5511222222222")

        result = self.use_case.execute(
            ListExecutionsFilter(contact_urn="whatsapp:+5511111111111")
        )

        self.assertEqual([e.uuid for e in result], [match.uuid])

    def test_filter_by_status(self):
        success = _make_execution(status=AgentExecutionStatus.SUCCESS)
        _make_execution(status=AgentExecutionStatus.ERROR)

        result = self.use_case.execute(
            ListExecutionsFilter(status=AgentExecutionStatus.SUCCESS)
        )
        self.assertEqual([e.uuid for e in result], [success.uuid])

    def test_filter_by_created_after_and_before(self):
        in_window = _make_execution(days_old=2)
        too_old = _make_execution(days_old=10)
        too_new = _make_execution(days_old=0)

        now = timezone.now()
        result = self.use_case.execute(
            ListExecutionsFilter(
                created_after=now - timedelta(days=5),
                created_before=now - timedelta(days=1),
            )
        )

        uuids = [e.uuid for e in result]
        self.assertIn(in_window.uuid, uuids)
        self.assertNotIn(too_old.uuid, uuids)
        self.assertNotIn(too_new.uuid, uuids)

    def test_pagination_via_limit_and_offset(self):
        for _ in range(5):
            _make_execution()

        page_one = self.use_case.execute(ListExecutionsFilter(limit=2, offset=0))
        page_two = self.use_case.execute(ListExecutionsFilter(limit=2, offset=2))

        self.assertEqual(len(page_one), 2)
        self.assertEqual(len(page_two), 2)
        self.assertNotEqual({e.uuid for e in page_one}, {e.uuid for e in page_two})

    def test_filter_by_integrated_agent_uuid(self):
        """``integrated_agent_uuid`` narrows the queryset to a single agent.

        Without it the query would leak rows from sibling integrations
        sharing the same project, which is exactly what tenant-scoped
        analytics views need to avoid.
        """
        project = Project.objects.create(name="Project A", uuid=uuid4())
        agent = Agent.objects.create(
            uuid=uuid4(),
            name="Agent A",
            slug="agent-a",
            description="",
            project=project,
        )
        integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(), agent=agent, project=project
        )
        other_integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(), agent=agent, project=project
        )
        mine = _make_execution(integrated_agent=integrated_agent)
        _make_execution(integrated_agent=other_integrated_agent)

        result = self.use_case.execute(
            ListExecutionsFilter(integrated_agent_uuid=integrated_agent.uuid)
        )

        self.assertEqual([e.uuid for e in result], [mine.uuid])

    def test_negative_offset_is_clamped_to_zero(self):
        """Negative offsets would slice from the end of a list in Python;
        the use case guards against that so a misconfigured caller gets
        the first page instead of a surprise tail slice.
        """
        for _ in range(3):
            _make_execution()

        result = self.use_case.execute(ListExecutionsFilter(offset=-10, limit=2))

        self.assertEqual(len(result), 2)

    def test_negative_limit_is_clamped_to_zero(self):
        """A negative limit collapses the slice to empty instead of
        falling back to the full queryset (which ``[0:-5]`` would do).
        """
        for _ in range(3):
            _make_execution()

        result = self.use_case.execute(ListExecutionsFilter(limit=-5, offset=0))

        self.assertEqual(result, [])
