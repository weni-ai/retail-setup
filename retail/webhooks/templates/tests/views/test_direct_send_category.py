import re

from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_webhook.services.broadcast import Broadcast
from retail.internal.test_mixins import BaseTestMixin, with_test_settings
from retail.projects.models import Project
from retail.templates.models import Template, Version
from retail.webhooks.templates.usecases.direct_send_category import (
    DirectSendCategoryWebhookUseCase,
)


_EVENT_NAME_REGEX = re.compile(r"\[DirectSendCategoryWebhook\] (?P<event>\w+):")


def _emitted_events(log_ctx):
    events = []
    for record in log_ctx.records:
        match = _EVENT_NAME_REGEX.match(record.getMessage())
        if match is not None:
            events.append(match.group("event"))
    return events


def _seed_project_with_flaggable_template(*, app_uuid, template_name):
    project = Project.objects.create(name="Acme", uuid=uuid4())
    agent = Agent.objects.create(
        project=project, name="OrderStatus", slug="order-status", description="desc"
    )
    integrated_agent = IntegratedAgent.objects.create(
        agent=agent, project=project, uuid=uuid4()
    )
    template = Template.objects.create(
        name=template_name, integrated_agent=integrated_agent, uuid=uuid4()
    )
    version = Version.objects.create(
        template=template,
        template_name=template_name,
        integrations_app_uuid=app_uuid,
        project=project,
        status="APPROVED",
    )
    template.current_version = version
    template.save(update_fields=["current_version"])
    return project, integrated_agent, template, version


@with_test_settings
class DirectSendCategoryWebhookViewTest(BaseTestMixin, APITestCase):
    URL_NAME = "direct-send-category-webhook"
    TEMPLATE_NAME = "weni_order_invoiced"

    def setUp(self):
        super().setUp()
        self.url = reverse(self.URL_NAME)
        self.app_uuid = uuid4()
        self.project, self.integrated_agent, self.template, self.version = (
            _seed_project_with_flaggable_template(
                app_uuid=self.app_uuid, template_name=self.TEMPLATE_NAME
            )
        )
        self.user = User.objects.create_user(
            username="internal", password="pwd", email="internal@example.com"
        )
        self.client = APIClient()

    def _valid_payload(self, **overrides):
        payload = {
            "project_uuid": str(self.project.uuid),
            "app_uuid": str(self.app_uuid),
            "template_name": self.TEMPLATE_NAME,
            "template_category": "MARKETING",
            "template_correct_category": "MARKETING",
        }
        payload.update(overrides)
        return payload

    def _authenticate_internal_user(self):
        self.setup_internal_user_permissions(self.user)
        self.client.force_authenticate(user=self.user)

    def test_happy_path_returns_200_and_flags_version(self):
        self._authenticate_internal_user()

        response = self.client.post(self.url, self._valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "detail": "Templates flagged.",
                "templates_updated": 1,
                "integrated_agents_inspected": 1,
            },
        )

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "FLAGGED")

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.post(self.url, self._valid_payload(), format="json")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_authenticated_user_without_internal_permission_is_forbidden(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.url, self._valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_required_field_returns_400(self):
        self._authenticate_internal_user()

        payload = self._valid_payload()
        payload.pop("template_correct_category")

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("template_correct_category", response.json())

    def test_malformed_uuid_returns_400(self):
        self._authenticate_internal_user()

        payload = self._valid_payload(project_uuid="not-a-uuid")

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project_uuid", response.json())

    def test_blank_template_name_returns_400(self):
        self._authenticate_internal_user()

        payload = self._valid_payload(template_name="")

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("template_name", response.json())

    def test_unexpected_exception_returns_500_and_emits_audit_lines(self):
        self._authenticate_internal_user()

        with patch.object(
            DirectSendCategoryWebhookUseCase,
            "_lookup_integrated_agents",
            side_effect=Exception("db lost"),
        ):
            with self.assertLogs(
                "retail.webhooks.templates.usecases.direct_send_category",
                level="INFO",
            ) as log_ctx:
                response = self.client.post(
                    self.url, self._valid_payload(), format="json"
                )

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.json(), {"detail": "Internal server error"})

        events = _emitted_events(log_ctx)
        self.assertIn("received", events)
        self.assertIn("unexpected_error", events)
        self.assertNotIn("completed", events)

        unexpected_records = [
            record
            for record in log_ctx.records
            if "unexpected_error" in record.getMessage()
        ]
        self.assertTrue(
            any(record.exc_info for record in unexpected_records),
            "unexpected_error log line must carry exc_info=True",
        )


@with_test_settings
class DirectSendCategoryWebhookReplayTest(BaseTestMixin, APITestCase):
    """Pins the bidirectional FR-008 idempotency contract via the HTTP
    boundary: (a) firing the same flagging payload twice converges on
    ``FLAGGED`` with exactly one underlying write and an
    ``"Already flagged."`` response on the replay (SC-004);
    (b) firing a corrected-category payload against an already
    ``FLAGGED`` Version auto-demotes to ``APPROVED`` per FR-006c /
    FR-007d."""

    URL_NAME = "direct-send-category-webhook"
    TEMPLATE_NAME = "weni_order_invoiced"

    def setUp(self):
        super().setUp()
        self.url = reverse(self.URL_NAME)
        self.app_uuid = uuid4()
        self.project, self.integrated_agent, self.template, self.version = (
            _seed_project_with_flaggable_template(
                app_uuid=self.app_uuid, template_name=self.TEMPLATE_NAME
            )
        )
        self.user = User.objects.create_user(
            username="internal-replay", password="pwd", email="replay@example.com"
        )
        self.setup_internal_user_permissions(self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _payload(self, **overrides):
        payload = {
            "project_uuid": str(self.project.uuid),
            "app_uuid": str(self.app_uuid),
            "template_name": self.TEMPLATE_NAME,
            "template_category": "MARKETING",
            "template_correct_category": "MARKETING",
        }
        payload.update(overrides)
        return payload

    def test_flag_replay_with_same_payload_is_noop(self):
        with patch.object(
            Version, "save", autospec=True, side_effect=Version.save
        ) as save_mock:
            first_response = self.client.post(self.url, self._payload(), format="json")
            second_response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            first_response.json(),
            {
                "detail": "Templates flagged.",
                "templates_updated": 1,
                "integrated_agents_inspected": 1,
            },
        )

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            second_response.json(),
            {
                "detail": "Already flagged.",
                "templates_updated": 0,
                "integrated_agents_inspected": 1,
            },
        )

        status_saves = [
            call
            for call in save_mock.call_args_list
            if call.kwargs.get("update_fields") == ["status"]
        ]
        self.assertEqual(len(status_saves), 1)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "FLAGGED")

    def test_corrected_category_replay_auto_demotes_to_approved(self):
        Version.objects.filter(pk=self.version.pk).update(status="FLAGGED")

        response = self.client.post(
            self.url,
            self._payload(
                template_category="UTILITY",
                template_correct_category="UTILITY",
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "detail": "Auto-demoted.",
                "templates_updated": 1,
                "integrated_agents_inspected": 1,
            },
        )

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "APPROVED")


@with_test_settings
class DirectSendCategoryWebhookDispatchIntegrationTest(BaseTestMixin, TestCase):
    URL_NAME = "direct-send-category-webhook"
    TEMPLATE_NAME = "weni_order_invoiced"

    def setUp(self):
        super().setUp()
        self.url = reverse(self.URL_NAME)
        self.app_uuid = uuid4()
        self.project, self.integrated_agent, self.template, self.version = (
            _seed_project_with_flaggable_template(
                app_uuid=self.app_uuid, template_name=self.TEMPLATE_NAME
            )
        )
        self.user = User.objects.create_user(
            username="internal-dispatch",
            password="pwd",
            email="dispatch@example.com",
        )
        self.setup_internal_user_permissions(self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_flagged_template_is_skipped_by_broadcast_dispatch_gate(self):
        payload = {
            "project_uuid": str(self.project.uuid),
            "app_uuid": str(self.app_uuid),
            "template_name": self.TEMPLATE_NAME,
            "template_category": "MARKETING",
            "template_correct_category": "MARKETING",
        }

        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "FLAGGED")

        broadcast = Broadcast(flows_service=MagicMock(), audit_func=MagicMock())
        lambda_data = {"template": self.TEMPLATE_NAME}

        self.assertIsNone(
            broadcast.get_current_template(self.integrated_agent, lambda_data)
        )


@with_test_settings
class DirectSendCategoryWebhookFailClosedTest(BaseTestMixin, APITestCase):
    """Pins FR-004b / FR-005 / FR-005a — the three negative scenarios
    enumerated in ``quickstart.md`` §7. Every well-formed payload
    returns HTTP 200 (so the upstream courier does not retry) and no
    Version row is mutated when the lookup misses."""

    URL_NAME = "direct-send-category-webhook"
    TEMPLATE_NAME = "weni_order_invoiced"

    def setUp(self):
        super().setUp()
        self.url = reverse(self.URL_NAME)
        self.app_uuid = uuid4()
        self.project, self.integrated_agent, self.template, self.version = (
            _seed_project_with_flaggable_template(
                app_uuid=self.app_uuid, template_name=self.TEMPLATE_NAME
            )
        )
        self.user = User.objects.create_user(
            username="internal-failclosed",
            password="pwd",
            email="failclosed@example.com",
        )
        self.setup_internal_user_permissions(self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.original_status = self.version.status

    def _payload(self, **overrides):
        payload = {
            "project_uuid": str(self.project.uuid),
            "app_uuid": str(self.app_uuid),
            "template_name": self.TEMPLATE_NAME,
            "template_category": "MARKETING",
            "template_correct_category": "MARKETING",
        }
        payload.update(overrides)
        return payload

    def _assert_version_unchanged(self):
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, self.original_status)

    def test_misrouted_app_uuid_returns_no_matching_integrated_agent(self):
        unrelated_app_uuid = str(uuid4())

        response = self.client.post(
            self.url, self._payload(app_uuid=unrelated_app_uuid), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "detail": "No matching IntegratedAgent.",
                "templates_updated": 0,
                "integrated_agents_inspected": 0,
            },
        )
        self._assert_version_unchanged()

    def test_misrouted_template_name_returns_template_not_found(self):
        response = self.client.post(
            self.url,
            self._payload(template_name="weni_unknown_template"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "detail": "Template not found.",
                "templates_updated": 0,
                "integrated_agents_inspected": 1,
            },
        )
        self._assert_version_unchanged()

    def test_template_with_null_current_version_returns_template_not_found(self):
        self.template.current_version = None
        self.template.save(update_fields=["current_version"])

        response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "detail": "Template not found.",
                "templates_updated": 0,
                "integrated_agents_inspected": 1,
            },
        )
        self._assert_version_unchanged()
