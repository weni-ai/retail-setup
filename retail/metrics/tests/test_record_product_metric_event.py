from datetime import datetime, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from retail.metrics.exceptions import ProductMetricPublishError, ProjectNotFoundError
from retail.metrics.usecases.record_product_metric_event import (
    RecordProductMetricEventDTO,
    RecordProductMetricEventUseCase,
)
from retail.projects.models import Project
from weni_datalake_sdk.paths.events_path import EventPath


class RecordProductMetricEventUseCaseTests(TestCase):
    def setUp(self):
        self.send_event = MagicMock()
        self.tenant_locale_service = MagicMock()
        self.tenant_locale_service.resolve_geo_country.return_value = "BR"
        self.use_case = RecordProductMetricEventUseCase(
            send_event=self.send_event,
            tenant_locale_service=self.tenant_locale_service,
        )
        self.occurred_at = datetime(2026, 9, 23, 15, 0, tzinfo=dt_timezone.utc)

    def _dto(self, **overrides) -> RecordProductMetricEventDTO:
        defaults = dict(
            event_type="billing_subscribe",
            user_email="user@example.com",
            vtex_account="teststore",
            suggested_plan="20k",
            project_uuid="11111111-1111-1111-1111-111111111111",
        )
        defaults.update(overrides)
        return RecordProductMetricEventDTO(**defaults)

    def test_execute_maps_click_onto_events_payload(self):
        with self._frozen_now():
            self.use_case.execute(self._dto())

        self.send_event.assert_called_once_with(
            EventPath,
            {
                "event_name": "billing_subscribe",
                "key": "teststore",
                "date": "2026-09-23T15:00:00+00:00",
                "project": "11111111-1111-1111-1111-111111111111",
                "value_type": "string",
                "value": "20k",
                "contact_urn": "",
                "metadata": {
                    "user_email": "user@example.com",
                    "vtex_account": "teststore",
                    "country": "BR",
                    "suggested_plan": "20k",
                },
            },
        )
        self.tenant_locale_service.resolve_geo_country.assert_called_once_with(
            "teststore",
            fallback_language=None,
        )

    def test_execute_omits_country_and_plan_when_absent(self):
        self.tenant_locale_service.resolve_geo_country.return_value = None

        self.use_case.execute(self._dto(suggested_plan=None))

        payload = self.send_event.call_args[0][1]
        self.assertEqual(payload["value"], "")
        self.assertEqual(
            payload["metadata"],
            {
                "user_email": "user@example.com",
                "vtex_account": "teststore",
            },
        )

    def test_execute_resolves_active_project_when_token_has_no_project(self):
        project = Project.objects.create(
            uuid=uuid4(),
            name="Store",
            vtex_account="teststore",
            language="pt-br",
        )

        self.use_case.execute(self._dto(project_uuid=None))

        payload = self.send_event.call_args[0][1]
        self.assertEqual(payload["project"], str(project.uuid))
        self.tenant_locale_service.resolve_geo_country.assert_called_once_with(
            "teststore",
            fallback_language="pt-br",
        )

    def test_execute_raises_when_no_active_project_matches_account(self):
        Project.objects.create(
            uuid=uuid4(),
            name="Inactive",
            vtex_account="teststore",
            is_active=False,
        )

        with self.assertRaises(ProjectNotFoundError):
            self.use_case.execute(self._dto(project_uuid=None))

        self.send_event.assert_not_called()

    def test_execute_raises_when_account_has_multiple_active_projects(self):
        Project.objects.create(uuid=uuid4(), name="One", vtex_account="teststore")
        Project.objects.create(uuid=uuid4(), name="Two", vtex_account="teststore")

        with self.assertRaises(ProjectNotFoundError):
            self.use_case.execute(self._dto(project_uuid=None))

        self.send_event.assert_not_called()

    def test_execute_raises_publish_error_without_database_write(self):
        self.send_event.side_effect = RuntimeError("datalake down")

        with CaptureQueriesContext(connection) as captured:
            with self.assertRaises(ProductMetricPublishError):
                self.use_case.execute(self._dto())

        self.assertEqual(_write_queries(captured), [])

    def test_write_queries_collects_mutations(self):
        captured = SimpleNamespace(
            captured_queries=[
                {"sql": "SELECT 1"},
                {"sql": "INSERT INTO x VALUES (1)"},
                {"sql": "UPDATE x SET a = 1"},
                {"sql": "DELETE FROM x"},
            ]
        )
        self.assertEqual(
            _write_queries(captured),
            [
                "INSERT INTO x VALUES (1)",
                "UPDATE x SET a = 1",
                "DELETE FROM x",
            ],
        )

    def _frozen_now(self):
        return patch(
            "retail.metrics.usecases.record_product_metric_event.timezone.now",
            return_value=self.occurred_at,
        )


def _write_queries(captured: CaptureQueriesContext) -> list:
    writes = []
    for query in captured.captured_queries:
        statement = query["sql"].lstrip().split(None, 1)[0].upper()
        if statement in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(query["sql"])
    return writes
