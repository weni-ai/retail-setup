"""Tests for ``ListAgentLogsUseCase``.

Pins the API-shaped filter semantics:
- search ILIKE across contact_urn AND order_id
- single calendar-day filter, treated as UTC
- multi-template / multi-status OR
- page/page_size with total
- stable ordering with uuid tiebreaker
- project-scoping prevents cross-tenant leakage
"""

from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.usecases.list_agent_logs import (
    ListAgentLogsFilter,
    ListAgentLogsUseCase,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.broadcasts.models import BroadcastMessage, BroadcastStatus
from retail.projects.models import Project
from retail.templates.models import Template


def _make_execution(
    integrated_agent: IntegratedAgent,
    *,
    contact_urn: str = "whatsapp:+5511999999999",
    status: str = AgentExecutionStatus.SUCCESS,
    order_id: str = None,
    template: Template = None,
    days_old: int = 0,
    seconds_old: int = 0,
    broadcast_message: BroadcastMessage = None,
) -> AgentExecution:
    execution = AgentExecution.objects.create(
        uuid=uuid4(),
        contact_urn=contact_urn,
        status=status,
        integrated_agent=integrated_agent,
        order_id=order_id,
        template=template,
        broadcast_message=broadcast_message,
    )
    if days_old or seconds_old:
        AgentExecution.objects.filter(uuid=execution.uuid).update(
            created_on=timezone.now() - timedelta(days=days_old, seconds=seconds_old)
        )
        execution.refresh_from_db()
    return execution


def _make_broadcast_message(
    integrated_agent: IntegratedAgent,
    *,
    status: str = BroadcastStatus.SENT,
) -> BroadcastMessage:
    return BroadcastMessage.objects.create(
        project=integrated_agent.project,
        integrated_agent=integrated_agent,
        status=status,
    )


class ListAgentLogsUseCaseTests(TestCase):
    def setUp(self):
        super().setUp()
        self.use_case = ListAgentLogsUseCase()

        self.project = Project.objects.create(name="Project A", uuid=uuid4())
        self.other_project = Project.objects.create(name="Other Project", uuid=uuid4())
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Agent A",
            slug="agent-a",
            description="",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(), agent=self.agent, project=self.project
        )
        self.other_integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(), agent=self.agent, project=self.other_project
        )

    def _filter(self, **overrides) -> ListAgentLogsFilter:
        defaults = dict(
            agent_uuid=self.integrated_agent.uuid,
            project_uuid=self.project.uuid,
        )
        defaults.update(overrides)
        return ListAgentLogsFilter(**defaults)

    def test_scopes_to_agent_and_project(self):
        mine = _make_execution(self.integrated_agent)
        _make_execution(self.other_integrated_agent)

        rows, total = self.use_case.execute(self._filter())

        self.assertEqual([r.uuid for r in rows], [mine.uuid])
        self.assertEqual(total, 1)

    def test_search_matches_contact_substring(self):
        match = _make_execution(
            self.integrated_agent, contact_urn="whatsapp:+5511777777777"
        )
        _make_execution(self.integrated_agent, contact_urn="whatsapp:+5511222222222")

        rows, total = self.use_case.execute(self._filter(search="777777"))

        self.assertEqual([r.uuid for r in rows], [match.uuid])
        self.assertEqual(total, 1)

    def test_search_matches_order_id_substring(self):
        match = _make_execution(
            self.integrated_agent,
            contact_urn="whatsapp:+5511000000000",
            order_id="ORD-98765",
        )
        _make_execution(
            self.integrated_agent,
            contact_urn="whatsapp:+5511111111111",
            order_id="ORD-11111",
        )

        rows, total = self.use_case.execute(self._filter(search="98765"))

        self.assertEqual([r.uuid for r in rows], [match.uuid])
        self.assertEqual(total, 1)

    def test_search_is_case_insensitive(self):
        match = _make_execution(self.integrated_agent, contact_urn="whatsapp:+ABC9999")

        rows, total = self.use_case.execute(self._filter(search="abc"))

        self.assertEqual([r.uuid for r in rows], [match.uuid])
        self.assertEqual(total, 1)

    def test_empty_search_string_does_not_constrain(self):
        kept = _make_execution(self.integrated_agent)

        rows, total = self.use_case.execute(self._filter(search="   "))

        self.assertEqual([r.uuid for r in rows], [kept.uuid])
        self.assertEqual(total, 1)

    def test_date_filter_treats_day_as_utc(self):
        target_day = date(2026, 5, 1)

        in_window = _make_execution(self.integrated_agent)
        AgentExecution.objects.filter(uuid=in_window.uuid).update(
            created_on=datetime(2026, 5, 1, 12, 0, tzinfo=dt_timezone.utc)
        )

        before = _make_execution(self.integrated_agent)
        AgentExecution.objects.filter(uuid=before.uuid).update(
            created_on=datetime(2026, 4, 30, 23, 59, 59, tzinfo=dt_timezone.utc)
        )

        after = _make_execution(self.integrated_agent)
        AgentExecution.objects.filter(uuid=after.uuid).update(
            created_on=datetime(2026, 5, 2, 0, 0, 1, tzinfo=dt_timezone.utc)
        )

        rows, total = self.use_case.execute(self._filter(date=target_day))

        self.assertEqual([r.uuid for r in rows], [in_window.uuid])
        self.assertEqual(total, 1)

    def test_date_filter_includes_utc_day_edges(self):
        target_day = date(2026, 5, 1)

        edge_start = _make_execution(self.integrated_agent)
        AgentExecution.objects.filter(uuid=edge_start.uuid).update(
            created_on=datetime.combine(
                target_day, time(0, 0, 0), tzinfo=dt_timezone.utc
            )
        )
        edge_end = _make_execution(self.integrated_agent)
        AgentExecution.objects.filter(uuid=edge_end.uuid).update(
            created_on=datetime.combine(
                target_day, time(23, 59, 59, 999999), tzinfo=dt_timezone.utc
            )
        )

        rows, total = self.use_case.execute(self._filter(date=target_day))

        self.assertEqual({r.uuid for r in rows}, {edge_start.uuid, edge_end.uuid})
        self.assertEqual(total, 2)

    def test_template_uuids_filter_combines_with_or(self):
        Agent.objects.create(
            uuid=uuid4(), name="x", slug="x", description="", project=self.project
        )
        template_a = Template.objects.create(
            uuid=uuid4(),
            name="a",
            integrated_agent=self.integrated_agent,
        )
        template_b = Template.objects.create(
            uuid=uuid4(),
            name="b",
            integrated_agent=self.integrated_agent,
        )
        template_c = Template.objects.create(
            uuid=uuid4(),
            name="c",
            integrated_agent=self.integrated_agent,
        )
        match_a = _make_execution(self.integrated_agent, template=template_a)
        match_b = _make_execution(self.integrated_agent, template=template_b)
        _make_execution(self.integrated_agent, template=template_c)

        rows, total = self.use_case.execute(
            self._filter(template_uuids=(template_a.uuid, template_b.uuid))
        )

        self.assertEqual({r.uuid for r in rows}, {match_a.uuid, match_b.uuid})
        self.assertEqual(total, 2)

    def test_statuses_filter_translates_log_status_to_internal(self):
        sent = _make_execution(
            self.integrated_agent, status=AgentExecutionStatus.SUCCESS
        )
        skipped = _make_execution(
            self.integrated_agent, status=AgentExecutionStatus.SKIP
        )
        _make_execution(self.integrated_agent, status=AgentExecutionStatus.PROCESSING)

        rows, total = self.use_case.execute(self._filter(statuses=("sent", "skipped")))

        self.assertEqual({r.uuid for r in rows}, {sent.uuid, skipped.uuid})
        self.assertEqual(total, 2)

    def test_statuses_filter_drops_unknown_values(self):
        _make_execution(self.integrated_agent, status=AgentExecutionStatus.SUCCESS)

        rows, total = self.use_case.execute(self._filter(statuses=("totally-bogus",)))

        self.assertEqual(rows, [])
        self.assertEqual(total, 0)


class ListAgentLogsBroadcastFilterTests(TestCase):
    """Filter semantics that traverse the ``broadcast_message`` FK.

    These pin the cross-feature wiring: when a row has a linked
    ``BroadcastMessage`` the surfaced log status reflects the courier
    lifecycle, and the same predicate flows through into the list
    filter so the user can drill down by ``delivered`` / ``read`` /
    courier-derived ``error`` and the ``sent`` bucket excludes the
    rows that have already advanced past it.
    """

    def setUp(self):
        super().setUp()
        self.use_case = ListAgentLogsUseCase()

        self.project = Project.objects.create(name="Project A", uuid=uuid4())
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Agent A",
            slug="agent-a",
            description="",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(), agent=self.agent, project=self.project
        )

    def _filter(self, **overrides) -> ListAgentLogsFilter:
        defaults = dict(
            agent_uuid=self.integrated_agent.uuid,
            project_uuid=self.project.uuid,
        )
        defaults.update(overrides)
        return ListAgentLogsFilter(**defaults)

    def _success_with_broadcast(self, broadcast_status: str) -> AgentExecution:
        broadcast_message = _make_broadcast_message(
            self.integrated_agent, status=broadcast_status
        )
        return _make_execution(
            self.integrated_agent,
            status=AgentExecutionStatus.SUCCESS,
            broadcast_message=broadcast_message,
        )

    def test_delivered_filter_returns_only_delivered_rows(self):
        delivered = self._success_with_broadcast(BroadcastStatus.DELIVERED)
        self._success_with_broadcast(BroadcastStatus.READ)
        self._success_with_broadcast(BroadcastStatus.SENT)

        rows, total = self.use_case.execute(self._filter(statuses=("delivered",)))

        self.assertEqual([r.uuid for r in rows], [delivered.uuid])
        self.assertEqual(total, 1)

    def test_read_filter_returns_only_read_rows(self):
        self._success_with_broadcast(BroadcastStatus.DELIVERED)
        read_row = self._success_with_broadcast(BroadcastStatus.READ)

        rows, total = self.use_case.execute(self._filter(statuses=("read",)))

        self.assertEqual([r.uuid for r in rows], [read_row.uuid])
        self.assertEqual(total, 1)

    def test_error_filter_combines_internal_error_and_courier_failed(self):
        internal_error = _make_execution(
            self.integrated_agent, status=AgentExecutionStatus.ERROR
        )
        courier_failed = self._success_with_broadcast(BroadcastStatus.FAILED)
        # ERRORED is transient — shouldn't be in the error bucket.
        self._success_with_broadcast(BroadcastStatus.ERRORED)
        self._success_with_broadcast(BroadcastStatus.SENT)

        rows, total = self.use_case.execute(self._filter(statuses=("error",)))

        self.assertEqual(
            {r.uuid for r in rows}, {internal_error.uuid, courier_failed.uuid}
        )
        self.assertEqual(total, 2)

    def test_sent_filter_excludes_delivered_read_and_failed(self):
        # ``sent`` covers success rows that are still in flight or
        # have transient courier states. DELIVERED / READ / FAILED
        # have moved past ``sent`` and must not appear here.
        sent_no_link = _make_execution(
            self.integrated_agent, status=AgentExecutionStatus.SUCCESS
        )
        still_in_flight = self._success_with_broadcast(BroadcastStatus.SENT)
        transient_error = self._success_with_broadcast(BroadcastStatus.ERRORED)
        self._success_with_broadcast(BroadcastStatus.DELIVERED)
        self._success_with_broadcast(BroadcastStatus.READ)
        self._success_with_broadcast(BroadcastStatus.FAILED)

        rows, total = self.use_case.execute(self._filter(statuses=("sent",)))

        self.assertEqual(
            {r.uuid for r in rows},
            {sent_no_link.uuid, still_in_flight.uuid, transient_error.uuid},
        )
        self.assertEqual(total, 3)

    def test_combined_delivered_and_read_filter_combines_with_or(self):
        delivered = self._success_with_broadcast(BroadcastStatus.DELIVERED)
        read_row = self._success_with_broadcast(BroadcastStatus.READ)
        self._success_with_broadcast(BroadcastStatus.SENT)

        rows, total = self.use_case.execute(
            self._filter(statuses=("delivered", "read"))
        )

        self.assertEqual({r.uuid for r in rows}, {delivered.uuid, read_row.uuid})
        self.assertEqual(total, 2)

    def test_join_does_not_duplicate_rows(self):
        # ``broadcast_message`` is a singular FK so the JOIN must not
        # multiply rows, even when the filter touches the joined table.
        delivered = self._success_with_broadcast(BroadcastStatus.DELIVERED)

        rows, total = self.use_case.execute(self._filter(statuses=("delivered",)))

        self.assertEqual([r.uuid for r in rows], [delivered.uuid])
        self.assertEqual(total, 1)

    def test_pagination_returns_total_irrespective_of_page_size(self):
        for index in range(7):
            _make_execution(self.integrated_agent, seconds_old=index)

        rows, total = self.use_case.execute(self._filter(page=1, page_size=3))
        self.assertEqual(len(rows), 3)
        self.assertEqual(total, 7)

        rows_page_two, total_page_two = self.use_case.execute(
            self._filter(page=2, page_size=3)
        )
        self.assertEqual(len(rows_page_two), 3)
        self.assertEqual(total_page_two, 7)

        first_page_uuids = {r.uuid for r in rows}
        second_page_uuids = {r.uuid for r in rows_page_two}
        self.assertEqual(first_page_uuids & second_page_uuids, set())

    def test_orders_by_created_on_desc_with_uuid_tiebreaker(self):
        common_time = timezone.now()
        a = _make_execution(self.integrated_agent)
        b = _make_execution(self.integrated_agent)
        AgentExecution.objects.filter(uuid__in=[a.uuid, b.uuid]).update(
            created_on=common_time
        )

        rows, _ = self.use_case.execute(self._filter())

        sorted_pair = sorted([a.uuid, b.uuid])
        self.assertEqual([r.uuid for r in rows], sorted_pair)

    def test_amount_and_currency_round_trip_through_db(self):
        execution = AgentExecution.objects.create(
            uuid=uuid4(),
            contact_urn="whatsapp:+5511000000000",
            status=AgentExecutionStatus.SUCCESS,
            integrated_agent=self.integrated_agent,
            order_id="ORD-1",
            amount=Decimal("199.90"),
            currency="USD",
        )

        rows, _ = self.use_case.execute(self._filter())

        self.assertEqual(rows[0].uuid, execution.uuid)
        self.assertEqual(rows[0].amount, Decimal("199.90"))
        self.assertEqual(rows[0].currency, "USD")
