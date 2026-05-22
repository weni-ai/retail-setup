"""Legacy datalake event snapshot tests (T035a — US4 / FR-020 / SC-008).

Pins the EXACT key set, value types, and emission count of the
``weni_datalake_sdk`` / ``CommerceWebhookPath`` event payload emitted by
the legacy dispatch path (``Broadcast._register_broadcast_event``) for
each template family pinned by T033 — body-only, image-header (s3-keyed)
+ URL button, and image-header (direct URL) + PAYMENT_REQUEST buttons +
``order_details``. Any drift in the datalake schema fails CI; consumers
downstream depend on these field names and types.

Mocks the SDK at the boundary with ``unittest.mock.patch`` so the test
never hits real infra (Constitution Principle III).
"""

from datetime import datetime
from typing import Any, Dict
from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase
from django.test.utils import override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_webhook.services.broadcast import Broadcast
from retail.projects.models import Project
from retail.templates.models import Template, Version


_LEGACY_EVENT_REQUIRED_KEYS = {
    "template",
    "template_variables",
    "contact_urn",
    "error",
    "data",
    "date",
    "project",
    "request",
    "response",
    "agent",
}
_LEGACY_EVENT_OPTIONAL_KEYS = {"status"}
_LEGACY_EVENT_ALLOWED_KEYS = _LEGACY_EVENT_REQUIRED_KEYS | _LEGACY_EVENT_OPTIONAL_KEYS


def _assert_legacy_datalake_event_shape(test_case: TestCase, event_data: Dict[str, Any]):
    """Assert the legacy datalake event matches the pre-feature baseline.

    Pinned invariants:
    - required keys (``_LEGACY_EVENT_REQUIRED_KEYS``) are always present,
    - any additional key MUST belong to ``_LEGACY_EVENT_OPTIONAL_KEYS``
      (``status`` is only emitted when ``lambda_data`` carries it),
    - value types match the schema consumers depend on,
    - the optional ``direct_send`` field MUST NOT appear on the legacy
      path (FR-020 — the legacy emission stays byte-identical).
    """
    keys = set(event_data.keys())
    missing = _LEGACY_EVENT_REQUIRED_KEYS - keys
    unexpected = keys - _LEGACY_EVENT_ALLOWED_KEYS
    test_case.assertFalse(
        missing,
        f"Legacy datalake event is missing required keys: {missing}",
    )
    test_case.assertFalse(
        unexpected,
        f"Legacy datalake event carries unexpected keys: {unexpected}",
    )
    test_case.assertNotIn(
        "direct_send",
        event_data,
        "Legacy datalake event MUST NOT carry a direct_send field (FR-020).",
    )

    test_case.assertIsInstance(event_data["template"], str)
    test_case.assertIsInstance(event_data["template_variables"], dict)
    test_case.assertIsInstance(event_data["contact_urn"], str)
    test_case.assertIsInstance(event_data["error"], dict)
    test_case.assertIsInstance(event_data["data"], dict)
    test_case.assertEqual(
        event_data["data"], {"event_type": "template_broadcast_sent"}
    )
    test_case.assertIsInstance(event_data["date"], str)
    datetime.fromisoformat(event_data["date"])
    test_case.assertIsInstance(event_data["project"], str)
    test_case.assertIsInstance(event_data["request"], dict)
    test_case.assertIsInstance(event_data["response"], dict)
    test_case.assertIsInstance(event_data["agent"], str)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "legacy-datalake",
        }
    }
)
class LegacyBroadcastDatalakeSnapshotTest(TestCase):
    """FR-020 / SC-008 — legacy datalake event payload MUST stay
    byte-identical (same keys, same value types, same emission count).
    """

    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid4(), name="Legacy DS Off", vtex_account="legacy-store"
        )
        self.agent = Agent.objects.create(
            name="Order Status Agent",
            lambda_arn="arn:aws:lambda:legacy",
            project=self.project,
            credentials={},
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
            is_active=True,
            config={},
        )

        self.flows_service = MagicMock()
        self.flows_service.send_whatsapp_broadcast.return_value = {
            "id": 4242,
            "status": "queued",
            "metadata": {"template": {"uuid": str(uuid4())}},
        }
        self.audit_calls = []

        def _capture_audit(path, data):
            self.audit_calls.append((path, data))

        self.audit_func = MagicMock(side_effect=_capture_audit)
        self.handler = Broadcast(
            flows_service=self.flows_service, audit_func=self.audit_func
        )

    def _create_template(self, *, name: str, metadata: Dict[str, Any]):
        template = Template.objects.create(
            name=name,
            integrated_agent=self.integrated_agent,
            metadata=metadata,
            is_active=True,
        )
        version = Version.objects.create(
            template=template,
            template_name=f"{name}_v1",
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="APPROVED",
        )
        template.current_version = version
        template.save(update_fields=["current_version"])
        return template

    def _dispatch(self, template, lambda_data):
        message = self.handler.build_message(self.integrated_agent, lambda_data)
        self.assertIsNotNone(message)
        self.assertNotIn(
            "direct_send",
            message.get("msg", {}),
            "Legacy msg MUST NOT carry direct_send (FR-015 / SC-004).",
        )
        self.handler.send_message(message, self.integrated_agent, lambda_data)
        return message

    def test_body_only_legacy_datalake_event_shape(self):
        """Scenario (a) — body + positional variables."""
        template = self._create_template(
            name="weni_order_invoiced",
            metadata={"language": "pt_BR"},
        )
        lambda_data = {
            "template": template.name,
            "template_variables": {"1": "Maria", "2": "12345"},
            "contact_urn": "whatsapp:5598123456789",
            "status": 0,
        }

        self._dispatch(template, lambda_data)

        self.assertEqual(len(self.audit_calls), 1)
        path, event_data = self.audit_calls[0]
        self.assertIsNotNone(path)
        _assert_legacy_datalake_event_shape(self, event_data)
        self.assertEqual(event_data["template"], "weni_order_invoiced")
        self.assertEqual(event_data["status"], 0)
        self.assertEqual(event_data["project"], str(self.project.uuid))
        self.assertEqual(event_data["agent"], str(self.agent.uuid))
        self.assertEqual(event_data["template_variables"], {"1": "Maria", "2": "12345"})

    def test_image_header_with_cta_url_button_legacy_datalake_event_shape(self):
        """Scenario (b) — image header (direct URL) + URL button."""
        template = self._create_template(
            name="weni_order_shipped",
            metadata={
                "language": "pt_BR",
                "header": {"header_type": "IMAGE", "text": ""},
            },
        )
        lambda_data = {
            "template": template.name,
            "template_variables": {
                "1": "Maria",
                "2": "12345",
                "image_url": "https://cdn.loja.com/orders/12345.jpg",
                "button": "12345",
            },
            "contact_urn": "whatsapp:5598123456789",
            "language": "pt-BR",
        }

        self._dispatch(template, lambda_data)

        self.assertEqual(len(self.audit_calls), 1)
        _, event_data = self.audit_calls[0]
        _assert_legacy_datalake_event_shape(self, event_data)
        self.assertNotIn(
            "status", event_data, "status MUST be absent when not in lambda_data."
        )
        request_msg = event_data["request"]["msg"]
        self.assertIn("attachments", request_msg)
        self.assertIn("buttons", request_msg)
        self.assertEqual(request_msg["buttons"][0]["sub_type"], "url")

    def test_image_header_with_payment_buttons_and_order_details_legacy_datalake_event_shape(
        self,
    ):
        """Scenario (c) — image header (direct URL) + PAYMENT_REQUEST
        buttons + ``order_details`` payload.
        """
        template = self._create_template(
            name="weni_payment_pending",
            metadata={"language": "pt_BR"},
        )
        order_details = {
            "reference_id": "12345-01",
            "total_amount": 26489,
        }
        payment_buttons = [
            {"type": "pix_dynamic_code", "text": "00020126580014br.gov.bcb.pix"},
            {"type": "payment_link", "text": "https://example.com/pay"},
        ]
        lambda_data = {
            "template": template.name,
            "template_variables": {
                "1": "Roberta",
                "image_url": "https://cdn.loja.com/orders/12345.jpg",
                "order_details": order_details,
                "payment_buttons": payment_buttons,
            },
            "contact_urn": "whatsapp:5598123456789",
            "language": "pt-BR",
        }

        self._dispatch(template, lambda_data)

        self.assertEqual(len(self.audit_calls), 1)
        _, event_data = self.audit_calls[0]
        _assert_legacy_datalake_event_shape(self, event_data)
        request_msg = event_data["request"]["msg"]
        self.assertEqual(request_msg["interaction_type"], "order_details")
        self.assertEqual(request_msg["order_details"], order_details)
        self.assertEqual(request_msg["buttons"][0]["sub_type"], "payment_request")
