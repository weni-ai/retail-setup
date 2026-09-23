from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from retail.internal.test_mixins import patch_retail_auth
from retail.projects.models import Project

SEND_EVENT_PATH = "retail.metrics.usecases.record_product_metric_event.send_event_data"
LOCALE_SERVICE_PATH = (
    "retail.metrics.usecases.record_product_metric_event.VtexTenantLocaleService"
)


class RecordProductMetricEventViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v3/metrics/events/"
        self.project_uuid = "11111111-1111-1111-1111-111111111111"

    def _auth(self, **overrides):
        defaults = dict(
            vtex_account="teststore",
            user_email="user@example.com",
            project_uuid=self.project_uuid,
        )
        defaults.update(overrides)
        return patch_retail_auth(**defaults)

    def test_returns_204_using_auth_identity_not_the_body(self):
        with self._auth(), self._publish(country="BR") as send_event:
            response = self.client.post(
                self.url,
                {
                    "event_type": "billing_subscribe",
                    "suggested_plan": "20k",
                    "user_email": "other@example.com",
                    "vtex_account": "other-store",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        payload = send_event.call_args[0][1]
        self.assertEqual(payload["event_name"], "billing_subscribe")
        self.assertEqual(payload["key"], "teststore")
        self.assertEqual(payload["project"], self.project_uuid)
        self.assertEqual(payload["value"], "20k")
        self.assertEqual(payload["metadata"]["user_email"], "user@example.com")
        self.assertEqual(payload["metadata"]["vtex_account"], "teststore")
        self.assertEqual(payload["metadata"]["country"], "BR")
        self.assertEqual(payload["metadata"]["suggested_plan"], "20k")

    def test_omits_country_when_locale_lookup_returns_nothing(self):
        with self._auth(), self._publish(country=None) as send_event:
            response = self.client.post(
                self.url,
                {"event_type": "help_whatsapp"},
                format="json",
            )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        metadata = send_event.call_args[0][1]["metadata"]
        self.assertNotIn("country", metadata)
        self.assertNotIn("suggested_plan", metadata)
        self.assertEqual(send_event.call_args[0][1]["value"], "")

    def test_resolves_project_from_vtex_account_when_token_has_none(self):
        project = Project.objects.create(
            uuid=uuid4(),
            name="Store",
            vtex_account="teststore",
        )

        with self._auth(project_uuid=None), self._publish(country="US") as send_event:
            response = self.client.post(
                self.url,
                {"event_type": "settings_view_plans"},
                format="json",
            )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertEqual(send_event.call_args[0][1]["project"], str(project.uuid))

    def test_returns_400_for_unknown_event_type(self):
        with self._auth(), self._publish() as send_event:
            response = self.client.post(
                self.url,
                {"event_type": "not_a_metric"},
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("event_type", response.data)
        send_event.assert_not_called()

    def test_returns_400_for_unknown_suggested_plan(self):
        with self._auth(), self._publish() as send_event:
            response = self.client.post(
                self.url,
                {"event_type": "billing_subscribe", "suggested_plan": "enterprise"},
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("suggested_plan", response.data)
        send_event.assert_not_called()

    def test_returns_403_when_auth_email_is_missing(self):
        with self._auth(user_email=None), self._publish() as send_event:
            response = self.client.post(
                self.url,
                {"event_type": "help_schedule_time"},
                format="json",
            )

        self.assertEqual(response.status_code, 403)
        send_event.assert_not_called()

    def test_returns_403_when_vtex_account_is_missing(self):
        with self._auth(vtex_account=None), self._publish() as send_event:
            response = self.client.post(
                self.url,
                {"event_type": "usage_banner_view_plans"},
                format="json",
            )

        self.assertEqual(response.status_code, 403)
        send_event.assert_not_called()

    def test_returns_404_when_account_has_no_active_project(self):
        with self._auth(project_uuid=None), self._publish() as send_event:
            response = self.client.post(
                self.url,
                {"event_type": "billing_talk_to_specialist"},
                format="json",
            )

        self.assertEqual(response.status_code, 404)
        send_event.assert_not_called()

    def test_returns_502_and_writes_nothing_when_datalake_fails(self):
        with self._auth(), self._publish(side_effect=RuntimeError("datalake down")):
            with CaptureQueriesContext(connection) as captured:
                response = self.client.post(
                    self.url,
                    {"event_type": "billing_subscribe", "suggested_plan": "5k"},
                    format="json",
                )

        self.assertEqual(response.status_code, 502)
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

    def _publish(self, country="BR", side_effect=None):
        return _PublishContext(country=country, side_effect=side_effect)


class _PublishContext:
    def __init__(self, country, side_effect):
        self.country = country
        self.side_effect = side_effect
        self.send_event = None

    def __enter__(self):
        self.locale_patch = patch(LOCALE_SERVICE_PATH)
        self.send_patch = patch(SEND_EVENT_PATH)
        locale_cls = self.locale_patch.start()
        self.send_event = self.send_patch.start()
        locale_cls.return_value.resolve_geo_country.return_value = self.country
        if self.side_effect is not None:
            self.send_event.side_effect = self.side_effect
        return self.send_event

    def __exit__(self, exc_type, exc, tb):
        self.send_patch.stop()
        self.locale_patch.stop()
        return False


def _write_queries(captured: CaptureQueriesContext) -> list:
    writes = []
    for query in captured.captured_queries:
        statement = query["sql"].lstrip().split(None, 1)[0].upper()
        if statement in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(query["sql"])
    return writes
